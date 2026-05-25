"""`dummyindex context bootstrap` — regenerate CLAUDE.md managed block only."""
from __future__ import annotations
import sys
from ._common import _parse_path_and_root, _resolve_context_root


def _cmd_bootstrap(args: list[str]) -> int:
    from dummyindex.context.output.bootstrap import (
        UnbalancedMarkersError,
        bootstrap_claude_md,
    )

    scope, explicit_root, rest = _parse_path_and_root(args)
    if rest:
        print(f"error: unknown argument(s) for `bootstrap`: {rest}", file=sys.stderr)
        return 2
    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    claude_md = out_root / ".claude" / "CLAUDE.md"
    try:
        bootstrap_claude_md(claude_md)
    except UnbalancedMarkersError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(f"CLAUDE.md  ->  managed block written: {claude_md.resolve()}")
    return 0

