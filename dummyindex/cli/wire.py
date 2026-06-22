"""`dummyindex context wire` — the interactive escalation surface for `wired`.

The headless reconciler (:func:`context.default_plugins.wire_default_plugins`)
runs inside best-effort, never-blocking ``install``/``ingest`` init: it
**classifies and reports** every declared ``wired`` entry as satisfied / acted /
needs-user but NEVER prompts. That leaves the *needs-user* entries unresolved —
an untrusted plugin that would need ``--yes``, a prior install failure, or a
``kind=skill`` entry with no enable primitive.

This command is where the prompting lives. It re-classifies ``config.wired``
READ-ONLY using the SAME shared helper ``status`` uses
(:func:`context.default_plugins.classify_wired_entry`), then resolves every entry
that is not already satisfied:

- a declared-but-absent wireable plugin (the **acted** class) is escalated via an
  injectable prompt seam (:data:`_PROMPT`) — an affirmative answer (or ``--yes``)
  performs the ``--yes``-equivalent install/enable; a decline leaves it needs-user.
- a ``kind=skill`` entry (a **needs-user** class) is surfaced as a manual notice —
  never auto-wired (no skill-enable primitive exists).
- a malformed plugin target (no ``<plugin>@<marketplace>``) is reported and skipped.

Non-interactive guards keep it from ever hanging a pipe or CI run: ``--yes``
auto-affirms every plugin (no prompt call), and a non-TTY stdin without
``--yes`` prints what *would* be prompted and exits 0 instead of blocking on
``input``. The prompt is the builtin :func:`input` by default but is reached
ONLY through :data:`_PROMPT`, so tests inject a fake and can never hang.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable

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

    Read-only classification first (shared with ``status``), then act. The
    *needs-user* bucket is what this surface resolves:

    - a ``kind=plugin`` entry that needs wiring (declared-but-absent — the
      ``acted`` bucket, plus any plugin the classifier already flagged) is the
      one we PROMPT for. An affirmative answer (or ``--yes``) performs the
      ``--yes``-equivalent install/enable; a decline leaves it needs-user.
    - a ``kind=skill`` entry is surfaced as a manual notice — never auto-wired
      (no skill-enable primitive exists).
    - a malformed plugin target (no ``<plugin>@<marketplace>``) is skipped.

    Never raises out of an unexpected per-entry failure — a wire error is
    reported and the entry stays needs-user."""
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

    # Entries this surface must resolve: a declared-but-absent (acted) plugin to
    # PROMPT-and-wire, every needs-user entry (skills → manual, bad target →
    # skip), and any other plugin the classifier flagged. Anything already
    # satisfied is left untouched.
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


def _is_wireable_plugin(entry: "WiredEntry") -> bool:
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


def _needs_user_label(entry: "WiredEntry") -> str:
    from dummyindex.context.default_plugins import WiredKind, _split_target

    if entry.kind is WiredKind.SKILL:
        return f"{entry.target} (skill — add manually)"
    if _split_target(entry.target) is None:
        return f"{entry.target} (not a <plugin>@<marketplace> target)"
    return f"{entry.target} (untrusted plugin — confirm to wire)"


def _split_ok(entry: "WiredEntry") -> bool:
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


def _wire_plugin(out_root: Path, entry: "WiredEntry") -> bool:
    """Wire one plugin entry (the ``--yes``-equivalent path). ``True`` on success.

    Mirrors the headless reconciler's action: ``enable_plugin`` writes the
    declaration into the committed ``settings.json``, then
    ``install_default_plugins`` best-effort materialises the bits. An install the
    CLI rejects leaves the entry needs-user (we return ``False``). Never raises —
    a settings-write failure is caught and reported as a failure to wire."""
    from dummyindex.context.claude_plugins import enable_plugin
    from dummyindex.context.claude_settings import MalformedSettingsError
    from dummyindex.context.default_plugins import (
        _split_target,
        install_default_plugins,
    )

    parts = _split_target(entry.target)
    if parts is None:
        return False
    plugin, marketplace = parts
    settings_path = out_root / ".claude" / "settings.json"
    try:
        enable_plugin(settings_path, plugin=plugin, marketplace=marketplace)
    except (MalformedSettingsError, OSError):
        return False
    install = install_default_plugins(out_root, enabled=True)
    for failed_target, _msg in install.errors:
        if failed_target == entry.target:
            return False
    return True
