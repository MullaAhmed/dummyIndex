"""`dummyindex context onboard` — persist the user's council preferences.

The interactive 5-question flow lives in the /dummyindex skill, not here.
This handler is the thin persistence surface the skill calls once it has
the answers, plus a non-interactive ``--defaults`` path for CI.

Flags:
  --scope repo|subdir|explicit     (default: repo)
  --scope-path PATH                (used when scope==subdir)
  --mode  light|standard|deep      (default: standard) — the GLOBAL council
                                   depth fallback.
  --model current|opus-4.8|sonnet-4.6|haiku-4.5
                                   REQUIRED in the non-defaults path —
                                   the model is never silently defaulted.
  --hook / --no-hook               auto_refresh_hook (default: on)
  --doc PATH                       repeatable -> external_docs
  --platform claude|codex|both     select host-aware defaults. When omitted,
                                   infer managed project guidance; fall back
                                   to Claude when no host marker exists.
  --defaults                       write the selected host's recommended
                                   defaults and ignore every other preference
                                   flag (CI path).

Per-command depth + wiring are hand-edited config keys, not onboard flags:
  command_depths   {"reconcile": "light", ...} — override council depth per
                   command (keys: ingest|reconcile|audit|build); a one-run
                   ``--depth light|standard|deep`` flag on each depth-bearing
                   command beats both ``command_depths`` and ``--mode``.
  wired            the declarative list of plugins/skills the repo keeps
                   present (reconcile state surfaced by ``status``).

Writes ``<root>/.context/config.json`` and echoes the resolved JSON.
"""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from typing import TypeVar

from dummyindex.context.domains.config import (
    CONFIG_SCHEMA_VERSION,
    Config,
    ConfigError,
    CouncilMode,
    ModelChoice,
    ScopeKind,
    default_config,
    write_config,
)

from .common import parse_path_and_root, pull_repeatable_flag, resolve_context_root

_E = TypeVar("_E", bound=Enum)


def _pull_value_flag(args: list[str], name: str) -> tuple[str | None, list[str]]:
    """Strip a single ``--{name} VALUE`` / ``--{name}=VALUE`` occurrence.

    Returns ``(value_or_None, remaining)``. Last occurrence wins.
    """
    value: str | None = None
    rest: list[str] = []
    long_flag = f"--{name}"
    eq_prefix = f"--{name}="
    i = 0
    while i < len(args):
        a = args[i]
        if a == long_flag and i + 1 < len(args) and not args[i + 1].startswith("--"):
            value = args[i + 1]
            i += 2
        elif a.startswith(eq_prefix):
            value = a.split("=", 1)[1]
            i += 1
        else:
            rest.append(a)
            i += 1
    return value, rest


def _pull_unique_value_flag(args: list[str], name: str) -> tuple[str | None, list[str]]:
    """Pull one value flag, rejecting ambiguous duplicate occurrences."""
    long_flag = f"--{name}"
    eq_prefix = f"--{name}="
    occurrences = sum(a == long_flag or a.startswith(eq_prefix) for a in args)
    if occurrences > 1:
        raise ConfigError(f"--{name} may be passed only once")
    return _pull_value_flag(args, name)


def _pull_bool_pair(
    args: list[str], on_flag: str, off_flag: str
) -> tuple[bool | None, list[str]]:
    """Resolve a ``--flag`` / ``--no-flag`` pair. Last occurrence wins.

    Returns ``(True|False|None, remaining)`` — ``None`` when neither given.
    """
    value: bool | None = None
    rest: list[str] = []
    for a in args:
        if a == on_flag:
            value = True
        elif a == off_flag:
            value = False
        else:
            rest.append(a)
    return value, rest


def run(args: list[str]) -> int:
    # Pull onboard-local flags first; what's left feeds the shared
    # path/root parser (so --root and the positional scope still work).
    defaults = "--defaults" in args
    args = [a for a in args if a != "--defaults"]

    docs, args = pull_repeatable_flag(args, "doc")
    scope_raw, args = _pull_value_flag(args, "scope")
    scope_path, args = _pull_value_flag(args, "scope-path")
    mode_raw, args = _pull_value_flag(args, "mode")
    model_raw, args = _pull_value_flag(args, "model")
    try:
        platform_raw, args = _pull_unique_value_flag(args, "platform")
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    hook, args = _pull_bool_pair(args, "--hook", "--no-hook")

    scope, explicit_root, rest = parse_path_and_root(args)
    if rest:
        print(f"error: unknown argument(s) for `onboard`: {rest}", file=sys.stderr)
        return 2

    project_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = project_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} does not exist — run `dummyindex ingest` first",
            file=sys.stderr,
        )
        return 2

    try:
        platform = _resolve_platform(project_root, platform_raw)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if defaults:
        config = default_config(platform=platform)
    else:
        if not model_raw:
            print("error: --model is required (or pass --defaults)", file=sys.stderr)
            return 2
        try:
            _validate_explicit_host_choices(platform_raw, model_raw, hook)
            config = _build_config(
                scope_raw=scope_raw,
                scope_path=scope_path,
                mode_raw=mode_raw,
                model_raw=model_raw,
                hook=hook,
                docs=docs,
                # Without an explicit flag, retain the historical interactive
                # hook default. Managed-marker inference is for --defaults;
                # explicit interactive workflows already name their host.
                platform=platform_raw or "claude",
            )
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    out_path = write_config(context_dir, config)
    print(f"context onboard: wrote {out_path}")
    # ``write_config`` stamps the installed dummyindex version on a replacement
    # Config. Echo the bytes that actually landed rather than the pre-stamp
    # object so stdout is an exact account of the persisted configuration.
    print(out_path.read_text(encoding="utf-8"), end="")
    return 0


def _build_config(
    *,
    scope_raw: str | None,
    scope_path: str | None,
    mode_raw: str | None,
    model_raw: str,
    hook: bool | None,
    docs: list[str],
    platform: str = "claude",
) -> Config:
    """Validate the onboard flags into a frozen Config. Raises ConfigError —
    including the ``scope==subdir`` cross-field invariant (a subdir scope
    without a ``--scope-path`` is rejected by ``Config.__post_init__``)."""
    scope = _coerce_enum(scope_raw, ScopeKind, ScopeKind.REPO, "scope")
    mode = _coerce_enum(mode_raw, CouncilMode, CouncilMode.STANDARD, "mode")
    model = _coerce_enum(model_raw, ModelChoice, None, "model")
    return Config(
        schema_version=CONFIG_SCHEMA_VERSION,
        scope=scope,
        scope_path=scope_path,
        mode=mode,
        model=model,
        auto_refresh_hook=(platform != "codex") if hook is None else hook,
        external_docs=tuple(docs),
    )


def _resolve_platform(project_root: Path, explicit: str | None) -> str:
    """Resolve the host set for defaults, preferring an explicit CLI value.

    Existing repositories do not persist their install host in config (this
    command is what creates config), so the no-flag path detects dummyindex's
    exact managed guidance markers. No marker preserves the historical Claude
    default instead of guessing from unrelated user-authored files.
    """
    if explicit is not None:
        if explicit not in {"claude", "codex", "both"}:
            raise ConfigError(
                f"--platform={explicit!r} is not one of: claude, codex, both"
            )
        return explicit

    from dummyindex.codex_guidance import project_instruction_paths
    from dummyindex.context.output.agents_md import AGENTS_BEGIN_MARKER
    from dummyindex.context.output.bootstrap import BEGIN_MARKER

    claude = any(
        _has_marker_line(path, BEGIN_MARKER)
        for path in (
            project_root / ".claude" / "CLAUDE.md",
            project_root / "CLAUDE.md",
        )
    )
    codex = any(
        _has_marker_line(
            project_root.joinpath(*relative.split("/")),
            AGENTS_BEGIN_MARKER,
        )
        for relative in project_instruction_paths(project_root)
    )
    if claude and codex:
        return "both"
    if codex:
        return "codex"
    return "claude"


def _validate_explicit_host_choices(
    platform: str | None, model: str, hook: bool | None
) -> None:
    """Reject explicit host/model/hook combinations that cannot be honored."""
    if platform == "codex":
        if model != ModelChoice.CURRENT.value:
            raise ConfigError("--platform codex requires --model current")
        if hook is True:
            raise ConfigError(
                "--platform codex does not install Claude hooks; use --no-hook"
            )
    elif platform == "both" and model != ModelChoice.CURRENT.value:
        raise ConfigError("--platform both requires --model current")
    elif platform == "claude" and model == ModelChoice.CURRENT.value:
        raise ConfigError(
            "--platform claude requires a Claude model: "
            "opus-4.8, sonnet-4.6, or haiku-4.5"
        )


def _has_marker_line(path: Path, marker: str) -> bool:
    """Whether ``path`` contains ``marker`` as a complete managed line."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return any(line.lstrip("\ufeff").strip() == marker for line in text.splitlines())


def _coerce_enum(
    raw: str | None,
    enum_cls: type[_E],
    default: _E | None,
    name: str,
) -> _E:
    """Coerce ``raw`` into a member of ``enum_cls``, falling back to ``default``.

    Returns the enum member (Config stores members). Raises ConfigError when
    ``raw`` is absent with no default, or is not a valid member value.
    """
    if raw is None:
        if default is None:
            raise ConfigError(f"--{name} is required")
        return default
    try:
        return enum_cls(raw)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in enum_cls)
        raise ConfigError(f"--{name}={raw!r} is not one of: {allowed}") from exc
