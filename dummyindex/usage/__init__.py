"""Token-usage reporting over Claude Code transcripts.

`dummyindex usage [chat|daily|session|monthly|blocks]`. Reads the JSONL
transcripts under `~/.claude/projects/`, deduplicates rewritten turns, and
renders token counts — the single-session `chat` view powers the `/tokens`
slash command; the rest aggregate every project.

Stdlib-only domain (bottom of the layering table): imports nothing from
`pipeline`, `analysis`, or `context`.
"""

from __future__ import annotations

from .aggregate import (
    by_day,
    by_month,
    by_session,
    chat_report,
    grand_total,
    into_blocks,
    sum_totals,
    window_tokens,
)
from .enums import ReportKind
from .errors import UsageError
from .models import (
    Block,
    ChatReport,
    PeriodBucket,
    SessionBucket,
    Totals,
    TurnUsage,
)
from .report import build_report
from .transcripts import (
    default_projects_root,
    encode_project_slug,
    find_main_transcript,
    iter_all_turns,
    load_session,
    resolve_session_id,
)

__all__ = [
    "Block",
    "ChatReport",
    "PeriodBucket",
    "ReportKind",
    "SessionBucket",
    "Totals",
    "TurnUsage",
    "UsageError",
    "build_report",
    "by_day",
    "by_month",
    "by_session",
    "chat_report",
    "default_projects_root",
    "encode_project_slug",
    "find_main_transcript",
    "grand_total",
    "into_blocks",
    "iter_all_turns",
    "load_session",
    "resolve_session_id",
    "sum_totals",
    "window_tokens",
]
