"""Tests for dummyindex.context.incremental — rebuild_changed quick-exit."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dummyindex.context.build.incremental import ChangeSet, rebuild_changed
from dummyindex.context.build.runner import build_all

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def primed_repo(tmp_path: Path) -> Path:
    """Sample repo with .context/ already built once."""
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    build_all(dest, cache_root=tmp_path / "cache")
    return dest


@pytest.mark.integration
def test_first_run_no_existing_context_treats_all_as_added(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    shutil.copytree(_FIXTURE_ROOT, fresh)
    result = rebuild_changed(fresh, cache_root=tmp_path / "cache")
    assert result.skipped is False
    assert result.build_result is not None
    assert len(result.changes.added) >= 1
    assert result.changes.modified == ()
    assert result.changes.removed == ()


@pytest.mark.integration
def test_no_changes_skips(primed_repo: Path, tmp_path: Path) -> None:
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.skipped is True
    assert result.build_result is None
    assert not result.changes.has_changes


@pytest.mark.integration
def test_modified_file_triggers_rebuild(primed_repo: Path, tmp_path: Path) -> None:
    app_py = primed_repo / "app.py"
    app_py.write_text(
        app_py.read_text(encoding="utf-8") + "\n# trivial edit\n",
        encoding="utf-8",
    )
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.skipped is False
    assert "app.py" in result.changes.modified
    assert result.changes.added == ()
    assert result.changes.removed == ()
    assert result.build_result is not None


@pytest.mark.integration
def test_added_file_triggers_rebuild(primed_repo: Path, tmp_path: Path) -> None:
    new_py = primed_repo / "extra.py"
    new_py.write_text("def added() -> int:\n    return 1\n", encoding="utf-8")
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.skipped is False
    assert "extra.py" in result.changes.added


@pytest.mark.integration
def test_removed_file_triggers_rebuild(primed_repo: Path, tmp_path: Path) -> None:
    (primed_repo / "helpers.py").unlink()
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.skipped is False
    assert "helpers.py" in result.changes.removed


@pytest.mark.integration
def test_rebuild_produces_updated_files_json(
    primed_repo: Path, tmp_path: Path
) -> None:
    new_py = primed_repo / "addition.py"
    new_py.write_text("def added() -> int:\n    return 99\n", encoding="utf-8")
    rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    files_json = (primed_repo / ".context" / "map" / "files.json").read_text(
        encoding="utf-8"
    )
    assert "addition.py" in files_json


@pytest.mark.unit
def test_changeset_has_changes_property() -> None:
    empty = ChangeSet(added=(), modified=(), removed=())
    assert empty.has_changes is False
    only_added = ChangeSet(added=("a.py",), modified=(), removed=())
    assert only_added.has_changes is True
    only_modified = ChangeSet(added=(), modified=("b.py",), removed=())
    assert only_modified.has_changes is True
    only_removed = ChangeSet(added=(), modified=(), removed=("c.py",))
    assert only_removed.has_changes is True
