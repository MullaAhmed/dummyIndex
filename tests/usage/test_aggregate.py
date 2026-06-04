"""Roll-up logic: totals, periods, sessions, 5-hour blocks, chat report."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from dummyindex.usage import (
    Totals,
    by_day,
    by_month,
    by_session,
    chat_report,
    grand_total,
    into_blocks,
    iter_all_turns,
    load_session,
    sum_totals,
    window_tokens,
)


@pytest.mark.unit
def test_grand_total_sums_all_fields() -> None:
    assert grand_total(Totals(1, 2, 3, 4)) == 10


@pytest.mark.unit
def test_sum_totals_over_corpus(usage_corpus: Path) -> None:
    turns = tuple(iter_all_turns(usage_corpus))
    totals = sum_totals(turns)
    # input: 100+2+3 (s1) + 1 (sub) + 10 (s2) = 116
    assert totals.input_tokens == 116
    # cache_read: 1000+1200+2000 + 500 + 300 = 5000
    assert totals.cache_read_tokens == 5000


@pytest.mark.unit
def test_by_day_buckets_two_utc_days(usage_corpus: Path) -> None:
    days = by_day(iter_all_turns(usage_corpus))
    assert [d.key for d in days] == ["2026-06-01", "2026-06-02"]
    day1 = days[0]
    # t1 + sub + t2 + s2 = 4 turns on 06-01.
    assert day1.turns == 4
    assert day1.totals.input_tokens == 100 + 1 + 2 + 10
    assert days[1].turns == 1  # only t3 on 06-02


@pytest.mark.unit
def test_by_month_collapses_to_single_bucket(usage_corpus: Path) -> None:
    months = by_month(iter_all_turns(usage_corpus))
    assert [m.key for m in months] == ["2026-06"]
    assert months[0].turns == 5


@pytest.mark.unit
def test_by_session_groups_and_orders_newest_first(usage_corpus: Path) -> None:
    sessions = by_session(iter_all_turns(usage_corpus))
    assert [s.session_id for s in sessions] == ["s1", "s2"]  # s1 active later
    s1 = sessions[0]
    assert s1.turns == 4  # 3 main + 1 subagent
    assert s1.started == datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    assert s1.last == datetime(2026, 6, 2, 9, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_into_blocks_splits_on_5h_gap(usage_corpus: Path) -> None:
    now = datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc)
    blocks = into_blocks(iter_all_turns(usage_corpus), now=now)
    # 10:00-cluster, 20:00 (s2), next-day 09:00 → three windows.
    assert len(blocks) == 3
    assert blocks[0].start == datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    assert blocks[0].turns == 3  # t1, sub, t2
    assert blocks[1].turns == 1  # s2
    assert blocks[2].turns == 1  # t3
    # All blocks are historical relative to `now`.
    assert not any(b.is_active for b in blocks)


@pytest.mark.unit
def test_into_blocks_marks_active_window() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    # `now` sits inside the first 5h window and within 5h of the last turn.
    blocks = into_blocks(_corpus_turns_within_one_window(), now=now)
    assert len(blocks) == 1
    assert blocks[0].is_active is True


@pytest.mark.unit
def test_into_blocks_empty() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    assert into_blocks((), now=now) == ()


@pytest.mark.unit
def test_chat_report_window_is_last_main_turn(usage_corpus: Path) -> None:
    main, sub, _ = load_session(usage_corpus / "proj-a" / "s1.jsonl")
    report = chat_report("s1", main, sub, subagent_count=1)
    # Last main turn (t3): input 3 + cw 0 + cr 2000 = 2003.
    assert report.window_now == 2003
    assert report.window_now == window_tokens(main[-1])
    assert report.main_turns == 3
    assert report.subagent_turns == 1
    assert report.subagent_count == 1
    assert report.main.cache_read_tokens == 1000 + 1200 + 2000


def _corpus_turns_within_one_window():
    from dummyindex.usage.models import TurnUsage

    return (
        TurnUsage(
            timestamp=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            session_id="s",
            project="p",
            model="claude-opus-4-8",
            input_tokens=5,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            output_tokens=5,
            is_subagent=False,
        ),
    )
