"""Single cross-cutting git-fact helper for the ``context`` engine.

Exposed once so no domain reaches into another's private ``_is_tracked`` /
``_is_git_repo``. Callers branch on :func:`is_git_repo` first (subprocess-free;
off-git they fall back to plain filesystem moves), then use :func:`is_tracked`
or :func:`run_git`. It sits in ``context/``, not a domain, because the need is
shared across domains.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..pipeline.io import is_git_repo as _fs_is_git_repo

__all__ = ["is_git_repo", "is_tracked", "run_git"]


def is_git_repo(root: Path) -> bool:
    """True when ``root`` is a git working tree — pure filesystem, no subprocess.

    Re-export of ``pipeline/io/git.py:is_git_repo``: accepts a ``.git`` directory
    or a ``.git`` file with a ``gitdir:`` pointer (submodule / worktree).
    """
    return _fs_is_git_repo(root)


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``git -C <root> <args>`` and return the ``CompletedProcess``.

    Like ``build/git_delta.py:_run_git`` but returns the whole result so callers
    of ``git mv`` / ``git add`` can read ``returncode``. No ``check=True``: a
    non-zero exit is a value, never a raise. Callers must gate on
    :func:`is_git_repo` first; with no ``git`` on ``PATH`` this raises
    ``FileNotFoundError``.
    """
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        # Force UTF-8 so non-ASCII paths decode on any host locale (C/POSIX
        # containers would otherwise raise).
        encoding="utf-8",
        errors="replace",
    )


def is_tracked(root: Path, path: Path) -> bool:
    """Whether ``path`` is tracked by git in the repo rooted at ``root``.

    Runs ``git ls-files --error-unmatch <rel>`` (exit 0 = tracked); a relative
    ``path`` is taken against ``root``. Returns ``True`` for a path outside
    ``root``, an off-git ``root`` or a missing ``git`` (like ``gc/delete.py``):
    "untracked" means nothing off-git. Callers that must tell "untracked" from
    "no repo" check :func:`is_git_repo` first.
    """
    rel = _relative_to_root(root, path)
    if rel is None:
        # ``git -C <root>`` can't address it; containment is the caller's concern.
        return True
    try:
        completed = run_git(root, "ls-files", "--error-unmatch", str(rel))
    except (FileNotFoundError, OSError):
        # git executable missing → treat as tracked (graceful off-git degradation).
        return True
    if completed.returncode == 0:
        return True
    # Non-zero means untracked *or* not a repo; the filesystem probe decides.
    return not is_git_repo(root)


def _relative_to_root(root: Path, path: Path) -> Path | None:
    """``path`` relative to ``root`` (symlinks resolved), or ``None`` if outside.

    A relative ``path`` is taken against ``root`` first.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return None
