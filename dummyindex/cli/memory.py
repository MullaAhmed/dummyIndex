"""`dummyindex context memory <verb>` — session-memory store ops.

Verbs:
  session-start   read-only emit for the SessionStart hook (silent when the
                  remember plugin is present or the store is empty).
  roll            relocate dated entries down the tiers (idempotent).
  init            create `.context/memory/` + empty tier stubs.

Wire-only: parse args, call the memory domain, print, return an exit code.
"""
from __future__ import annotations

import sys
from datetime import date

from ._common import _parse_path_and_root, _resolve_context_root

_VERBS = ("session-start", "roll", "init")


def _cmd_memory(args: list[str]) -> int:
    from dummyindex.context.domains.memory import (
        ensure_memory_store,
        memory_dir,
        render_session_start,
        roll_tiers,
    )

    if not args:
        print(
            f"error: usage: dummyindex context memory {{{'|'.join(_VERBS)}}}",
            file=sys.stderr,
        )
        return 2
    verb, rest = args[0], args[1:]
    if verb not in _VERBS:
        print(f"error: unknown memory verb {verb!r}", file=sys.stderr)
        return 2

    scope, explicit_root, leftover = _parse_path_and_root(rest)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2
    root = _resolve_context_root(scope, explicit_root=explicit_root)

    if verb == "session-start":
        block = render_session_start(root)
        if block:
            print(block)
        return 0  # a SessionStart hook must never fail the session

    context_dir = root / ".context"

    if verb == "init":
        created = ensure_memory_store(context_dir)
        if created:
            print(
                f"memory init: created {', '.join(created)} under "
                f"{memory_dir(context_dir)}"
            )
        else:
            print(f"memory init: store already present at {memory_dir(context_dir)}")
        return 0

    # verb == "roll"
    if not memory_dir(context_dir).is_dir():
        print("memory roll: no .context/memory/ store; nothing to do.")
        return 0
    report = roll_tiers(context_dir, today=date.today())
    suffix = (
        f" (dates: {', '.join(report.moved_dates)})" if report.moved_dates else ""
    )
    print(
        f"memory roll: now→recent {report.now_to_recent}, "
        f"recent→archive {report.recent_to_archive}{suffix}"
    )
    return 0
