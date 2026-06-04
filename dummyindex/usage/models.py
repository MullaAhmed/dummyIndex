"""Frozen data carriers for token-usage reporting — data only, no behaviour.

Token arithmetic (summing, grand totals) lives in `aggregate.py`; these
classes just hold the parsed and rolled-up numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TurnUsage:
    """One assistant turn's token usage, parsed from a transcript line.

    `session_id` and `project` are derived from the file path (so a subagent
    turn is attributed to its parent session), not from fields inside the line.
    """

    timestamp: datetime
    session_id: str
    project: str
    model: str
    input_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    output_tokens: int
    is_subagent: bool


@dataclass(frozen=True)
class Totals:
    """A rolled-up token count. The four fields Claude Code reports per turn."""

    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class PeriodBucket:
    """Usage for one calendar period (a day `YYYY-MM-DD` or month `YYYY-MM`)."""

    key: str
    totals: Totals
    turns: int
    models: tuple[str, ...]


@dataclass(frozen=True)
class SessionBucket:
    """Usage for one chat session, including its subagents."""

    session_id: str
    project: str
    started: datetime
    last: datetime
    totals: Totals
    turns: int
    models: tuple[str, ...]


@dataclass(frozen=True)
class Block:
    """A 5-hour billing-style window grouping contiguous activity."""

    start: datetime
    end: datetime
    totals: Totals
    turns: int
    is_active: bool
    models: tuple[str, ...]


@dataclass(frozen=True)
class ModelUsage:
    """Cumulative usage attributed to one model (main + subagent turns)."""

    model: str
    totals: Totals
    turns: int


@dataclass(frozen=True)
class ChatReport:
    """The single-session view behind the `/tokens` command.

    `window_now` is the most recent main-thread turn's input + cache (what
    `/context` shows); `context_limit` is the inferred model context ceiling
    used for the window percentage. `by_model` breaks the deduplicated
    cumulative totals down per model; `total` is their sum and `subagents` is
    the subagent-only portion (folded into `total`). `started`/`last` are the
    first and last main-turn timestamps (None when the session has no turns).
    """

    session_id: str
    window_now: int
    context_limit: int
    by_model: tuple[ModelUsage, ...]
    total: Totals
    subagents: Totals
    main_turns: int
    subagent_turns: int
    subagent_count: int
    started: Optional[datetime]
    last: Optional[datetime]
