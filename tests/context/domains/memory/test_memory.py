"""Unit tests for the session-memory domain."""
from __future__ import annotations

from datetime import date

import pytest

from dummyindex.context.domains.memory import (
    MemoryTier,
    Section,
    ensure_memory_store,
    memory_dir,
    remember_plugin_present,
    render_session_start,
    roll_tiers,
)
from dummyindex.context.domains.memory.parse import (
    render,
    read_text_or_empty,
    section_date,
    split_sections,
)

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
    for tier in MemoryTier:
        assert (memory_dir(ctx) / tier.value).exists()


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
    assert out == text


def test_remember_plugin_detection(tmp_path):
    assert remember_plugin_present(tmp_path) is False
    (tmp_path / ".remember").mkdir()
    assert remember_plugin_present(tmp_path) is True


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


def _seed_now(tmp_path, body):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    (memory_dir(ctx) / "now.md").write_text(
        f"# Now\n\n## 2026-06-05 10:00 | main\n{body}\n", encoding="utf-8"
    )


def test_session_start_none_when_no_store(tmp_path):
    assert render_session_start(tmp_path) is None


def test_session_start_none_when_store_empty(tmp_path):
    ensure_memory_store(_ctx(tmp_path))
    assert render_session_start(tmp_path) is None


def test_session_start_none_when_remember_present(tmp_path):
    _seed_now(tmp_path, "did stuff")
    (tmp_path / ".remember").mkdir()
    assert render_session_start(tmp_path) is None


def test_session_start_emits_block(tmp_path):
    _seed_now(tmp_path, "did stuff")
    block = render_session_start(tmp_path)
    assert block is not None
    assert "=== HANDOFF ===" in block
    assert "=== MEMORY ===" in block
    assert "/dummyindex-remember" in block
    assert "did stuff" in block


def test_session_start_truncates(tmp_path):
    _seed_now(tmp_path, "x" * 9000)
    block = render_session_start(tmp_path, max_chars=500)
    assert len(block) <= 520
    assert "truncated" in block


def test_roll_cascades_very_old_now_to_archive(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "now.md").write_text(
        "# Now\n\n## 2026-05-01 09:00 | main\nancient work\n", encoding="utf-8"
    )
    report = roll_tiers(ctx, today=date(2026, 6, 5), recent_keep_days=7)
    assert report.now_to_recent == 1
    assert report.recent_to_archive == 1
    assert "ancient work" in (mdir / "archive.md").read_text(encoding="utf-8")
    assert "ancient work" not in (mdir / "now.md").read_text(encoding="utf-8")
    assert "ancient work" not in (mdir / "recent.md").read_text(encoding="utf-8")


def test_session_start_truncation_keeps_handoff_marker(tmp_path):
    _seed_now(tmp_path, "y" * 9000)
    block = render_session_start(tmp_path, max_chars=120)
    assert block is not None
    assert "=== HANDOFF ===" in block


def test_session_start_includes_recent_and_core(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "recent.md").write_text("# Recent\n\n## 2026-06-01\nrecent stuff\n", encoding="utf-8")
    (mdir / "core-memories.md").write_text("# Core memories\n\n- a durable fact\n", encoding="utf-8")
    block = render_session_start(tmp_path)
    assert block is not None
    assert "recent.md (head)" in block and "recent stuff" in block
    assert "core-memories.md" in block and "a durable fact" in block


def test_roll_preserves_undated_section_during_rewrite(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "now.md").write_text(
        "# Now\n\n## scratch note\nundated keep\n\n## 2026-06-03 09:00 | main\nold dated\n",
        encoding="utf-8",
    )
    report = roll_tiers(ctx, today=date(2026, 6, 5))
    assert report.now_to_recent == 1
    now_txt = (mdir / "now.md").read_text(encoding="utf-8")
    assert "undated keep" in now_txt
    assert "old dated" not in now_txt
