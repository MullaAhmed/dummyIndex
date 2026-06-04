"""Rendering: empty-input guards, truncation, and a chat smoke."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dummyindex.usage import ChatReport, SessionBucket, Totals
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
def test_render_chat_unknown_model_when_empty() -> None:
    report = ChatReport(
        session_id="deadbeef",
        window_now=0,
        main=Totals(),
        subagents=Totals(),
        main_turns=0,
        subagent_turns=0,
        subagent_count=0,
        models=(),
    )
    out = render_chat(report)
    assert "unknown" in out
    assert "no subagents ran" in out
