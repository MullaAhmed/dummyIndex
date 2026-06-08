"""Tests for the Stop-hook handoff nudge (dummyindex context memory nudge)."""
from __future__ import annotations

from dummyindex.context.domains.memory.enums import AUTO_BREADCRUMB_TAG, MemoryVerb


def test_new_memory_verbs_exist():
    assert MemoryVerb("nudge") is MemoryVerb.NUDGE
    assert MemoryVerb("breadcrumb") is MemoryVerb.BREADCRUMB


def test_auto_breadcrumb_tag_constant():
    assert AUTO_BREADCRUMB_TAG == "(auto-breadcrumb)"


from datetime import datetime, timezone

from dummyindex.context.domains.memory import nudge as nudge_mod
from dummyindex.usage.models import TurnUsage


def _turn(output_tokens: int) -> TurnUsage:
    return TurnUsage(
        timestamp=datetime(2026, 6, 8, tzinfo=timezone.utc),
        session_id="s",
        project="p",
        model="claude-opus-4-8",
        input_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=output_tokens,
        is_subagent=False,
    )


def test_significant_when_subagents_used():
    assert nudge_mod.is_significant((_turn(10),), subagent_file_count=1) is True


def test_significant_when_output_tokens_over_threshold():
    big = (_turn(nudge_mod.LONG_OUTPUT_TOKENS),)
    assert nudge_mod.is_significant(big, subagent_file_count=0) is True


def test_not_significant_when_small_and_no_subagents():
    small = (_turn(100), _turn(200))
    assert nudge_mod.is_significant(small, subagent_file_count=0) is False


def test_total_main_output_tokens_sums():
    assert nudge_mod.total_main_output_tokens((_turn(100), _turn(250))) == 350
