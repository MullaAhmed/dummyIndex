"""Frozen data carriers for token-usage reporting — data only, no behaviour.

Token arithmetic (summing, grand totals) lives in `aggregate.py`; these
classes just hold the parsed and rolled-up numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
class ChatReport:
    """The single-session view behind the `/tokens` command.

    `window_now` is the most recent main-thread turn's input + cache (what
    `/context` shows); `main` and `subagents` are cumulative, deduplicated.
    """

    session_id: str
    window_now: int
    main: Totals
    subagents: Totals
    main_turns: int
    subagent_turns: int
    subagent_count: int
    models: tuple[str, ...]
