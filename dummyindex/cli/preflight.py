"""`dummyindex context preflight` — report the existing setup before writing.

Read-only inventory of ``.claude/``, ``.context/`` ownership, and git state
so the running session can show "what I will touch vs leave alone" and refuse
to clobber a config it doesn't understand. A ``.context/`` that doesn't carry
dummyindex's ``meta.json`` marker is reported as foreign — not managed.
Prints markdown by default, JSON with ``--json``.
"""
from __future__ import annotations

import json
import sys

from .common import parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    from dummyindex.context.domains.preflight import (
        build_preflight_report,
        render_preflight_md,
    )

    scope, explicit_root, rest = parse_path_and_root(args)
    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    if rest:
        print(f"error: unknown argument(s) for `preflight`: {rest}", file=sys.stderr)
        return 2

    project_root = resolve_context_root(scope, explicit_root=explicit_root)
    report = build_preflight_report(project_root)

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_preflight_md(report))
    return 0
