"""Tests for the pure-filesystem git-dir helpers in ``pipeline/io/git.py``.

These cover the cases dummyindex's old ``(.git).is_dir()`` checks missed:
git submodules and worktrees, whose ``.git`` is a regular *file* carrying a
``gitdir:`` pointer rather than a directory. No subprocess / real ``git`` —
the helpers are deterministic filesystem parsers and the tests build the
on-disk shapes by hand under ``tmp_path``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.pipeline.io import is_git_repo, resolve_git_dir, submodule_paths

# Not yet re-exported from dummyindex.pipeline.io — the package __init__ is
# owned by a concurrent change; promote this import when the re-export lands.
from dummyindex.pipeline.io.git import superproject_root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ----- is_git_repo ----------------------------------------------------------


@pytest.mark.unit
def test_plain_directory_is_a_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert is_git_repo(tmp_path) is True


@pytest.mark.unit
def test_submodule_git_file_is_a_repo(tmp_path: Path) -> None:
    # A submodule's `.git` is a file pointing at the superproject's module dir.
    _write(tmp_path / ".git", "gitdir: ../.git/modules/backend\n")
    assert is_git_repo(tmp_path) is True


@pytest.mark.unit
def test_worktree_git_file_is_a_repo(tmp_path: Path) -> None:
    _write(tmp_path / ".git", "gitdir: /home/me/proj/.git/worktrees/feature\n")
    assert is_git_repo(tmp_path) is True


@pytest.mark.unit
def test_missing_git_is_not_a_repo(tmp_path: Path) -> None:
    assert is_git_repo(tmp_path) is False


@pytest.mark.unit
def test_empty_git_file_is_not_a_repo(tmp_path: Path) -> None:
    _write(tmp_path / ".git", "")
    assert is_git_repo(tmp_path) is False


@pytest.mark.unit
def test_git_file_without_gitdir_prefix_is_not_a_repo(tmp_path: Path) -> None:
    _write(tmp_path / ".git", "not a pointer at all\n")
    assert is_git_repo(tmp_path) is False


# ----- resolve_git_dir ------------------------------------------------------


@pytest.mark.unit
def test_resolve_plain_directory(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert resolve_git_dir(tmp_path) == (tmp_path / ".git").resolve()


@pytest.mark.unit
def test_resolve_relative_gitdir_pointer(tmp_path: Path) -> None:
    # Submodule layout: superproject/.git/modules/backend is the real git dir.
    superproject = tmp_path
    module_dir = superproject / ".git" / "modules" / "backend"
    module_dir.mkdir(parents=True)
    submodule = superproject / "backend"
    submodule.mkdir()
    _write(submodule / ".git", "gitdir: ../.git/modules/backend\n")

    assert resolve_git_dir(submodule) == module_dir.resolve()


@pytest.mark.unit
def test_resolve_absolute_gitdir_pointer(tmp_path: Path) -> None:
    real = tmp_path / "elsewhere" / "gitdir"
    real.mkdir(parents=True)
    root = tmp_path / "checkout"
    root.mkdir()
    _write(root / ".git", f"gitdir: {real}\n")

    assert resolve_git_dir(root) == real.resolve()


@pytest.mark.unit
def test_resolve_worktree_follows_commondir(tmp_path: Path) -> None:
    # Worktree: `.git` file -> .git/worktrees/<name>, whose `commondir`
    # points back at the common dir where hooks/ and config live.
    common = tmp_path / "proj" / ".git"
    worktree_meta = common / "worktrees" / "feature"
    worktree_meta.mkdir(parents=True)
    _write(worktree_meta / "commondir", "../..\n")
    checkout = tmp_path / "feature-checkout"
    checkout.mkdir()
    _write(checkout / ".git", f"gitdir: {worktree_meta}\n")

    # Should resolve through commondir to the common git dir, not the
    # per-worktree metadata dir — that's where hooks/ live.
    assert resolve_git_dir(checkout) == common.resolve()


@pytest.mark.unit
def test_resolve_worktree_without_commondir_returns_gitdir(tmp_path: Path) -> None:
    worktree_meta = tmp_path / "proj" / ".git" / "worktrees" / "feature"
    worktree_meta.mkdir(parents=True)
    checkout = tmp_path / "feature-checkout"
    checkout.mkdir()
    _write(checkout / ".git", f"gitdir: {worktree_meta}\n")

    assert resolve_git_dir(checkout) == worktree_meta.resolve()


@pytest.mark.unit
def test_resolve_missing_git_returns_none(tmp_path: Path) -> None:
    assert resolve_git_dir(tmp_path) is None


@pytest.mark.unit
def test_resolve_empty_git_file_returns_none(tmp_path: Path) -> None:
    _write(tmp_path / ".git", "")
    assert resolve_git_dir(tmp_path) is None


@pytest.mark.unit
def test_resolve_malformed_git_file_returns_none(tmp_path: Path) -> None:
    _write(tmp_path / ".git", "garbage with no pointer\n")
    assert resolve_git_dir(tmp_path) is None


@pytest.mark.unit
def test_resolve_gitdir_with_no_path_returns_none(tmp_path: Path) -> None:
    # `gitdir:` prefix present but empty payload — a repo by the prefix
    # rule, but there's nothing to resolve.
    _write(tmp_path / ".git", "gitdir:   \n")
    assert is_git_repo(tmp_path) is True
    assert resolve_git_dir(tmp_path) is None


@pytest.mark.unit
def test_resolve_tolerates_trailing_whitespace(tmp_path: Path) -> None:
    real = tmp_path / "gitdir"
    real.mkdir()
    root = tmp_path / "checkout"
    root.mkdir()
    _write(root / ".git", f"gitdir: {real}   \n\n")
    assert resolve_git_dir(root) == real.resolve()


# ----- submodule_paths ------------------------------------------------------


@pytest.mark.unit
def test_submodule_paths_absent_gitmodules(tmp_path: Path) -> None:
    assert submodule_paths(tmp_path) == ()


@pytest.mark.unit
def test_submodule_paths_parses_declared_paths(tmp_path: Path) -> None:
    _write(
        tmp_path / ".gitmodules",
        '[submodule "frontend"]\n'
        "\tpath = frontend\n"
        "\turl = git@example.com:fe.git\n"
        '[submodule "backend"]\n'
        "\tpath = backend\n"
        "\turl = git@example.com:be.git\n",
    )
    assert submodule_paths(tmp_path) == (
        (tmp_path / "frontend").resolve(),
        (tmp_path / "backend").resolve(),
    )


@pytest.mark.unit
def test_submodule_paths_resolves_nested_path(tmp_path: Path) -> None:
    _write(
        tmp_path / ".gitmodules",
        '[submodule "vendor/lib"]\n\tpath = vendor/lib\n',
    )
    assert submodule_paths(tmp_path) == ((tmp_path / "vendor" / "lib").resolve(),)


@pytest.mark.unit
def test_submodule_paths_skips_section_without_path(tmp_path: Path) -> None:
    _write(
        tmp_path / ".gitmodules",
        '[submodule "x"]\n\turl = git@example.com:x.git\n',
    )
    assert submodule_paths(tmp_path) == ()


@pytest.mark.unit
def test_submodule_paths_malformed_returns_empty(tmp_path: Path) -> None:
    # No section header → MissingSectionHeaderError (a configparser.Error).
    _write(tmp_path / ".gitmodules", "this is not : valid [ ini\n")
    assert submodule_paths(tmp_path) == ()


# ----- superproject_root ------------------------------------------------------


def _make_superproject(tmp_path: Path, submodule_rel: str) -> tuple[Path, Path]:
    """A superproject declaring one submodule at ``submodule_rel``."""
    parent = tmp_path / "mono"
    (parent / ".git").mkdir(parents=True)
    _write(
        parent / ".gitmodules",
        f'[submodule "{submodule_rel}"]\n'
        f"\tpath = {submodule_rel}\n"
        "\turl = git@example.com:sub.git\n",
    )
    sub = parent / submodule_rel
    sub.mkdir(parents=True)
    _write(sub / ".git", "gitdir: ../.git/modules/sub\n")
    return parent, sub


@pytest.mark.unit
def test_superproject_root_finds_declaring_parent(tmp_path: Path) -> None:
    parent, sub = _make_superproject(tmp_path, "frontend")
    assert superproject_root(sub) == parent.resolve()


@pytest.mark.unit
def test_superproject_root_walks_past_non_repo_dirs(tmp_path: Path) -> None:
    # Submodule nested below an intermediate non-repo directory.
    parent, sub = _make_superproject(tmp_path, "apps/frontend")
    assert superproject_root(sub) == parent.resolve()


@pytest.mark.unit
def test_superproject_root_plain_repo_returns_none(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    assert superproject_root(repo) is None


@pytest.mark.unit
def test_superproject_root_undeclared_nested_repo_returns_none(tmp_path: Path) -> None:
    # An enclosing repo that does NOT declare the nested checkout in its
    # .gitmodules is not its superproject — just a plain nested repo.
    parent, _ = _make_superproject(tmp_path, "frontend")
    nested = parent / "vendor" / "lib"
    nested.mkdir(parents=True)
    (nested / ".git").mkdir()
    assert superproject_root(nested) is None


@pytest.mark.unit
def test_superproject_root_ignores_escaping_gitmodules_path(tmp_path: Path) -> None:
    # A .gitmodules entry escaping the superproject (`path = ../escapee`)
    # must not make a non-ancestor claim the sibling checkout.
    parent = tmp_path / "mono"
    (parent / ".git").mkdir(parents=True)
    _write(
        parent / ".gitmodules",
        '[submodule "escapee"]\n\tpath = ../escapee\n\turl = x\n',
    )
    escapee = tmp_path / "escapee"
    escapee.mkdir()
    _write(escapee / ".git", "gitdir: somewhere\n")
    assert superproject_root(escapee) is None
