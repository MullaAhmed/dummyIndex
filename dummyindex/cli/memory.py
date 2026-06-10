"""`dummyindex context memory <verb>` — session-memory store ops.

Verbs:
  session-start   read-only emit for the SessionStart hook (silent when the
                  remember plugin is present or the store is empty).
  roll            relocate dated entries down the tiers (idempotent).
  init            create `.context/session-memory/` + empty tier stubs.
  nudge           Stop-hook: emit handoff CTA when session is significant.
  breadcrumb      PreCompact-hook: write a deterministic entry to now.md.

Wire-only: parse args, call the memory domain, print, return an exit code.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from .common import parse_path_and_root, resolve_context_root


def _read_hook_stdin() -> dict[str, object]:
    """Parse the hook's JSON from stdin; {} when absent/at a TTY/malformed."""
    import json

    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _resolve_transcript(
    hook: dict[str, object], root: Path
) -> tuple[str, Path | None]:
    from dummyindex.context.domains.memory import find_main_transcript, resolve_session_id

    raw_sid = hook.get("session_id")
    session_id = raw_sid if isinstance(raw_sid, str) else (resolve_session_id() or "")
    tp = hook.get("transcript_path")
    if isinstance(tp, str) and tp:
        return session_id, Path(tp)
    return session_id, find_main_transcript(session_id=session_id or None, cwd=root)


def run(args: list[str]) -> int:
    from dummyindex.context.domains.memory import (
        MemoryVerb,
        ensure_memory_store,
        memory_dir,
        render_session_start,
        roll_tiers,
    )

    if not args:
        print(
            f"error: usage: dummyindex context memory {{{'|'.join(v.value for v in MemoryVerb)}}}",
            file=sys.stderr,
        )
        return 2
    verb_str, rest = args[0], args[1:]
    try:
        verb = MemoryVerb(verb_str)
    except ValueError:
        print(f"error: unknown memory verb {verb_str!r}", file=sys.stderr)
        return 2

    scope, explicit_root, leftover = parse_path_and_root(rest)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2
    root = resolve_context_root(scope, explicit_root=explicit_root)

    if verb is MemoryVerb.NUDGE:
        from dummyindex.context.domains.memory import decide_nudge

        session_id, main_transcript = _resolve_transcript(_read_hook_stdin(), root)
        payload = decide_nudge(
            root=root,
            main_transcript=main_transcript,
            session_id=session_id,
            now=datetime.now(),
        )
        if payload:
            print(payload)
        return 0  # a Stop hook must never fail the turn

    if verb is MemoryVerb.BREADCRUMB:
        from dummyindex.context.domains.memory import run_breadcrumb

        _session_id, main_transcript = _resolve_transcript(_read_hook_stdin(), root)
        run_breadcrumb(root=root, main_transcript=main_transcript, now=datetime.now())
        return 0  # a PreCompact hook must never fail

    if verb is MemoryVerb.SESSION_START:
        block = render_session_start(root)
        if block:
            print(block)
        return 0  # a SessionStart hook must never fail the session

    context_dir = root / ".context"

    if verb is MemoryVerb.INIT:
        created = ensure_memory_store(context_dir)
        if created:
            print(
                f"memory init: created {', '.join(created)} under "
                f"{memory_dir(context_dir)}"
            )
        else:
            print(f"memory init: store already present at {memory_dir(context_dir)}")
        return 0

    # verb is MemoryVerb.ROLL
    if not memory_dir(context_dir).is_dir():
        print("memory roll: no .context/session-memory/ store; nothing to do.")
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
