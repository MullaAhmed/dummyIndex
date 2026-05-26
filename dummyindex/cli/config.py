"""`dummyindex context config <action>` — read the per-repo config.json.

Today the only action is ``show`` (print the stored JSON). ``get`` / ``set``
are reserved for v0.16 — the dispatcher rejects them with a clear error so
the surface is explicitly forward-leaning rather than silently broken.
"""
from __future__ import annotations

import json
import sys

from dummyindex.context.domains.config import ConfigError, read_config

from ._common import _parse_path_and_root, _resolve_context_root


def _cmd_config(args: list[str]) -> int:
    if not args:
        print("error: config requires a sub-action (show)", file=sys.stderr)
        return 2

    action, rest_args = args[0], args[1:]
    if action != "show":
        print(f"error: unknown config sub-action '{action}' (expected: show)", file=sys.stderr)
        return 2

    scope, explicit_root, rest = _parse_path_and_root(rest_args)
    if rest:
        print(f"error: unknown argument(s) for `config show`: {rest}", file=sys.stderr)
        return 2

    project_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = project_root / ".context"

    try:
        config = read_config(context_dir)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if config is None:
        print(
            "no config.json — run onboarding (/dummyindex --reconfigure) or "
            "'dummyindex context onboard --defaults'",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(config.to_dict(), indent=2))
    return 0
