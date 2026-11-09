"""`dummyindex context wire`: the interactive escalation surface for `wired`.

The headless reconciler only classifies and reports, never prompting. This re-classifies
``config.wired`` read-only (``classify_wired_entry``, shared with ``status``) and prompts
via :data:`_PROMPT` for each untrusted wireable plugin; skills get a manual notice and
malformed targets are skipped. Never hangs: ``--yes`` affirms without prompting, and a
non-TTY stdin without ``--yes`` prints what would be prompted and exits 0.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .common import parse_path_and_root, resolve_context_root

if TYPE_CHECKING:
    from dummyindex.context.default_plugins import WiredEntry

# Injectable prompt seam. Tests monkeypatch this (or pass ``prompt=``) so the
# real :func:`input` is never called and the suite can never block on stdin.
_PROMPT: Callable[[str], str] = input


def run(args: list[str]) -> int:
    scope, explicit_root, rest = parse_path_and_root(args)
    auto_yes = "--yes" in rest
    rest = [a for a in rest if a != "--yes"]
    if rest:
        print(f"error: unknown argument(s) for `wire`: {rest}", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} does not exist — run `dummyindex ingest` first",
            file=sys.stderr,
        )
        return 2

    return _wire(out_root, context_dir, auto_yes=auto_yes, prompt=_PROMPT)


def _wire(
    out_root: Path,
    context_dir: Path,
    *,
    auto_yes: bool,
    prompt: Callable[[str], str],
) -> int:
    """Reconcile ``config.wired`` interactively. Returns the process exit code.

    Classify read-only first (shared with ``status``), then resolve each unsatisfied
    entry: prompt for a wireable plugin (``--yes`` or a yes installs it, a decline
    leaves it needs-user); skills are manual, never auto-wired; malformed targets are
    skipped. A wire error is reported and leaves the entry needs-user."""
    from dummyindex.context.default_plugins import (
        WiredClass,
        WiredKind,
        _already_decided,
        classify_wired_entry,
    )
    from dummyindex.context.domains.config import ConfigError, read_config

    try:
        config = read_config(context_dir)
    except ConfigError as exc:
        print(f"error: could not read config.json: {exc}", file=sys.stderr)
        return 2

    if config is None:
        print("no config; run `dummyindex context onboard` first — nothing to wire.")
        return 0
    if not config.wired:
        print("wired: none declared — nothing to wire.")
        return 0

    def is_present(target: str) -> bool:
        return _already_decided(out_root, target)

    classified = [
        (entry, classify_wired_entry(entry, is_present=is_present))
        for entry in config.wired
    ]
    satisfied = sum(1 for _, c in classified if c is WiredClass.SATISFIED)

    # Resolve everything not already satisfied: wireable plugins are prompted;
    # skills and bad targets are surfaced.
    to_resolve = [e for e, c in classified if c is not WiredClass.SATISFIED]
    prompt_plugins = [e for e in to_resolve if _is_wireable_plugin(e)]

    # Non-TTY + no --yes: never block on input. Report what WOULD be prompted.
    interactive = auto_yes or _stdin_is_tty()
    if not interactive and prompt_plugins:
        print(
            f"wired: {len(config.wired)} declared "
            f"({satisfied} satisfied, {len(to_resolve)} need you)."
        )
        print("stdin is not a TTY and --yes was not passed — not prompting.")
        for entry in to_resolve:
            print(f"  would prompt: {_needs_user_label(entry)}")
        return 0

    wired_now: list[str] = []
    skipped: list[str] = []
    remaining: list[str] = []

    for entry in to_resolve:
        if entry.kind is WiredKind.SKILL:
            print(
                f"skill: {entry.target} must be added manually "
                f"(no skill-enable primitive; declared + surfaced only)"
            )
            remaining.append(entry.target)
            continue
        if not _split_ok(entry):
            print(
                f"needs-user: {entry.target} is not a <plugin>@<marketplace> "
                f"target — skipped"
            )
            remaining.append(entry.target)
            continue
        if auto_yes or _affirm(prompt, entry.target):
            if _wire_plugin(out_root, entry):
                wired_now.append(entry.target)
                print(f"wired: {entry.target}")
            else:
                remaining.append(entry.target)
                print(f"could not wire: {entry.target} (left needs-user)")
        else:
            skipped.append(entry.target)
            remaining.append(entry.target)
            print(f"skipped: {entry.target} (left needs-user)")

    print(
        f"summary: {len(wired_now)} wired, {len(skipped)} skipped, "
        f"{len(remaining)} needs-user remaining "
        f"({satisfied} already satisfied)."
    )
    return 0


def _is_wireable_plugin(entry: WiredEntry) -> bool:
    """True for a plugin entry with a valid ``<plugin>@<marketplace>`` target —
    the only entries this surface will prompt-and-wire (skills/bad targets are
    surfaced, never wired)."""
    from dummyindex.context.default_plugins import WiredKind

    return entry.kind is WiredKind.PLUGIN and _split_ok(entry)


def _stdin_is_tty() -> bool:
    """True iff stdin is an interactive terminal. Any error reads as not-a-TTY."""
    try:
        return bool(sys.stdin.isatty())
    except Exception:  # pragma: no cover - defensive; isatty rarely raises
        return False


def _needs_user_label(entry: WiredEntry) -> str:
    from dummyindex.context.default_plugins import WiredKind, _split_target

    if entry.kind is WiredKind.SKILL:
        return f"{entry.target} (skill — add manually)"
    if _split_target(entry.target) is None:
        return f"{entry.target} (not a <plugin>@<marketplace> target)"
    return f"{entry.target} (untrusted plugin — confirm to wire)"


def _split_ok(entry: WiredEntry) -> bool:
    from dummyindex.context.default_plugins import _split_target

    return _split_target(entry.target) is not None


def _affirm(prompt: Callable[[str], str], target: str) -> bool:
    """Ask the user whether to wire an untrusted plugin. Default is No.

    Any prompt error (EOF on a piped stdin that slipped past the TTY guard, etc.)
    reads as a decline — never an unhandled crash."""
    try:
        answer = prompt(f"Wire untrusted plugin {target}? [y/N] ")
    except (EOFError, KeyboardInterrupt, OSError):
        return False
    return answer.strip().lower() in ("y", "yes")


def _wire_plugin(out_root: Path, entry: WiredEntry) -> bool:
    """Wire one plugin entry (the ``--yes``-equivalent path). ``True`` on success.

    Declaration and materialisation both get the same one-entry selection, so a
    reviewed default gets its reviewed marketplace and a custom plugin can never
    install unrelated defaults. Any declaration or install error returns ``False``."""
    from dummyindex.context.default_plugins import (
        _split_target,
        install_default_plugins,
        wire_default_plugins,
    )

    if _split_target(entry.target) is None:
        return False

    selected = (entry,)
    declared = wire_default_plugins(selected, out_root, enabled=True)
    if declared.errors or declared.needs_user:
        return False
    install = install_default_plugins(out_root, wired=selected, enabled=True)
    return not install.errors
