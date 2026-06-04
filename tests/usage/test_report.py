"""End-to-end `build_report` over a synthetic projects dir, plus rendering."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from dummyindex.usage import ReportKind, UsageError, build_report

_NOW = datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc)


def _report(kind: ReportKind, root: Path, *, session_id=None, cwd=Path("/nope")) -> str:
    return build_report(
        kind, projects_root=root, now=_NOW, session_id=session_id, cwd=cwd
    )


@pytest.mark.unit
def test_chat_report_renders_window_and_totals(usage_corpus: Path) -> None:
    out = _report(ReportKind.CHAT, usage_corpus, session_id="s1")
    assert "Context window now   2,003 tokens" in out
    assert "main" in out and "subagents(1)" in out
    assert "TOTAL" in out


@pytest.mark.unit
def test_chat_report_no_subagents_note(usage_corpus: Path) -> None:
    out = _report(ReportKind.CHAT, usage_corpus, session_id="s2")
    assert "no subagents ran" in out


@pytest.mark.unit
def test_chat_report_raises_when_session_missing(usage_corpus: Path) -> None:
    with pytest.raises(UsageError):
        _report(ReportKind.CHAT, usage_corpus, session_id="ghost")


@pytest.mark.unit
def test_daily_report_lists_both_days(usage_corpus: Path) -> None:
    out = _report(ReportKind.DAILY, usage_corpus)
    assert "2026-06-01" in out
    assert "2026-06-02" in out
    assert "daily (UTC)" in out


@pytest.mark.unit
def test_monthly_report(usage_corpus: Path) -> None:
    out = _report(ReportKind.MONTHLY, usage_corpus)
    assert "2026-06" in out


@pytest.mark.unit
def test_session_report_lists_sessions(usage_corpus: Path) -> None:
    out = _report(ReportKind.SESSION, usage_corpus)
    assert "s1" in out and "s2" in out
    assert "sessions (2)" in out


@pytest.mark.unit
def test_blocks_report_three_windows(usage_corpus: Path) -> None:
    out = _report(ReportKind.BLOCKS, usage_corpus)
    assert "5-hour blocks (3)" in out


@pytest.mark.unit
def test_history_raises_on_empty_projects_dir(tmp_path: Path) -> None:
    empty = tmp_path / "projects"
    empty.mkdir()
    with pytest.raises(UsageError):
        _report(ReportKind.DAILY, empty)


@pytest.mark.unit
def test_history_raises_when_projects_dir_absent(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        _report(ReportKind.DAILY, tmp_path / "does-not-exist")
