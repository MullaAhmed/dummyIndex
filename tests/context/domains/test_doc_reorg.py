"""Tests for the gated in-place doc reorg safety net (`context doc-reorg`)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.doc_reorg import (
    BackupError,
    DirtyTreeError,
    backup_docs,
    discover_doc_files,
    git_is_clean,
    require_clean_tree,
    restore_backup,
)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(path), check=True, capture_output=True)


def _init_clean_repo(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t.t")
    _git(path, "config", "user.name", "t")
    (path / "README.md").write_text("# Project\noriginal readme\n", encoding="utf-8")
    (path / "docs").mkdir()
    (path / "docs" / "guide.md").write_text("# Guide\noriginal guide\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")


# ----- discovery ------------------------------------------------------------


@pytest.mark.unit
def test_discovery_finds_repo_docs(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "docs" / "logo.png").write_bytes(b"\x89PNG")  # binary: ignored

    rels = {p.relative_to(tmp_path).as_posix() for p in discover_doc_files(tmp_path)}
    assert "README.md" in rels
    assert "docs/a.md" in rels
    assert "docs/logo.png" not in rels  # only rewritable text formats


# ----- guard ----------------------------------------------------------------


@pytest.mark.integration
def test_guard_clean_then_dirty(tmp_path: Path) -> None:
    _init_clean_repo(tmp_path)
    assert git_is_clean(tmp_path) is True
    require_clean_tree(tmp_path)  # no raise

    (tmp_path / "README.md").write_text("edited\n", encoding="utf-8")
    assert git_is_clean(tmp_path) is False
    with pytest.raises(DirtyTreeError):
        require_clean_tree(tmp_path)


@pytest.mark.integration
def test_guard_dirty_overridable(tmp_path: Path) -> None:
    _init_clean_repo(tmp_path)
    (tmp_path / "README.md").write_text("edited\n", encoding="utf-8")
    require_clean_tree(tmp_path, allow_dirty=True)  # no raise


@pytest.mark.unit
def test_require_clean_tree_refuses_non_git(tmp_path: Path) -> None:
    with pytest.raises(DirtyTreeError):
        require_clean_tree(tmp_path)  # not a git repo → unknown → refuse


# ----- backup / restore round trip ------------------------------------------


@pytest.mark.integration
def test_backup_modify_restore_round_trip(tmp_path: Path) -> None:
    _init_clean_repo(tmp_path)
    files = discover_doc_files(tmp_path)
    backup = backup_docs(tmp_path, files, timestamp="snap1")

    assert "README.md" in backup.files
    assert "docs/guide.md" in backup.files
    assert Path(backup.backup_dir).is_dir()

    # Simulate a reorg: overwrite README, delete the guide.
    (tmp_path / "README.md").write_text("REWRITTEN\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").unlink()

    result = restore_backup(tmp_path, Path(backup.backup_dir))

    assert (tmp_path / "README.md").read_text() == "# Project\noriginal readme\n"
    assert (tmp_path / "docs" / "guide.md").read_text() == "# Guide\noriginal guide\n"
    assert set(result.restored) == {"README.md", "docs/guide.md"}


@pytest.mark.integration
def test_restore_reports_created_files_without_deleting(tmp_path: Path) -> None:
    """The advisor's case: a reorg that *creates* a doc. Restore must report it
    in created_since and must NOT delete it (git clean is the user's call)."""
    _init_clean_repo(tmp_path)
    backup = backup_docs(tmp_path, discover_doc_files(tmp_path), timestamp="snap2")

    # Reorg splits content into a new file.
    (tmp_path / "docs" / "new_section.md").write_text("split out\n", encoding="utf-8")

    result = restore_backup(tmp_path, Path(backup.backup_dir))

    assert "docs/new_section.md" in result.created_since
    assert (tmp_path / "docs" / "new_section.md").is_file()  # not deleted


@pytest.mark.integration
def test_restore_rejects_path_traversal_manifest(tmp_path: Path) -> None:
    """A tampered/foreign manifest with a `../` entry must be refused, not
    allowed to write outside the repo."""
    _init_clean_repo(tmp_path)
    backup = backup_docs(tmp_path, discover_doc_files(tmp_path), timestamp="evil")
    bdir = Path(backup.backup_dir)
    (bdir / "manifest.json").write_text(
        json.dumps({"files": ["../../escape.md"]}), encoding="utf-8"
    )

    with pytest.raises(BackupError):
        restore_backup(tmp_path, bdir)
    assert not (tmp_path.parent.parent / "escape.md").exists()  # nothing escaped


@pytest.mark.integration
def test_restore_reports_skipped_when_backup_copy_missing(tmp_path: Path) -> None:
    """A manifest entry whose backup copy is gone is reported in `skipped`,
    so a short restore never reads as complete."""
    _init_clean_repo(tmp_path)
    backup = backup_docs(tmp_path, discover_doc_files(tmp_path), timestamp="partial")
    bdir = Path(backup.backup_dir)
    (bdir / "docs" / "guide.md").unlink()  # simulate a partial backup

    result = restore_backup(tmp_path, bdir)
    assert "docs/guide.md" in result.skipped
    assert "README.md" in result.restored


@pytest.mark.integration
def test_backup_dir_is_gitignored(tmp_path: Path) -> None:
    _init_clean_repo(tmp_path)
    backup_docs(tmp_path, discover_doc_files(tmp_path), timestamp="snap3")
    gitignore = (tmp_path / ".context" / ".gitignore").read_text(encoding="utf-8")
    assert "_doc_backups/" in gitignore


# ----- CLI ------------------------------------------------------------------


@pytest.mark.integration
def test_cli_guard_exit_codes(tmp_path: Path) -> None:
    _init_clean_repo(tmp_path)
    assert dispatch(["doc-reorg", "guard", str(tmp_path)]) == 0
    (tmp_path / "README.md").write_text("dirty\n", encoding="utf-8")
    assert dispatch(["doc-reorg", "guard", str(tmp_path)]) == 1


@pytest.mark.unit
def test_cli_guard_unknown_state_exits_1(tmp_path: Path) -> None:
    # Not a git repo → status unknown. The guard now routes through
    # require_clean_tree (single source of truth), which refuses on unknown
    # state, so the CLI must still exit 1 rather than treat it as clean.
    assert dispatch(["doc-reorg", "guard", str(tmp_path)]) == 1


@pytest.mark.integration
def test_cli_list_and_backup_and_restore(tmp_path: Path, capsys) -> None:
    _init_clean_repo(tmp_path)

    assert dispatch(["doc-reorg", "list", str(tmp_path), "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert "README.md" in listed

    assert dispatch(["doc-reorg", "backup", str(tmp_path), "--json"]) == 0
    backup = json.loads(capsys.readouterr().out)
    backup_dir = backup["backup_dir"]

    (tmp_path / "README.md").write_text("changed\n", encoding="utf-8")
    assert dispatch(["doc-reorg", "restore", str(tmp_path), "--from", backup_dir]) == 0
    assert (tmp_path / "README.md").read_text() == "# Project\noriginal readme\n"


@pytest.mark.unit
def test_cli_unknown_action_and_missing_from(tmp_path: Path) -> None:
    assert dispatch(["doc-reorg", "nope", str(tmp_path)]) == 2
    assert dispatch(["doc-reorg", "restore", str(tmp_path)]) == 2  # no --from
