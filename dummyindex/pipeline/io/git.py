# pure-filesystem git-repo detection (submodule / worktree aware)
"""Recognise a git working tree without shelling out to ``git``.

A plain checkout has a ``.git`` *directory*. Submodules and worktrees
instead carry a ``.git`` *file* whose first line is ``gitdir: <path>``
pointing at the real git dir (under the superproject's
``.git/modules/<name>`` or the parent's ``.git/worktrees/<name>``). The
old ``(.git).is_dir()`` checks reported those valid repos as non-repos.

Everything here is a deterministic filesystem read: no subprocess, no
network, no third-party deps. Malformed input is treated as "not a repo"
rather than raised — these helpers gate optional install-time steps and
must never crash the command they guard.
"""
from __future__ import annotations

import configparser
from pathlib import Path

_GITDIR_PREFIX = "gitdir:"
_COMMONDIR = "commondir"


def is_git_repo(root: Path) -> bool:
    """True when ``root`` is a git working tree.

    Accepts both a ``.git`` directory (plain checkout) and a ``.git`` file
    whose first line starts with ``gitdir:`` (submodule / worktree). The
    pointer target does not have to resolve — git's own discovery treats
    the prefix as the marker, so a dangling pointer is still "a repo".
    """
    dot_git = root / ".git"
    if dot_git.is_dir():
        return True
    return _first_line(dot_git).startswith(_GITDIR_PREFIX)


def resolve_git_dir(root: Path) -> Path | None:
    """Return the actual git dir for ``root``, or ``None`` if there isn't one.

    - Plain checkout: the ``.git`` directory itself.
    - Submodule / worktree: the directory named by the ``.git`` file's
      ``gitdir:`` pointer (relative paths resolve against ``root``).
    - Worktree refinement: when the pointed-at dir holds a ``commondir``
      file, follow it to the *common* git dir — that's where ``hooks/`` and
      ``config`` live, which is what callers scrubbing legacy hooks need.

    Returns ``None`` when ``.git`` is absent or the pointer is empty /
    unparseable. Never raises on malformed content.
    """
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git.resolve()

    pointer = _read_gitdir_payload(dot_git)
    if not pointer:
        return None
    git_dir = _resolve_against(root, pointer)
    return _follow_commondir(git_dir)


def submodule_paths(root: Path) -> tuple[Path, ...]:
    """Absolute paths of the git submodules declared in ``<root>/.gitmodules``.

    A pure-filesystem INI parse — no subprocess, matching the rest of this
    module. Each ``[submodule "<name>"]`` section's ``path`` is resolved
    against ``root`` (in declaration order). Returns ``()`` when
    ``.gitmodules`` is absent or unparseable; never raises — these helpers
    gate optional steps and must not crash the command they guard.
    """
    gitmodules = root / ".gitmodules"
    if not gitmodules.is_file():
        return ()
    parser = configparser.ConfigParser()
    try:
        parser.read_string(gitmodules.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, configparser.Error):
        return ()
    paths: list[Path] = []
    for section in parser.sections():
        rel = parser.get(section, "path", fallback="").strip()
        if rel:
            paths.append((root / rel).resolve())
    return tuple(paths)


def _first_line(dot_git: Path) -> str:
    """First line of a ``.git`` *file*, or ``""`` if it can't be read.

    Returns ``""`` for a missing file, a directory, an unreadable/undecodable
    file, or an empty file — never raises.
    """
    if not dot_git.is_file():
        return ""
    try:
        lines = dot_git.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return ""
    return lines[0] if lines else ""


def _read_gitdir_payload(dot_git: Path) -> str | None:
    """Return the ``gitdir:`` payload from a ``.git`` *file*, else ``None``.

    ``None`` when the first line lacks the ``gitdir:`` prefix or the payload
    is empty — i.e. there is no path to resolve.
    """
    first_line = _first_line(dot_git)
    if not first_line.startswith(_GITDIR_PREFIX):
        return None
    payload = first_line[len(_GITDIR_PREFIX):].strip()
    return payload or None


def _resolve_against(root: Path, pointer: str) -> Path:
    """Resolve a (possibly relative) gitdir pointer against ``root``."""
    target = Path(pointer)
    if not target.is_absolute():
        target = root / target
    return target.resolve()


def _follow_commondir(git_dir: Path) -> Path:
    """Follow a worktree's ``commondir`` to the shared git dir, if present.

    For a normal git dir there is no ``commondir`` file and ``git_dir`` is
    returned unchanged. For a worktree metadata dir, ``commondir`` holds a
    path (usually relative) to the common dir where ``hooks/`` live.
    """
    commondir_file = git_dir / _COMMONDIR
    if not commondir_file.is_file():
        return git_dir
    try:
        rel = commondir_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return git_dir
    if not rel:
        return git_dir
    return _resolve_against(git_dir, rel)
