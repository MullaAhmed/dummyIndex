# build-time git interaction: shells out to git, degrades to None on any failure
"""Commit-anchored delta detection via ``git`` subprocess.

The pure-filesystem helpers in ``pipeline/io/git.py`` are intentionally
subprocess-free and stay that way. This module is the *build-lifecycle*
counterpart: it shells out to ``git`` to learn the current HEAD and the
set of paths that changed since a recorded anchor commit. It lives under
``context/build/`` because it's consumed only by the build lifecycle
(``runner``, ``incremental``, the reconcile report) and never by
``pipeline`` or ``analysis``; ``subprocess`` is stdlib, so this respects
the §2 layering table without inventing a ``runtime/`` layer for a single
non-cross-cutting helper.

Everything here **degrades gracefully**: when ``git`` is absent, the
directory isn't a repo, or the anchor commit is unknown, the functions
return ``None`` / empty rather than raising. These results gate the
non-destructive rebuild path and must never crash the command they guard.

The delta covers committed history **and** the working tree, including
untracked files:

- ``git diff --name-status --no-renames <since>`` reports tracked
  additions / modifications / deletions from ``<since>`` through the
  working tree (so uncommitted edits are included). ``--no-renames``
  keeps every line single-status (``A``/``M``/``D``) so a rename never
  appears as the unparsed ``R100 old new`` form.
- ``git status --porcelain -uall`` contributes the ``??`` (untracked)
  files that ``git diff`` never sees. ``-uall`` lists files inside a new
  directory individually rather than collapsing to a bare ``dir/``.

The two sources cover disjoint sets (diff = tracked, ``??`` = untracked),
so there is no double-count when they are merged.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ChangedPaths:
    """Repo-relative POSIX paths that changed between an anchor and HEAD.

    ``added`` includes untracked working-tree files; ``modified`` and
    ``removed`` are tracked-file edits and deletions. All tuples are
    sorted and de-duplicated.
    """

    added: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


def head_commit(root: Path) -> Optional[str]:
    """Return ``git rev-parse HEAD`` for ``root``, or ``None``.

    ``None`` when git is absent, ``root`` isn't a repo, or HEAD is
    unborn (a fresh ``git init`` with no commits). Never raises.
    """
    out = _run_git(root, "rev-parse", "HEAD")
    if out is None:
        return None
    sha = out.strip()
    return sha or None


def changed_paths(root: Path, since: str) -> Optional[ChangedPaths]:
    """Paths changed between ``since`` and HEAD, including the working tree.

    Composes ``git diff --name-status --no-renames <since>`` (tracked
    changes through the working tree) with the ``??`` lines of
    ``git status --porcelain -uall`` (untracked files). Returns ``None``
    when git is absent, ``root`` isn't a repo, or ``since`` is unknown to
    the repo (e.g. an anchor commit that was never fetched). Never raises.
    """
    if not since:
        return None

    # `-c core.quotePath=false` keeps non-ASCII paths as raw UTF-8 instead of
    # C-escaped octal (``"caf\303\251.py"``), so a `café.py` arrives intact.
    diff_out = _run_git(
        root, "-c", "core.quotePath=false",
        "diff", "--name-status", "--no-renames", since,
    )
    if diff_out is None:
        # git missing, not a repo, or `since` not a valid commit.
        return None

    added: set[str] = set()
    modified: set[str] = set()
    removed: set[str] = set()

    for line in diff_out.splitlines():
        status, path = _parse_diff_line(line)
        if path is None:
            continue
        if status == "A":
            added.add(path)
        elif status == "M":
            modified.add(path)
        elif status == "D":
            removed.add(path)
        # Any other status (copies, type-changes) is ignored — the spec's
        # classification only cares about added / modified / removed.

    status_out = _run_git(
        root, "-c", "core.quotePath=false", "status", "--porcelain", "-uall"
    )
    if status_out is not None:
        for line in status_out.splitlines():
            path = _parse_untracked_line(line)
            if path is not None:
                added.add(path)

    return ChangedPaths(
        added=tuple(sorted(added)),
        modified=tuple(sorted(modified)),
        removed=tuple(sorted(removed)),
    )


def _parse_diff_line(line: str) -> tuple[Optional[str], Optional[str]]:
    """Split a ``--name-status`` line into (status-letter, path).

    Lines look like ``M\tpath/to/file`` — a single status char (with
    ``--no-renames`` there is never a similarity score) and a
    tab-separated path. Returns ``(None, None)`` for blank / malformed
    lines.
    """
    if not line:
        return None, None
    parts = line.split("\t")
    if len(parts) < 2:
        return None, None
    status = parts[0].strip()[:1]
    path = parts[-1].strip()
    return (status or None), (path or None)


def _parse_untracked_line(line: str) -> Optional[str]:
    """Return the path from a porcelain ``?? path`` line, else ``None``.

    Only untracked entries (``??``) contribute here — tracked changes are
    already captured by ``git diff``.
    """
    if not line.startswith("?? "):
        return None
    path = line[3:].strip().strip('"')
    return path or None


def _run_git(root: Path, *args: str) -> Optional[str]:
    """Run ``git -C <root> <args>`` and return stdout, or ``None`` on failure.

    ``None`` is returned when the ``git`` executable is missing
    (``FileNotFoundError``) or the command exits non-zero (not a repo,
    unknown commit, …). Never raises ``CalledProcessError`` — there is no
    ``check=True``.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            # Force UTF-8 decoding so raw non-ASCII paths (emitted under
            # `core.quotePath=false`) decode consistently regardless of the
            # host locale (C/POSIX containers would otherwise raise).
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout
