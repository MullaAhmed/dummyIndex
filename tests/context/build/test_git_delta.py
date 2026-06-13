"""Tests for ``context/build/git_delta.py`` — subprocess git delta detection.

These exercise both the happy path (a real throwaway ``git init`` under
``tmp_path``, never the host repo) and the graceful-degradation contract
(non-git dir / unknown anchor → ``None``, never a raise).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dummyindex.context.build import (
    ChangedPaths,
    changed_paths,
    head_commit,
)
from dummyindex.context.build.git_delta import (
    commit_exists,
    is_ancestor_of_head,
)


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _init_repo(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t.t")
    _git(path, "config", "user.name", "t")


def _commit_all(path: Path, message: str) -> str:
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", message)
    return _git(path, "rev-parse", "HEAD").strip()


# ----- head_commit ----------------------------------------------------------


@pytest.mark.unit
def test_head_commit_returns_sha_in_real_repo(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    sha = _commit_all(tmp_path, "init")
    assert head_commit(tmp_path) == sha


@pytest.mark.unit
def test_head_commit_none_on_non_git_dir(tmp_path: Path) -> None:
    # No `git init` — must degrade, never raise.
    assert head_commit(tmp_path) is None


@pytest.mark.unit
def test_head_commit_none_on_unborn_head(tmp_path: Path) -> None:
    _init_repo(tmp_path)  # no commit yet → HEAD is unborn
    assert head_commit(tmp_path) is None


# ----- changed_paths --------------------------------------------------------


@pytest.mark.unit
def test_changed_paths_none_on_non_git_dir(tmp_path: Path) -> None:
    assert changed_paths(tmp_path, "deadbeef") is None


@pytest.mark.unit
def test_changed_paths_none_on_unknown_anchor(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    # An anchor the repo never saw → git diff exits non-zero → None.
    assert changed_paths(tmp_path, "0123456789abcdef0123456789abcdef01234567") is None


@pytest.mark.unit
def test_changed_paths_none_on_empty_since(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    assert changed_paths(tmp_path, "") is None


@pytest.mark.unit
def test_changed_paths_classifies_committed_changes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "gone.py").write_text("y = 2\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")

    (tmp_path / "keep.py").write_text("x = 99\n", encoding="utf-8")  # modify
    (tmp_path / "gone.py").unlink()  # remove
    (tmp_path / "fresh.py").write_text("z = 3\n", encoding="utf-8")  # add
    _commit_all(tmp_path, "change")

    delta = changed_paths(tmp_path, anchor)
    assert delta is not None
    assert "fresh.py" in delta.added
    assert "keep.py" in delta.modified
    assert "gone.py" in delta.removed


@pytest.mark.unit
def test_changed_paths_includes_uncommitted_worktree_edit(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")

    # Modify but DON'T commit — must still show as modified.
    (tmp_path / "keep.py").write_text("x = 2\n", encoding="utf-8")

    delta = changed_paths(tmp_path, anchor)
    assert delta is not None
    assert "keep.py" in delta.modified


@pytest.mark.unit
def test_changed_paths_includes_untracked_file(tmp_path: Path) -> None:
    # The discriminating case: a never-`git add`ed file. Plain `git diff`
    # would miss it; the `git status --porcelain -uall` leg must catch it.
    _init_repo(tmp_path)
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")

    (tmp_path / "untracked.py").write_text("new = 1\n", encoding="utf-8")

    delta = changed_paths(tmp_path, anchor)
    assert delta is not None
    assert "untracked.py" in delta.added


@pytest.mark.unit
def test_changed_paths_empty_when_clean(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    delta = changed_paths(tmp_path, anchor)
    assert delta == ChangedPaths(added=(), modified=(), removed=())


@pytest.mark.unit
def test_changed_paths_non_ascii_untracked_unescaped(tmp_path: Path) -> None:
    # Discriminating case for WARN 7: git C-escapes bytes >=0x80 under the
    # default `core.quotePath=true` (a non-ASCII name appears as
    # `"caf\303\251.py"`). The fix runs `status` with quotePath=false so the
    # untracked path arrives as raw UTF-8 `café.py`. A space-only name would
    # NOT discriminate — git never escapes spaces — so this uses a non-ASCII
    # char on purpose.
    _init_repo(tmp_path)
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")

    (tmp_path / "café.py").write_text("y = 2\n", encoding="utf-8")

    delta = changed_paths(tmp_path, anchor)
    assert delta is not None
    assert "café.py" in delta.added


@pytest.mark.unit
def test_changed_paths_non_ascii_committed_unescaped(tmp_path: Path) -> None:
    # The diff leg must also disable quotePath so a committed non-ASCII path
    # arrives un-escaped.
    _init_repo(tmp_path)
    (tmp_path / "café.py").write_text("x = 1\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")

    (tmp_path / "café.py").write_text("x = 99\n", encoding="utf-8")  # modify
    _commit_all(tmp_path, "edit")

    delta = changed_paths(tmp_path, anchor)
    assert delta is not None
    assert "café.py" in delta.modified


# ----- commit_exists --------------------------------------------------------


@pytest.mark.unit
def test_commit_exists_true_for_known_sha(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    sha = _commit_all(tmp_path, "init")
    assert commit_exists(tmp_path, sha) is True


@pytest.mark.unit
def test_commit_exists_false_for_unknown_sha(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    # A well-formed but absent sha → reachable repo, object missing → False.
    assert commit_exists(tmp_path, "0123456789abcdef0123456789abcdef01234567") is False


@pytest.mark.unit
def test_commit_exists_none_on_non_git_dir(tmp_path: Path) -> None:
    # No repo at all → cannot tell → None (degrade, never raise).
    assert commit_exists(tmp_path, "deadbeef") is None


@pytest.mark.unit
def test_commit_exists_none_on_empty_sha(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    assert commit_exists(tmp_path, "") is None


# ----- is_ancestor_of_head --------------------------------------------------


@pytest.mark.unit
def test_is_ancestor_true_for_earlier_commit(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    first = _commit_all(tmp_path, "init")
    (tmp_path / "a.py").write_text("x = 2\n", encoding="utf-8")
    _commit_all(tmp_path, "second")
    assert is_ancestor_of_head(tmp_path, first) is True


@pytest.mark.unit
def test_is_ancestor_false_for_divergent_branch_commit(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    # A commit on a side branch that's never merged into HEAD.
    _git(tmp_path, "checkout", "-q", "-b", "side")
    (tmp_path / "b.py").write_text("y = 1\n", encoding="utf-8")
    side = _commit_all(tmp_path, "side work")
    _git(tmp_path, "checkout", "-q", "-")  # back to the default branch
    assert is_ancestor_of_head(tmp_path, side) is False


@pytest.mark.unit
def test_is_ancestor_none_on_unknown_sha(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    # merge-base errors out for an unknown object → None (can't decide).
    assert (
        is_ancestor_of_head(tmp_path, "0123456789abcdef0123456789abcdef01234567")
        is None
    )
