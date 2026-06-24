"""Unit tests for ``gc.delete.delete_workspace`` — the bounded destructive op.

Security-sensitive: this is the only GC verb that removes data. Every guard in
the ladder (slug → sentinel → realpath → liveness → recoverability → rmtree)
has a refusal test here, and each refusal asserts that **nothing was deleted**.

Fixtures build a synthetic ``.context/`` under ``tmp_path`` (never this repo's
mutable contents). The recoverability guard reads ``git ls-files``, so the
tracked/untracked cases use a real ``git init`` repo under ``tmp_path`` — the
one place a real ``git`` is genuinely required to exercise the behaviour.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.domains.audit.errors import AuditSlugError
from dummyindex.context.domains.gc.delete import delete_workspace
from dummyindex.context.domains.gc.enums import CandidateKind
from dummyindex.context.domains.gc.errors import GcPathError, GcTargetError
from dummyindex.context.domains.proposals.errors import ProposalSlugError

# A complete checklist (every box ticked) — liveness must NOT refuse this.
_CHECKLIST_DONE = (
    "# Checklist — done\n\n- [x] First item done.\n- [x] Second item done.\n"
)

# A partial checklist (some boxes unchecked) — liveness MUST refuse this.
_CHECKLIST_PARTIAL = (
    "# Checklist — partial\n\n- [x] First item done.\n- [ ] Second item still open.\n"
)


# ----- helpers --------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> None:
    """Run ``git -C <repo_root> <args>`` for fixture setup (raises on failure)."""
    subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    """Create ``<tmp>/repo`` as a real git repo and return its ``.context/`` dir.

    ``context_dir.parent`` is the repo root, mirroring the real layout the
    recoverability guard assumes (``repo_root = context_dir.parent``).
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test")
    context_dir = repo_root / ".context"
    (context_dir / "proposals").mkdir(parents=True)
    (context_dir / "audits").mkdir(parents=True)
    return context_dir


def _write_proposal(
    context_dir: Path,
    slug: str,
    *,
    status: str = "done",
    checklist: str = _CHECKLIST_DONE,
) -> Path:
    """Create ``proposals/<slug>/`` with ``proposal.json`` + ``checklist.md``."""
    workspace = context_dir / "proposals" / slug
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "proposal.json").write_text(
        json.dumps({"slug": slug, "title": slug, "status": status}, indent=2) + "\n",
        encoding="utf-8",
    )
    (workspace / "checklist.md").write_text(checklist, encoding="utf-8")
    return workspace


def _commit_all(repo_root: Path) -> None:
    """Stage + commit everything so ``git ls-files`` sees the workspace tracked."""
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "-m", "fixture")


# ----- happy path -----------------------------------------------------------


@pytest.mark.unit
def test_tracked_complete_proposal_is_deleted(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "live-feature")
    _commit_all(context_dir.parent)

    result = delete_workspace(
        context_dir, kind=CandidateKind.PROPOSAL, slug="live-feature"
    )

    assert result.deleted is True
    assert result.refused is False
    assert result.untracked is False
    assert not workspace.exists()


# ----- guard 1: slug validation (out-of-charset traversal) ------------------


@pytest.mark.unit
def test_traversal_slug_raises_proposal_slug_error(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    # A sibling that traversal could reach if the guard were absent.
    victim = context_dir / "proposals" / "victim"
    victim.mkdir(parents=True)

    with pytest.raises(ProposalSlugError):
        delete_workspace(context_dir, kind=CandidateKind.PROPOSAL, slug="../../etc")

    # The slug guard fires before any path work, so nothing is removed.
    assert victim.exists()


@pytest.mark.unit
def test_traversal_slug_raises_audit_slug_error_for_audit_kind(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    with pytest.raises(AuditSlugError):
        delete_workspace(context_dir, kind=CandidateKind.AUDIT, slug="../../etc")


# ----- guard 2: sentinel reject (the critical _archive case) ----------------


@pytest.mark.unit
def test_archive_sentinel_slug_raises_gc_target_error(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    # `_archive` is charset-VALID and resolves INSIDE the root, so guard 3
    # cannot catch it — guard 2 must. Give it real children to prove they live.
    archive = context_dir / "proposals" / "_archive" / "ponytail-improvements"
    archive.mkdir(parents=True)
    (archive / "spec.md").write_text("archived\n", encoding="utf-8")

    with pytest.raises(GcTargetError):
        delete_workspace(context_dir, kind=CandidateKind.PROPOSAL, slug="_archive")

    assert (context_dir / "proposals" / "_archive").exists()
    assert archive.exists()


@pytest.mark.unit
def test_leading_underscore_slug_raises_gc_target_error(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    sentinel = context_dir / "proposals" / "_"
    sentinel.mkdir(parents=True)

    with pytest.raises(GcTargetError):
        delete_workspace(context_dir, kind=CandidateKind.PROPOSAL, slug="_")

    assert sentinel.exists()


# ----- guard 3: realpath containment (symlink escape) -----------------------


@pytest.mark.unit
def test_symlinked_path_escaping_root_raises_gc_path_error(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    # A real directory OUTSIDE the .context root that must never be deleted.
    outside = tmp_path / "outside-target"
    outside.mkdir()
    (outside / "precious.txt").write_text("do not delete\n", encoding="utf-8")

    # A workspace dir under proposals/ that is actually a symlink to `outside`.
    link = context_dir / "proposals" / "sneaky"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(GcPathError):
        delete_workspace(context_dir, kind=CandidateKind.PROPOSAL, path=str(link))

    # The escape is refused: neither the symlink target nor its contents go.
    assert outside.exists()
    assert (outside / "precious.txt").exists()


# ----- guard 4: liveness (in_progress / partial checklist) ------------------


@pytest.mark.unit
def test_in_progress_proposal_refused_without_force_partial(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "wip", status="in_progress")
    _commit_all(context_dir.parent)

    with pytest.raises(GcTargetError):
        delete_workspace(context_dir, kind=CandidateKind.PROPOSAL, slug="wip")

    assert workspace.exists()


@pytest.mark.unit
def test_partial_checklist_proposal_refused_without_force_partial(
    tmp_path: Path,
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(
        context_dir, "half-done", status="done", checklist=_CHECKLIST_PARTIAL
    )
    _commit_all(context_dir.parent)

    with pytest.raises(GcTargetError):
        delete_workspace(context_dir, kind=CandidateKind.PROPOSAL, slug="half-done")

    assert workspace.exists()


@pytest.mark.unit
def test_in_progress_proposal_deleted_with_force_partial(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "wip", status="in_progress")
    _commit_all(context_dir.parent)

    result = delete_workspace(
        context_dir, kind=CandidateKind.PROPOSAL, slug="wip", force_partial=True
    )

    assert result.deleted is True
    assert not workspace.exists()


@pytest.mark.unit
def test_partial_checklist_proposal_deleted_with_force_partial(
    tmp_path: Path,
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(
        context_dir, "half-done", status="done", checklist=_CHECKLIST_PARTIAL
    )
    _commit_all(context_dir.parent)

    result = delete_workspace(
        context_dir,
        kind=CandidateKind.PROPOSAL,
        slug="half-done",
        force_partial=True,
    )

    assert result.deleted is True
    assert not workspace.exists()


# ----- guard 5: recoverability (git-tracked vs untracked) -------------------


@pytest.mark.unit
def test_untracked_workspace_refused_without_allow_untracked(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    # Created but never committed → git ls-files misses it → untracked.
    workspace = _write_proposal(context_dir, "scratch")
    # NOTE: no _commit_all() here.

    result = delete_workspace(context_dir, kind=CandidateKind.PROPOSAL, slug="scratch")

    assert result.deleted is False
    assert result.refused is True
    assert result.untracked is True
    assert result.reason is not None
    assert "allow_untracked" in result.reason
    # Refusal must not delete.
    assert workspace.exists()


@pytest.mark.unit
def test_untracked_workspace_deleted_with_allow_untracked(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "scratch")
    # Never committed → untracked.

    result = delete_workspace(
        context_dir,
        kind=CandidateKind.PROPOSAL,
        slug="scratch",
        allow_untracked=True,
    )

    assert result.deleted is True
    assert result.untracked is True
    assert not workspace.exists()


# ----- missing dir: idempotent no-op (NOT an error) -------------------------


@pytest.mark.unit
def test_missing_dir_is_idempotent_no_op(tmp_path: Path) -> None:
    context_dir = _init_repo(tmp_path)
    # No such workspace on disk.

    result = delete_workspace(
        context_dir, kind=CandidateKind.PROPOSAL, slug="never-existed"
    )

    assert result.deleted is False
    assert result.refused is False
    assert result.reason is not None
    assert "nothing to delete" in result.reason
