"""Tests for the PreCompact deterministic breadcrumb."""
from __future__ import annotations

from datetime import datetime, timezone

from dummyindex.context.domains.memory import breadcrumb as bc
from dummyindex.context.domains.memory.enums import AUTO_BREADCRUMB_TAG


def _facts(**kw) -> bc.BreadcrumbFacts:
    base = dict(
        branch="main",
        files_changed=2,
        insertions=10,
        deletions=3,
        changed_files=("a.py", "b.py"),
        main_turns=12,
        subagents=1,
    )
    base.update(kw)
    return bc.BreadcrumbFacts(**base)


def test_render_entry_heading_is_tagged():
    now = datetime(2026, 6, 8, 14, 5, tzinfo=timezone.utc)
    section = bc.render_entry(_facts(), now)
    assert section.heading == f"## 2026-06-08 14:05 | main {AUTO_BREADCRUMB_TAG}"
    assert "2 files changed (+10/-3)" in section.body
    assert "subagents: 1" in section.body
    assert "a.py, b.py" in section.body


def test_render_entry_caps_file_list():
    files = tuple(f"f{i}.py" for i in range(12))
    section = bc.render_entry(_facts(changed_files=files, files_changed=12), now=datetime(2026, 6, 8, tzinfo=timezone.utc))
    assert "+4 more" in section.body  # 12 files, cap 8 → 4 more
    assert "f8.py" not in section.body


def test_render_entry_no_changes():
    section = bc.render_entry(
        _facts(changed_files=(), files_changed=0, insertions=0, deletions=0),
        now=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )
    assert "(no tracked changes)" in section.body
