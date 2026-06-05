"""Unit tests for the session-memory domain."""
from __future__ import annotations

import pytest

from dummyindex.context.domains.memory import (
    MemoryTier,
    ensure_memory_store,
    memory_dir,
)
from dummyindex.context.domains.memory._parse import (
    render,
    section_date,
    split_sections,
)
from dummyindex.context.domains.memory.models import Section

pytestmark = pytest.mark.unit


def _ctx(tmp_path):
    return tmp_path / ".context"


def test_ensure_memory_store_creates_all_tiers(tmp_path):
    created = ensure_memory_store(_ctx(tmp_path))
    assert set(created) == {t.value for t in MemoryTier}
    mdir = memory_dir(_ctx(tmp_path))
    assert (mdir / "now.md").read_text(encoding="utf-8").startswith("# Now")
    assert (mdir / "core-memories.md").read_text(encoding="utf-8").startswith("# Core memories")


def test_ensure_memory_store_is_non_destructive(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    (memory_dir(ctx) / "now.md").write_text(
        "# Now\n\n## 2026-06-05 10:00 | main\nkeep me\n", encoding="utf-8"
    )
    created = ensure_memory_store(ctx)
    assert created == ()
    assert "keep me" in (memory_dir(ctx) / "now.md").read_text(encoding="utf-8")


def test_split_sections_separates_preamble_and_sections():
    text = "# Now\n\n## 2026-06-05 10:00 | main\nbody one\n\n## 2026-06-04 09:00 | dev\nbody two\n"
    pre, secs = split_sections(text)
    assert pre == "# Now"
    assert len(secs) == 2
    assert secs[0].heading == "## 2026-06-05 10:00 | main"
    assert "body one" in secs[0].body


def test_section_date_extracts_iso_date():
    assert section_date("## 2026-06-05 10:00 | main") == "2026-06-05"
    assert section_date("## no date here") is None


def test_render_roundtrips_sections():
    text = "# Recent\n\n## 2026-06-05\nalpha\n"
    pre, secs = split_sections(text)
    out = render(pre, secs)
    assert "# Recent" in out and "## 2026-06-05" in out and "alpha" in out
