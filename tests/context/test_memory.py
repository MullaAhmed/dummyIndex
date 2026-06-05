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


from dummyindex.context.domains.memory.detect import remember_plugin_present


def test_remember_plugin_detection(tmp_path):
    assert remember_plugin_present(tmp_path) is False
    (tmp_path / ".remember").mkdir()
    assert remember_plugin_present(tmp_path) is True


from datetime import date

from dummyindex.context.domains.memory import roll_tiers


def test_roll_moves_old_now_entries_to_recent(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "now.md").write_text(
        "# Now\n\n## 2026-06-05 14:00 | main\ntoday work\n\n"
        "## 2026-06-03 09:00 | main\nold work\n",
        encoding="utf-8",
    )
    report = roll_tiers(ctx, today=date(2026, 6, 5))
    assert report.now_to_recent == 1
    now_txt = (mdir / "now.md").read_text(encoding="utf-8")
    recent_txt = (mdir / "recent.md").read_text(encoding="utf-8")
    assert "today work" in now_txt and "old work" not in now_txt
    assert "old work" in recent_txt
    assert "2026-06-03" in report.moved_dates


def test_roll_is_idempotent(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "now.md").write_text(
        "# Now\n\n## 2026-06-03 09:00 | main\nold work\n", encoding="utf-8"
    )
    roll_tiers(ctx, today=date(2026, 6, 5))
    now_snap = (mdir / "now.md").read_text(encoding="utf-8")
    recent_snap = (mdir / "recent.md").read_text(encoding="utf-8")
    report2 = roll_tiers(ctx, today=date(2026, 6, 5))
    assert report2.now_to_recent == 0 and report2.recent_to_archive == 0
    assert (mdir / "now.md").read_text(encoding="utf-8") == now_snap
    assert (mdir / "recent.md").read_text(encoding="utf-8") == recent_snap


def test_roll_moves_stale_recent_to_archive(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "recent.md").write_text(
        "# Recent\n\n## 2026-05-01\nway old\n", encoding="utf-8"
    )
    report = roll_tiers(ctx, today=date(2026, 6, 5), recent_keep_days=7)
    assert report.recent_to_archive == 1
    assert "way old" in (mdir / "archive.md").read_text(encoding="utf-8")
    assert "way old" not in (mdir / "recent.md").read_text(encoding="utf-8")


def test_roll_keeps_undated_sections_in_place(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "now.md").write_text(
        "# Now\n\n## scratch note\nno date\n", encoding="utf-8"
    )
    report = roll_tiers(ctx, today=date(2026, 6, 5))
    assert report.now_to_recent == 0
    assert "no date" in (mdir / "now.md").read_text(encoding="utf-8")
