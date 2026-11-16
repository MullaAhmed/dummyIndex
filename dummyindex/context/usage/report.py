"""Orchestrate a usage report end to end: locate transcripts, aggregate,
render to a display string.

The single entry point the CLI calls. Stays free of `print`/`sys.exit` and
of environment reads (the caller resolves `session_id`, `cwd`, and
`projects_root`) so it is straightforward to test.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import aggregate, render, transcripts
from .enums import ReportKind
from .errors import UsageError


def build_report(
    kind: ReportKind,
    *,
    projects_root: Path,
    now: datetime,
    session_id: str | None,
    cwd: Path,
) -> str:
    """Render the requested report to a display string.

    Raises `UsageError` when the data needed for the report is absent (no
    projects directory, or no transcript for the current session).
    """
    if kind is ReportKind.CHAT:
        return _chat(projects_root, session_id=session_id, cwd=cwd)

    turns = tuple(transcripts.iter_all_turns(projects_root))
    if not turns:
        raise UsageError(
            f"no usage found under {projects_root}", path=str(projects_root)
        )

    if kind is ReportKind.DAILY:
        return render.render_periods(
            aggregate.by_day(turns), title="daily", key_header="day"
        )
    if kind is ReportKind.MONTHLY:
        return render.render_periods(
            aggregate.by_month(turns), title="monthly", key_header="month"
        )
    if kind is ReportKind.SESSION:
        return render.render_sessions(aggregate.by_session(turns))
    if kind is ReportKind.BLOCKS:
        return render.render_blocks(aggregate.into_blocks(turns, now=now))
    raise UsageError(f"unsupported report kind: {kind.value}")  # pragma: no cover


def _chat(projects_root: Path, *, session_id: str | None, cwd: Path) -> str:
    main_transcript = transcripts.find_main_transcript(
        projects_root, session_id=session_id, cwd=cwd
    )
    if main_transcript is None:
        if session_id:
            # The session is known, but its transcript isn't on disk yet (a
            # brand-new chat whose first turn hasn't been flushed). Report an
            # empty session — never another session's numbers.
            return render.render_chat(
                aggregate.chat_report(session_id, (), (), subagent_count=0)
            )
        raise UsageError(
            "could not identify the current session: "
            f"${transcripts.SESSION_ID_ENV} is unset and no transcript exists "
            f"under {projects_root / transcripts.encode_project_slug(cwd)}"
        )
    main, sub, n_subagents = transcripts.load_session(main_transcript)
    report = aggregate.chat_report(
        main_transcript.stem, main, sub, subagent_count=n_subagents
    )
    return render.render_chat(report)
