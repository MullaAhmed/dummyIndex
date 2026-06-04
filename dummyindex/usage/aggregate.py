"""Pure roll-ups over `TurnUsage` records.

No I/O, no printing — takes parsed turns, returns frozen buckets. The CLI
boundary renders and prints them.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from .models import (
    Block,
    ChatReport,
    ModelUsage,
    PeriodBucket,
    SessionBucket,
    Totals,
    TurnUsage,
)

BLOCK_HOURS = 5

# Known Claude context-window ceilings. The transcript does not record the
# model's limit, so the window percentage infers it: the smallest tier that
# holds the session's peak window (a session that ever exceeded 200K is
# provably on the 1M tier).
CONTEXT_TIERS = (200_000, 1_000_000)


def sum_totals(turns: Iterable[TurnUsage]) -> Totals:
    """Add up the four token fields across `turns`."""
    inp = cw = cr = out = 0
    for turn in turns:
        inp += turn.input_tokens
        cw += turn.cache_creation_tokens
        cr += turn.cache_read_tokens
        out += turn.output_tokens
    return Totals(
        input_tokens=inp,
        cache_creation_tokens=cw,
        cache_read_tokens=cr,
        output_tokens=out,
    )


def grand_total(totals: Totals) -> int:
    """The single headline number: every token field added together."""
    return (
        totals.input_tokens
        + totals.cache_creation_tokens
        + totals.cache_read_tokens
        + totals.output_tokens
    )


def window_tokens(turn: TurnUsage) -> int:
    """A turn's context-window occupancy: input + both cache fields."""
    return turn.input_tokens + turn.cache_creation_tokens + turn.cache_read_tokens


def _models(turns: Iterable[TurnUsage]) -> tuple[str, ...]:
    return tuple(sorted({turn.model for turn in turns if turn.model}))


def infer_context_limit(peak_window: int) -> int:
    """Smallest known context tier that holds `peak_window` (see CONTEXT_TIERS)."""
    for tier in CONTEXT_TIERS:
        if peak_window <= tier:
            return tier
    return CONTEXT_TIERS[-1]


def by_model(turns: Iterable[TurnUsage]) -> tuple[ModelUsage, ...]:
    """Per-model usage, biggest spender first."""
    grouped: dict[str, list[TurnUsage]] = {}
    for turn in turns:
        grouped.setdefault(turn.model or "unknown", []).append(turn)
    usages = [
        ModelUsage(model=model, totals=sum_totals(group), turns=len(group))
        for model, group in grouped.items()
    ]
    return tuple(sorted(usages, key=lambda u: grand_total(u.totals), reverse=True))


def chat_report(
    session_id: str,
    main_turns: tuple[TurnUsage, ...],
    sub_turns: tuple[TurnUsage, ...],
    *,
    subagent_count: int,
) -> ChatReport:
    """Roll up one session into the `/tokens` view."""
    all_turns = main_turns + sub_turns
    window_now = window_tokens(main_turns[-1]) if main_turns else 0
    peak_window = max((window_tokens(turn) for turn in main_turns), default=0)
    return ChatReport(
        session_id=session_id,
        window_now=window_now,
        context_limit=infer_context_limit(peak_window),
        by_model=by_model(all_turns),
        total=sum_totals(all_turns),
        subagents=sum_totals(sub_turns),
        main_turns=len(main_turns),
        subagent_turns=len(sub_turns),
        subagent_count=subagent_count,
        started=min((turn.timestamp for turn in main_turns), default=None),
        last=max((turn.timestamp for turn in main_turns), default=None),
    )


def _by_period(turns: Iterable[TurnUsage], *, fmt: str) -> tuple[PeriodBucket, ...]:
    grouped: dict[str, list[TurnUsage]] = {}
    for turn in turns:
        grouped.setdefault(turn.timestamp.strftime(fmt), []).append(turn)
    return tuple(
        PeriodBucket(
            key=key,
            totals=sum_totals(group),
            turns=len(group),
            models=_models(group),
        )
        for key, group in sorted(grouped.items())
    )


def by_day(turns: Iterable[TurnUsage]) -> tuple[PeriodBucket, ...]:
    """Usage per UTC calendar day, oldest first."""
    return _by_period(turns, fmt="%Y-%m-%d")


def by_month(turns: Iterable[TurnUsage]) -> tuple[PeriodBucket, ...]:
    """Usage per UTC calendar month, oldest first."""
    return _by_period(turns, fmt="%Y-%m")


def by_session(turns: Iterable[TurnUsage]) -> tuple[SessionBucket, ...]:
    """Usage per chat session (subagents folded into their parent), newest
    activity first."""
    grouped: dict[str, list[TurnUsage]] = {}
    for turn in turns:
        grouped.setdefault(turn.session_id, []).append(turn)
    buckets = [
        SessionBucket(
            session_id=session_id,
            project=group[0].project,
            started=min(turn.timestamp for turn in group),
            last=max(turn.timestamp for turn in group),
            totals=sum_totals(group),
            turns=len(group),
            models=_models(group),
        )
        for session_id, group in grouped.items()
    ]
    return tuple(sorted(buckets, key=lambda bucket: bucket.last, reverse=True))


def into_blocks(
    turns: Iterable[TurnUsage], *, now: datetime, window_hours: int = BLOCK_HOURS
) -> tuple[Block, ...]:
    """Group activity into fixed `window_hours` windows, oldest first.

    A window opens at the first turn floored to the hour. A new window opens
    when a turn lands `window_hours` after the open time, or `window_hours`
    after the previous turn (an idle gap). A window is active when `now` falls
    inside it and the last turn was within `window_hours` of `now`.
    """
    span = timedelta(hours=window_hours)
    ordered = sorted(turns, key=lambda turn: turn.timestamp)
    if not ordered:
        return ()

    blocks: list[Block] = []
    current: list[TurnUsage] = []
    start = ordered[0].timestamp.replace(minute=0, second=0, microsecond=0)
    last = ordered[0].timestamp

    def _close() -> None:
        end = start + span
        is_active = now < end and (now - last) < span
        blocks.append(
            Block(
                start=start,
                end=end,
                totals=sum_totals(current),
                turns=len(current),
                is_active=is_active,
                models=_models(current),
            )
        )

    for turn in ordered:
        if current and (
            turn.timestamp - start >= span or turn.timestamp - last >= span
        ):
            _close()
            current = []
            start = turn.timestamp.replace(minute=0, second=0, microsecond=0)
        current.append(turn)
        last = turn.timestamp
    _close()
    return tuple(blocks)
