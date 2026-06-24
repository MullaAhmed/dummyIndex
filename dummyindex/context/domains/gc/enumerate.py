"""Enumerate the generated-doc workspaces the hygiene sweep may retire.

``enumerate_candidates`` walks only the *immediate* children of
``proposals_root`` and ``audits_root`` and returns one frozen :class:`Candidate`
per generated-doc workspace dir. It is pure structure + git facts — it assigns
no verdict and computes no ``signals`` (the sibling ``classify`` step fills those
later; this module never imports it). The sentinel rules:

- Every entry whose name starts with ``_`` is a sentinel *container* and is
  skipped (covers ``_archive``, future ``_doc_backups``-style scratch). Dot-dirs
  are skipped too.
- The single exception is ``_archive``: the sweep descends one level and surfaces
  each of *its* child dirs as an :class:`CandidateKind.ARCHIVED` candidate.

``session-memory`` lives at ``.context/session-memory`` — *not* under
``proposals/`` or ``audits/`` — so it is never reached by this walk and needs no
special-casing (it self-rolls; GC never touches it).

No ``print`` — this is domain logic; the CLI prints.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from ..audit.workspace import audits_root
from ..proposals.store import proposals_root
from .constants import ARCHIVE_SENTINEL
from .enums import CandidateKind
from .models import Candidate


def enumerate_candidates(
    context_dir: Path,
    *,
    today: date | None = None,
) -> tuple[Candidate, ...]:
    """Return every generated-doc workspace under ``proposals/`` + ``audits/``.

    Walks the immediate children of ``proposals_root(context_dir)`` and
    ``audits_root(context_dir)`` only. Skips ``_``-prefixed sentinel containers
    and dot-dirs, with the lone exception of ``_archive`` — whose children are
    surfaced as :class:`CandidateKind.ARCHIVED`. Candidates are returned sorted
    by ``(kind, slug)`` for a deterministic report. ``today`` (defaulting to
    :func:`date.today`) is the reference point for ``age_days`` and is accepted
    so tests can pin it.
    """
    reference = today or date.today()
    repo_root = context_dir.parent

    candidates: list[Candidate] = []
    candidates.extend(
        _walk_proposals(proposals_root(context_dir), repo_root, reference)
    )
    candidates.extend(_walk_audits(audits_root(context_dir), repo_root, reference))

    return tuple(sorted(candidates, key=lambda c: (c.kind.value, c.slug)))


def _walk_proposals(
    root: Path, repo_root: Path, today: date
) -> list[Candidate]:
    """Candidates under ``proposals/`` — normal slugs + ``_archive`` children."""
    out: list[Candidate] = []
    for child in _child_dirs(root):
        name = child.name
        if name == ARCHIVE_SENTINEL:
            out.extend(_walk_archive(child, repo_root, today))
            continue
        if _is_sentinel(name):
            continue
        out.append(
            _make_candidate(
                child,
                repo_root,
                kind=CandidateKind.PROPOSAL,
                rel_path=f"proposals/{name}",
                status=_read_status(child),
                today=today,
            )
        )
    return out


def _walk_archive(
    archive_dir: Path, repo_root: Path, today: date
) -> list[Candidate]:
    """Surface each child of ``proposals/_archive/`` as an ARCHIVED candidate."""
    out: list[Candidate] = []
    for child in _child_dirs(archive_dir):
        name = child.name
        if _is_sentinel(name):
            continue
        out.append(
            _make_candidate(
                child,
                repo_root,
                kind=CandidateKind.ARCHIVED,
                rel_path=f"proposals/{ARCHIVE_SENTINEL}/{name}",
                status=None,
                today=today,
            )
        )
    return out


def _walk_audits(root: Path, repo_root: Path, today: date) -> list[Candidate]:
    """Candidates under ``audits/`` — normal slugs only (no ``status``)."""
    out: list[Candidate] = []
    for child in _child_dirs(root):
        name = child.name
        if _is_sentinel(name):
            continue
        out.append(
            _make_candidate(
                child,
                repo_root,
                kind=CandidateKind.AUDIT,
                rel_path=f"audits/{name}",
                status=None,
                today=today,
            )
        )
    return out


def _child_dirs(root: Path) -> list[Path]:
    """Immediate child directories of ``root`` (empty if ``root`` is absent)."""
    if not root.is_dir():
        return []
    return [entry for entry in root.iterdir() if entry.is_dir()]


def _is_sentinel(name: str) -> bool:
    """Whether ``name`` is a skip-this entry: leading-``_`` or a dot-dir."""
    return name.startswith("_") or name.startswith(".")


def _make_candidate(
    workspace: Path,
    repo_root: Path,
    *,
    kind: CandidateKind,
    rel_path: str,
    status: str | None,
    today: date,
) -> Candidate:
    """Build one :class:`Candidate` with its git ``tracked`` / ``age_days`` facts."""
    tracked = _is_tracked(repo_root, rel_path)
    return Candidate(
        kind=kind,
        slug=workspace.name,
        rel_path=rel_path,
        status=status,
        signals=(),  # the sibling `classify` step fills signals later.
        tracked=tracked,
        age_days=_age_days(repo_root, rel_path, today) if tracked else None,
    )


def _read_status(workspace: Path) -> str | None:
    """Read the ``status`` field from ``proposal.json`` (None if unreadable)."""
    path = workspace / "proposal.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("status")
    return str(value) if value is not None else None


def _is_tracked(repo_root: Path, rel: str) -> bool:
    """Whether ``rel`` (under ``.context/``) is git-tracked.

    ``git ls-files --error-unmatch`` exits 0 iff the path is tracked. When git
    is absent the workspace is treated as ``tracked=True`` so an off-git repo
    never makes every doc look "unrecoverable" on delete.
    """
    rel_to_repo = f".context/{rel}"
    out = _run_git(repo_root, "ls-files", "--error-unmatch", rel_to_repo)
    if out is None:
        # Distinguish "git missing" (→ tracked) from "tracked but ls-files
        # returned no stdout". `_run_git` collapses a non-zero exit (untracked)
        # to None too, so re-probe whether git itself is reachable.
        if _run_git(repo_root, "rev-parse", "--git-dir") is None:
            return True  # off-git: never look unrecoverable.
        return False  # in a repo, but the path is untracked.
    return True


def _age_days(repo_root: Path, rel: str, today: date) -> int | None:
    """Days since ``rel``'s last git commit, or ``None`` off-git / untracked.

    Uses ``git log -1 --format=%ct`` (the commit timestamp) only — never the
    filesystem mtime, which a fresh clone resets to checkout time.
    """
    rel_to_repo = f".context/{rel}"
    out = _run_git(repo_root, "log", "-1", "--format=%ct", "--", rel_to_repo)
    if out is None:
        return None
    text = out.strip()
    if not text:
        return None
    try:
        commit_ts = int(text)
    except ValueError:
        return None
    commit_date = datetime.fromtimestamp(commit_ts, tz=timezone.utc).date()
    return (today - commit_date).days


def _run_git(repo_root: Path, *args: str) -> str | None:
    """Run ``git -C <repo_root> <args>`` → stdout, or ``None`` on any failure.

    Mirrors ``build/git_delta.py:_run_git``: a missing executable or a non-zero
    exit collapses to ``None`` (never ``CalledProcessError``). Kept local so
    ``enumerate`` owns its own minimal git probe rather than coupling to the
    build-lifecycle module.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout
