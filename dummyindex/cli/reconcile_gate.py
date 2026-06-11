"""`dummyindex context reconcile-gate` — Stop-hook gate that blocks session
exit once when `.context/` is stale after a substantial session.

Wire-only: read the Stop-hook JSON from stdin, decide, print the block
payload (if any), and ALWAYS return 0 — a Stop hook must never fail the turn.
"""
from __future__ import annotations

import sys

from .common import parse_path_and_root, resolve_context_root
from .memory import _read_hook_stdin, _resolve_transcript


def run(args: list[str]) -> int:
    from dummyindex.context.reconcile_gate import decide_block

    scope, explicit_root, leftover = parse_path_and_root(args)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2
    root = resolve_context_root(scope, explicit_root=explicit_root)

    hook = _read_hook_stdin()
    _session_id, main_transcript = _resolve_transcript(hook, root)
    stop_hook_active = bool(hook.get("stop_hook_active"))
    payload = decide_block(
        root=root,
        main_transcript=main_transcript,
        stop_hook_active=stop_hook_active,
    )
    if payload:
        print(payload)
    return 0  # a Stop hook must never fail the turn
