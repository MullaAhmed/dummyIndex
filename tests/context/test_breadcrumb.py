"""Tests for the PreCompact deterministic breadcrumb."""
from __future__ import annotations

import io
import subprocess
from datetime import datetime
from pathlib import Path

from dummyindex.cli import dispatch
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
    now = datetime(2026, 6, 8, 14, 5)
    section = bc.render_entry(_facts(), now)
    assert section.heading == f"## 2026-06-08 14:05 | main {AUTO_BREADCRUMB_TAG}"
    assert "2 files changed (+10/-3)" in section.body
    assert "subagents: 1" in section.body
    assert "a.py, b.py" in section.body


def test_render_entry_caps_file_list():
    files = tuple(f"f{i}.py" for i in range(12))
    section = bc.render_entry(_facts(changed_files=files, files_changed=12), now=datetime(2026, 6, 8))
    assert "+4 more" in section.body  # 12 files, cap 8 → 4 more
    assert "f8.py" not in section.body


def test_render_entry_no_changes():
    section = bc.render_entry(
        _facts(changed_files=(), files_changed=0, insertions=0, deletions=0),
        now=datetime(2026, 6, 8),
    )
    assert "(no tracked changes)" in section.body


def _read_now(ctx: Path) -> str:
    return (ctx / "session-memory" / "now.md").read_text(encoding="utf-8")


def _seed_now(ctx: Path, body: str) -> None:
    mdir = ctx / "session-memory"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "now.md").write_text(body, encoding="utf-8")


def test_write_breadcrumb_prepends_to_now(tmp_path: Path):
    ctx = tmp_path / ".context"
    _seed_now(ctx, "# Now\n\n## 2026-06-07 09:00 | main\nReal handoff.\n")
    now = datetime(2026, 6, 8, 14, 5)
    bc.write_breadcrumb(ctx, _facts(), now)
    text = _read_now(ctx)
    assert text.startswith("# Now")
    # Breadcrumb is newest (top), the real handoff is preserved below it.
    bc_idx = text.index(AUTO_BREADCRUMB_TAG)
    real_idx = text.index("Real handoff.")
    assert bc_idx < real_idx


def test_write_breadcrumb_replaces_existing_breadcrumb(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 5)
    _seed_now(ctx, "# Now\n")
    bc.write_breadcrumb(ctx, _facts(files_changed=1), now)
    bc.write_breadcrumb(ctx, _facts(files_changed=9), now)
    text = _read_now(ctx)
    # Only one breadcrumb section; the second call updated in place.
    assert text.count(AUTO_BREADCRUMB_TAG) == 1
    assert "9 files changed" in text
    assert "1 files changed" not in text


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def test_gather_facts_reads_branch_and_diff(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "x.py").write_text("a = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "x.py")
    _git(tmp_path, "commit", "-qm", "init")
    (tmp_path / "x.py").write_text("a = 1\nb = 2\n", encoding="utf-8")

    facts = bc.build_breadcrumb_facts(tmp_path, main_transcript=None)
    assert facts.files_changed == 1
    assert facts.insertions == 1
    assert "x.py" in facts.changed_files
    assert facts.main_turns == 0  # no transcript


def test_gather_facts_survives_non_git_dir(tmp_path: Path):
    facts = bc.build_breadcrumb_facts(tmp_path, main_transcript=None)
    assert facts.branch == "unknown"
    assert facts.files_changed == 0
    assert facts.changed_files == ()


def test_run_breadcrumb_writes_breadcrumb(tmp_path: Path):
    """run_breadcrumb ensures store and writes a breadcrumb."""
    _git(tmp_path, "init", "-q")
    now = datetime(2026, 6, 8, 14, 5)
    result = bc.run_breadcrumb(root=tmp_path, main_transcript=None, now=now)
    assert result is True
    text = (tmp_path / ".context" / "session-memory" / "now.md").read_text()
    assert AUTO_BREADCRUMB_TAG in text


def test_run_breadcrumb_silent_with_remember_plugin(tmp_path: Path):
    """run_breadcrumb returns False and writes nothing when .remember/ exists."""
    (tmp_path / ".remember").mkdir()
    now = datetime(2026, 6, 8, 14, 5)
    result = bc.run_breadcrumb(root=tmp_path, main_transcript=None, now=now)
    assert result is False
    assert not (tmp_path / ".context" / "session-memory").exists()


def test_cli_breadcrumb_writes_now(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id": "abc"}'))

    rc = dispatch(["memory", "breadcrumb"])
    assert rc == 0
    text = (tmp_path / ".context" / "session-memory" / "now.md").read_text()
    assert AUTO_BREADCRUMB_TAG in text


def test_cli_breadcrumb_silent_with_remember_plugin(tmp_path, monkeypatch):
    (tmp_path / ".remember").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id": "abc"}'))

    rc = dispatch(["memory", "breadcrumb"])
    assert rc == 0
    assert not (tmp_path / ".context" / "session-memory").exists()
