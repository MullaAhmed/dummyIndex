"""`dummyindex context onboard` — persist the user's council preferences.

The interactive 5-question flow lives in the /dummyindex skill, not here.
This handler is the thin persistence surface the skill calls once it has
the answers, plus a non-interactive ``--defaults`` path for CI.

Flags:
  --scope repo|subdir|explicit     (default: repo)
  --scope-path PATH                (used when scope==subdir)
  --mode  light|standard|deep      (default: standard)
  --model opus-4.8|sonnet-4.6|haiku-4.5
                                   REQUIRED in the non-defaults path —
                                   the model is never silently defaulted.
  --hook / --no-hook               auto_refresh_hook (default: on)
  --doc PATH                       repeatable -> external_docs
  --defaults                       write the recommended defaults and ignore
                                   every other flag (CI path).

Writes ``<root>/.context/config.json`` and echoes the resolved JSON.
"""
from __future__ import annotations

import json
import sys
from enum import Enum
from typing import TypeVar

from dummyindex.context.domains.config import (
    Config,
    ConfigError,
    CONFIG_SCHEMA_VERSION,
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
        if a == long_flag and i + 1 < len(args):
            value = args[i + 1]
            i += 2
        elif a.startswith(eq_prefix):
            value = a.split("=", 1)[1]
            i += 1
        else:
            rest.append(a)
            i += 1
    return value, rest


def _pull_bool_pair(args: list[str], on_flag: str, off_flag: str) -> tuple[bool | None, list[str]]:
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

    if defaults:
        config = default_config()
    else:
        if not model_raw:
            print("error: --model is required (or pass --defaults)", file=sys.stderr)
            return 2
        try:
            config = _build_config(
                scope_raw=scope_raw,
                scope_path=scope_path,
                mode_raw=mode_raw,
                model_raw=model_raw,
                hook=hook,
                docs=docs,
            )
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    out_path = write_config(context_dir, config)
    print(f"context onboard: wrote {out_path}")
    print(json.dumps(config.to_dict(), indent=2))
    return 0


def _build_config(
    *,
    scope_raw: str | None,
    scope_path: str | None,
    mode_raw: str | None,
    model_raw: str,
    hook: bool | None,
    docs: list[str],
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
        auto_refresh_hook=True if hook is None else hook,
        external_docs=tuple(docs),
    )


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
