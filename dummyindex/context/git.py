# cross-cutting git-fact seam: the one place new context code asks git questions
"""Single cross-cutting git-fact helper for the ``context`` engine.

Three questions downstream consumers (the migration domain, the write-guard,
and — eventually — ``gc``) need to ask git, exposed **once** so no domain ever
reaches across a boundary into another domain's private ``_is_tracked`` /
``_is_git_repo``:

- :func:`is_git_repo` — a **pure-filesystem** predicate (no subprocess), reused
  from ``pipeline/io/git.py``. Callers branch on this *first*: in a non-git tree
  they skip every git call and fall back to plain filesystem moves. Being the
  reliable, subprocess-free gate is the whole reason this seam exists.
- :func:`is_tracked` — whether a path is tracked by git in a repo. Consulted
  only **after** :func:`is_git_repo` is true; its non-git behaviour is the
  deliberate degradation preserved from ``gc/delete.py:_is_tracked`` (see the
  function docstring).
- :func:`run_git` — run ``git -C <root> <args>`` and return the
  ``CompletedProcess``. Models the subprocess shape of
  ``build/git_delta.py:_run_git`` (the real git-mv/-add precedent), but returns
  the whole result instead of just stdout so a caller can read ``returncode``.

This module lives top-level under ``context/`` (not inside a domain) because it
is cross-cutting: a sibling domain with the same need would want it, so by the
folder-organization §3 test it is a shared helper, not part of any one domain.
``subprocess`` is stdlib, so this respects the import-layering table without
inventing a ``runtime/`` layer for a single helper.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..pipeline.io import is_git_repo as _fs_is_git_repo

__all__ = ["is_git_repo", "is_tracked", "run_git"]


def is_git_repo(root: Path) -> bool:
    """True when ``root`` is a git working tree — pure filesystem, no subprocess.

    Thin re-export of ``pipeline/io/git.py:is_git_repo``: recognises both a
    ``.git`` *directory* (plain checkout) and a ``.git`` *file* carrying a
    ``gitdir:`` pointer (submodule / worktree). Surfaced here so seam consumers
    import one module. Because it never shells out, it is the reliable predicate
    callers branch on **before** deciding to invoke git at all.
    """
    return _fs_is_git_repo(root)


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``git -C <root> <args>`` and return the ``CompletedProcess``.

    Models the subprocess shape of ``build/git_delta.py:_run_git`` — UTF-8
    decode with ``errors="replace"`` so a non-ASCII path never raises a decode
    error on a C/POSIX-locale host — but returns the whole ``CompletedProcess``
    instead of just stdout, so a caller running ``git mv`` / ``git add`` can
    inspect ``returncode``. There is **no** ``check=True``: a non-zero git exit
    is a value to read, never a raise.

    Callers must gate on :func:`is_git_repo` first (the seam's contract); this
    issues a real subprocess, so reaching it with no ``git`` executable on
    ``PATH`` raises ``FileNotFoundError`` rather than degrading silently.
    """
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        # Force UTF-8 decoding so raw non-ASCII paths decode consistently
        # regardless of the host locale (C/POSIX containers would otherwise
        # raise) — same rationale as build/git_delta.py:_run_git.
        encoding="utf-8",
        errors="replace",
    )


def is_tracked(root: Path, path: Path) -> bool:
    """Whether ``path`` is tracked by git in the repo rooted at ``root``.

    Uses ``git -C <root> ls-files --error-unmatch <rel>`` — exit 0 means at
    least one tracked path matches. ``path`` is made repo-relative (a relative
    ``path`` is taken against ``root``); a ``path`` outside ``root`` can't be
    addressed by ``-C <root>`` git and degrades to ``True`` (see below).

    *Non-git degradation (preserved verbatim from ``gc/delete.py:_is_tracked``):*
    when ``root`` is **not** a git repo, or the ``git`` executable is absent,
    this returns ``True``. An off-git file was never under git's tracking
    promise, so reporting it "untracked" would be a meaningless answer. This is
    exactly why the seam also exposes :func:`is_git_repo`: a caller that must
    distinguish "untracked inside a real repo" from "no repo at all" branches on
    ``is_git_repo(root)`` first and only consults ``is_tracked`` once inside a
    repo, where the in-repo answer (tracked ⇔ ``True``) is well-defined.
    """
    rel = _relative_to_root(root, path)
    if rel is None:
        # Outside ``root`` entirely — ``git -C <root>`` can't speak to it.
        # Degrade to tracked; containment is the caller's concern, not this
        # predicate's.
        return True
    try:
        completed = run_git(root, "ls-files", "--error-unmatch", str(rel))
    except (FileNotFoundError, OSError):
        # git executable missing → treat as tracked (graceful off-git degradation).
        return True
    if completed.returncode == 0:
        return True
    # A non-zero exit is ambiguous: the path is untracked *or* ``root`` isn't a
    # repo. Disambiguate with the filesystem probe — a real repo means the path
    # is genuinely untracked (``False``); no repo means degrade to tracked.
    return not is_git_repo(root)


def _relative_to_root(root: Path, path: Path) -> Path | None:
    """``path`` relative to ``root`` (symlinks resolved), or ``None`` if outside.

    A relative ``path`` is taken against ``root`` first, mirroring how the
    migration domain hands this absolute stray paths that already live under the
    repo root.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        return candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return None
