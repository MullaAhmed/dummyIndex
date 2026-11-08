# build-time git interaction: shells out to git, degrades to None on any failure
"""Commit-anchored delta detection via ``git`` subprocess.

Subprocess lives here, not in the deliberately subprocess-free ``pipeline/io/git.py``.
Nothing here raises: a missing git, non-repo or unknown anchor yields ``None`` (or
``False``), because these results gate the non-destructive rebuild and must never crash
the command they guard. :func:`changed_paths` merges tracked changes (``git diff``) with
untracked files (``git status``); the two sets are disjoint, so nothing double-counts.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


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


def head_commit(root: Path) -> str | None:
    """Return ``git rev-parse HEAD`` for ``root``, or ``None``.

    ``None`` when git is absent, ``root`` isn't a repo, or HEAD is
    unborn (a fresh ``git init`` with no commits). Never raises.
    """
    out = _run_git(root, "rev-parse", "HEAD")
    if out is None:
        return None
    sha = out.strip()
    return sha or None


def working_tree_dirty(root: Path) -> bool | None:
    """True when the working tree has uncommitted changes OUTSIDE ``.context/``.

    ``reconcile-stamp`` warns with it: the stamp anchors to HEAD, so uncommitted source
    re-surfaces as drift next reconcile. ``.context/`` is excluded because reconcile
    always writes there. ``None`` when git is absent or ``root`` isn't a repo. Never raises.
    """
    out = _run_git(root, "-c", "core.quotePath=false", "status", "--porcelain", "-uall")
    if out is None:
        return None
    for line in out.splitlines():
        # porcelain: two status chars, a space, then the path.
        path = line[3:].strip().strip('"') if len(line) > 3 else ""
        if not path:
            continue
        if path == ".context" or path.startswith(".context/"):
            continue
        return True
    return False


def commit_exists(root: Path, sha: str) -> bool | None:
    """Whether ``sha`` names a commit object present in ``root``'s repo.

    ``True`` when the object resolves, ``False`` when the repo is reachable
    but the object is absent (a gc'd / never-fetched anchor — the rebase/squash
    orphan case), and ``None`` when git is absent or ``root`` isn't a repo (so
    the caller can't distinguish "missing object" from "no repo"). Never raises.
    """
    if not sha:
        return None
    # `cat-file -e <sha>^{commit}` exits 0 iff the object exists and is a
    # commit. Probe `rev-parse --git-dir` first so a non-repo returns None
    # rather than the same non-zero exit an absent object produces.
    if _run_git(root, "rev-parse", "--git-dir") is None:
        return None
    probe = _run_git(root, "cat-file", "-e", f"{sha}^{{commit}}")
    return probe is not None


def is_ancestor_of_head(root: Path, sha: str) -> bool | None:
    """Whether ``sha`` is an ancestor of HEAD in ``root``'s repo.

    ``True`` / ``False`` per ``git merge-base --is-ancestor``; ``None`` when
    git is absent, ``root`` isn't a repo, HEAD is unborn, or ``sha`` is unknown
    (any case where the relationship can't be decided). Never raises. The
    caller uses this to warn that a delta against a non-ancestor anchor may
    include other branches' work.
    """
    if not sha:
        return None
    if commit_exists(root, sha) is not True:
        return None
    if head_commit(root) is None:
        return None
    # `_run_git` maps every non-zero exit to None, but exit 1 here means "not an ancestor".
    return _is_ancestor_exit(root, sha)


def _is_ancestor_exit(root: Path, sha: str) -> bool | None:
    """Run ``merge-base --is-ancestor`` and map its tri-state exit code.

    0 → ``True`` (ancestor), 1 → ``False`` (not an ancestor), anything else
    (or a missing git) → ``None``. Kept separate from ``_run_git`` because
    that helper collapses every non-zero exit to ``None`` — here exit 1 is a
    *meaningful* answer, not a failure.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError):
        return None
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    return None


def commits_since(root: Path, anchor: str | None) -> int | None:
    """Return ``git rev-list --count <anchor>..HEAD`` for ``root``, or ``None``.

    The commit-count throttle the GC sweep anchors on; ``0`` when ``anchor`` is HEAD.
    ``None`` (the signal goes safely dark) when ``anchor`` is ``None``, git is absent,
    ``root`` isn't a repo, HEAD is unborn, or ``anchor`` is unknown to the repo (checked
    via :func:`commit_exists` up front, not ``rev-list``'s exit code). Never raises.
    """
    if anchor is None:
        return None
    # An unknown anchor (gc'd / rewritten history) or no repo: nothing to count against.
    if commit_exists(root, anchor) is not True:
        return None
    # An unborn HEAD has no commit to count up to.
    if head_commit(root) is None:
        return None
    out = _run_git(root, "rev-list", "--count", f"{anchor}..HEAD")
    if out is None:
        return None
    text = out.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def changed_paths(root: Path, since: str) -> ChangedPaths | None:
    """Paths changed between ``since`` and HEAD, including the working tree.

    Composes ``git diff --name-status --no-renames <since>`` (tracked changes through the
    working tree; ``--no-renames`` keeps every line ``A``/``M``/``D``) with the ``??``
    lines of ``git status --porcelain -uall`` (untracked files, listed one by one).
    ``None`` when git is absent, ``root`` isn't a repo, or ``since`` is unknown. Never raises.
    """
    if not since:
        return None

    # `-c core.quotePath=false` keeps non-ASCII paths as raw UTF-8 instead of
    # C-escaped octal (``"caf\303\251.py"``), so a `café.py` arrives intact.
    diff_out = _run_git(
        root,
        "-c",
        "core.quotePath=false",
        "diff",
        "--name-status",
        "--no-renames",
        since,
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
        # Other statuses (copies, type-changes) are ignored.

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


def _parse_diff_line(line: str) -> tuple[str | None, str | None]:
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


def _parse_untracked_line(line: str) -> str | None:
    """Return the path from a porcelain ``?? path`` line, else ``None``.

    Only untracked entries (``??``) contribute here — tracked changes are
    already captured by ``git diff``.
    """
    if not line.startswith("?? "):
        return None
    path = line[3:].strip().strip('"')
    return path or None


def _run_git(root: Path, *args: str) -> str | None:
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
