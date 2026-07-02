"""Tests for the cross-cutting git-fact seam in ``context/git.py``.

The seam exposes three functions with two distinct I/O boundaries, so the
markers split accordingly (``--strict-markers`` is on, no implicit default):

- ``is_git_repo`` is a pure-filesystem probe (re-exported from
  ``pipeline/io/git.py``), so its happy/sad cases are built as on-disk shapes
  under ``tmp_path`` — ``@pytest.mark.unit`` — mirroring
  ``tests/pipeline/io/test_git.py``.
- ``is_tracked`` / ``run_git`` *are* the git-subprocess boundary; they can only
  be exercised against a real ``git`` (a throwaway ``git init`` under
  ``tmp_path``, never the host repo), so those are ``@pytest.mark.integration``.
  The one ``is_tracked`` path that never shells out (a path outside ``root``) is
  a pure-logic ``@pytest.mark.unit``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dummyindex.context.git import is_git_repo, is_tracked, run_git


def _git(path: Path, *args: str) -> str:
    """Run a real ``git`` command in ``path`` (test setup only)."""
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _init_repo(path: Path) -> None:
    """A throwaway repo with local identity config (never the host repo)."""
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t.t")
    _git(path, "config", "user.name", "t")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ----- is_git_repo (pure filesystem) ----------------------------------------


@pytest.mark.unit
def test_is_git_repo_true_for_dot_git_dir(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert is_git_repo(tmp_path) is True


@pytest.mark.unit
def test_is_git_repo_false_for_plain_dir(tmp_path: Path) -> None:
    assert is_git_repo(tmp_path) is False


@pytest.mark.unit
def test_is_git_repo_true_for_submodule_git_file(tmp_path: Path) -> None:
    # A submodule / worktree carries a ``.git`` *file* with a gitdir pointer;
    # the seam must recognise it (it reuses the pipeline filesystem probe).
    _write(tmp_path / ".git", "gitdir: ../.git/modules/backend\n")
    assert is_git_repo(tmp_path) is True


@pytest.mark.integration
def test_is_git_repo_true_after_real_git_init(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert is_git_repo(tmp_path) is True


# ----- is_tracked (git subprocess) ------------------------------------------


@pytest.mark.integration
def test_is_tracked_true_for_tracked_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    tracked = tmp_path / "a.py"
    tracked.write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "a.py")

    assert is_tracked(tmp_path, tracked) is True


@pytest.mark.integration
def test_is_tracked_false_for_untracked_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    untracked = tmp_path / "b.py"
    untracked.write_text("y = 2\n", encoding="utf-8")  # written but never `git add`ed

    assert is_tracked(tmp_path, untracked) is False


@pytest.mark.integration
def test_is_tracked_true_when_not_a_git_repo(tmp_path: Path) -> None:
    # Documented degradation: outside a git repo, a file is reported tracked so
    # an off-git path is never refused as "untracked". This branch still issues
    # the ls-files subprocess (git errors), hence integration.
    stray = tmp_path / "c.py"
    stray.write_text("z = 3\n", encoding="utf-8")
    assert is_git_repo(tmp_path) is False

    assert is_tracked(tmp_path, stray) is True


@pytest.mark.unit
def test_is_tracked_true_for_path_outside_root(tmp_path: Path) -> None:
    # ``root`` is a real repo, but the queried path lives outside it: ``git -C
    # root`` can't address it, so it degrades to True without shelling out.
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "d.py"
    _write(outside, "w = 4\n")

    assert is_tracked(root, outside) is True


# ----- run_git (git subprocess) ---------------------------------------------


@pytest.mark.integration
def test_run_git_returns_completed_process(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    result = run_git(tmp_path, "rev-parse", "--is-inside-work-tree")

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0
    assert result.stdout.strip() == "true"


@pytest.mark.integration
def test_run_git_runs_in_the_given_root(tmp_path: Path) -> None:
    # Two sibling dirs: only one is a repo. ``run_git`` must target the root it
    # is handed (``-C <root>``), so the repo answers 0 and the plain dir does
    # not — proving the call isn't keyed off the process cwd.
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plain = tmp_path / "plain"
    plain.mkdir()

    assert run_git(repo, "rev-parse", "--git-dir").returncode == 0
    assert run_git(plain, "rev-parse", "--git-dir").returncode != 0


@pytest.mark.integration
def test_run_git_does_not_raise_on_nonzero_exit(tmp_path: Path) -> None:
    # No ``check=True``: a failing git command returns a CompletedProcess with a
    # non-zero returncode, it does not raise CalledProcessError.
    _init_repo(tmp_path)
    result = run_git(tmp_path, "rev-parse", "no-such-ref")

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode != 0
