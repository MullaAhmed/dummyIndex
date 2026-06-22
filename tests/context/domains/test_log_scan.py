"""Tests for dummyindex.context.domains.log_scan — shared resumption-log scan.

Covers the pure ``last_matching`` helper that both the council and audit
resumption logs delegate to (the deduplicated ``latest_status`` body).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from dummyindex.context.domains.log_scan import last_matching


@dataclass(frozen=True)
class _Entry:
    key: int
    agent: str
    status: str
    note: Optional[str] = None


@pytest.mark.unit
def test_last_matching_returns_most_recent_match() -> None:
    """When several entries match the predicate, the last one in order wins."""
    entries = [
        _Entry(key=1, agent="security", status="started"),
        _Entry(key=1, agent="security", status="complete"),
        _Entry(key=2, agent="security", status="started"),
    ]
    result = last_matching(
        entries,
        lambda e: e.key == 1 and e.agent == "security",
    )
    assert result == "complete"


@pytest.mark.unit
def test_last_matching_empty_iterable_returns_none() -> None:
    assert last_matching([], lambda e: True) is None


@pytest.mark.unit
def test_last_matching_no_match_returns_none() -> None:
    entries = [
        _Entry(key=1, agent="security", status="complete"),
        _Entry(key=2, agent="architect", status="started"),
    ]
    assert last_matching(entries, lambda e: e.key == 9) is None


@pytest.mark.unit
def test_last_matching_default_attr_is_status() -> None:
    """The default ``attr`` reads ``.status`` without it being passed."""
    entries = [_Entry(key=0, agent="dev", status="skipped")]
    assert last_matching(entries, lambda e: e.agent == "dev") == "skipped"


@pytest.mark.unit
def test_last_matching_custom_attr() -> None:
    """A non-default ``attr`` selects a different field of the matched entry."""
    entries = [
        _Entry(key=1, agent="dev", status="started", note="first"),
        _Entry(key=1, agent="dev", status="complete", note="second"),
    ]
    assert last_matching(entries, lambda e: e.key == 1, attr="note") == "second"
