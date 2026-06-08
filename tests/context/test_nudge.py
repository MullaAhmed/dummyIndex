"""Tests for the Stop-hook handoff nudge (dummyindex context memory nudge)."""
from __future__ import annotations

from dummyindex.context.domains.memory.enums import AUTO_BREADCRUMB_TAG, MemoryVerb


def test_new_memory_verbs_exist():
    assert MemoryVerb("nudge") is MemoryVerb.NUDGE
    assert MemoryVerb("breadcrumb") is MemoryVerb.BREADCRUMB


def test_auto_breadcrumb_tag_constant():
    assert AUTO_BREADCRUMB_TAG == "(auto-breadcrumb)"
