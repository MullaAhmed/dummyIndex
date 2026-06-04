"""Rendering: empty-input guards, truncation, and a chat smoke."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dummyindex.usage import ChatReport, ModelUsage, SessionBucket, Totals
from dummyindex.usage.render import (
    render_blocks,
    render_chat,
    render_periods,
    render_sessions,
)


@pytest.mark.unit
def test_render_periods_empty() -> None:
    assert "no usage found" in render_periods([], title="daily", key_header="day")


@pytest.mark.unit
def test_render_sessions_empty() -> None:
    assert "no usage found" in render_sessions([])


@pytest.mark.unit
def test_render_blocks_empty() -> None:
    assert "no usage found" in render_blocks([])


@pytest.mark.unit
def test_render_sessions_truncates_long_project() -> None:
    bucket = SessionBucket(
        session_id="abcdef123456",
        project="x" * 60,
        started=datetime(2026, 6, 1, tzinfo=timezone.utc),
        last=datetime(2026, 6, 1, tzinfo=timezone.utc),
        totals=Totals(1, 1, 1, 1),
        turns=1,
        models=("claude-opus-4-8",),
    )
    out = render_sessions([bucket])
    assert "…" in out  # project name was shortened
    assert "abcdef12" in out  # session id truncated to 8


@pytest.mark.unit
def test_render_chat_empty_session() -> None:
    report = ChatReport(
        session_id="deadbeef",
        window_now=0,
        context_limit=200_000,
        by_model=(),
        total=Totals(),
        subagents=Totals(),
        main_turns=0,
        subagent_turns=0,
        subagent_count=0,
        started=None,
        last=None,
    )
    out = render_chat(report)
    assert "0 main turns" in out
    assert "subagents: none" in out
    assert "TOTAL" in out


@pytest.mark.unit
def test_render_chat_per_model_timing_and_window_pct() -> None:
    report = ChatReport(
        session_id="abcd1234",
        window_now=450_000,
        context_limit=1_000_000,
        by_model=(
            ModelUsage("claude-opus-4-8", Totals(100, 200, 300, 50), 5),
            ModelUsage("claude-sonnet-4-6", Totals(1, 2, 3, 4), 2),
        ),
        total=Totals(101, 202, 303, 54),
        subagents=Totals(1, 2, 3, 4),
        main_turns=5,
        subagent_turns=2,
        subagent_count=1,
        started=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        last=datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc),
    )
    out = render_chat(report)
    assert "claude-opus-4-8" in out and "claude-sonnet-4-6" in out
    assert "≈45% of 1M" in out  # 450,000 / 1,000,000
    assert "2h30m" in out  # duration
    assert "(+2 subagent)" in out
    assert "subagents: 1 transcript(s)" in out


@pytest.mark.unit
@pytest.mark.parametrize(
    "delta_seconds, expected",
    [(42, "42s"), (300, "5m"), (90_000, "1d01h")],
)
def test_render_chat_duration_formats(delta_seconds: int, expected: str) -> None:
    from datetime import timedelta

    start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
    report = ChatReport(
        session_id="abcd1234",
        window_now=10,
        context_limit=200_000,
        by_model=(ModelUsage("claude-opus-4-8", Totals(1, 0, 0, 1), 1),),
        total=Totals(1, 0, 0, 1),
        subagents=Totals(),
        main_turns=1,
        subagent_turns=0,
        subagent_count=0,
        started=start,
        last=start + timedelta(seconds=delta_seconds),
    )
    assert expected in render_chat(report)
