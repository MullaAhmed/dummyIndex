"""Unit tests for ``gc.enumerate.enumerate_candidates``.

Builds a synthetic ``.context/`` under ``tmp_path`` (never this repo's mutable
contents) and asserts the walk surfaces the right candidates with the right
kinds, rel-paths, statuses, and the sentinel-skipping rules. The off-git case
(no ``git init``) pins ``tracked=True`` / ``age_days=None`` — off-git must never
look "unrecoverable".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.gc.enumerate import enumerate_candidates
from dummyindex.context.domains.gc.enums import CandidateKind


def _make_proposal(context_dir: Path, slug: str, *, status: str | None) -> Path:
    """Create ``.context/proposals/<slug>/`` with a ``proposal.json``."""
    workspace = context_dir / "proposals" / slug
    workspace.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"slug": slug, "title": slug}
    if status is not None:
        payload["status"] = status
    (workspace / "proposal.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return workspace


def _make_audit(context_dir: Path, slug: str) -> Path:
    """Create ``.context/audits/<slug>/`` (no ``report.md`` needed here)."""
    workspace = context_dir / "audits" / slug
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "audit.json").write_text("{}\n", encoding="utf-8")
    return workspace


def _make_archive_child(context_dir: Path, slug: str) -> Path:
    """Create ``.context/proposals/_archive/<slug>/``."""
    workspace = context_dir / "proposals" / "_archive" / slug
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "spec.md").write_text("archived\n", encoding="utf-8")
    return workspace


@pytest.fixture
def context_dir(tmp_path: Path) -> Path:
    """A fixture ``.context/`` covering every enumeration branch (off-git)."""
    ctx = tmp_path / ".context"
    (ctx / "proposals").mkdir(parents=True)
    (ctx / "audits").mkdir(parents=True)

    _make_proposal(ctx, "live-feature", status="done")
    _make_audit(ctx, "auth-review")
    _make_archive_child(ctx, "ponytail-improvements")

    # Sentinel containers: a leading-underscore dir that is NOT _archive must be
    # skipped entirely (no candidate for the container, none for its children).
    backups = ctx / "proposals" / "_doc_backups"
    backups.mkdir(parents=True)
    (backups / "spec.md").write_text("backup\n", encoding="utf-8")

    # A dot-dir is skipped too.
    (ctx / "proposals" / ".scratch").mkdir(parents=True)

    # A stray file (not a dir) directly under a root must be ignored.
    (ctx / "proposals" / "stray.md").write_text("nope\n", encoding="utf-8")

    # session-memory lives outside proposals/audits, so it is naturally excluded.
    (ctx / "session-memory").mkdir(parents=True)

    return ctx


@pytest.mark.unit
def test_proposal_surfaces_with_status(context_dir: Path) -> None:
    candidates = enumerate_candidates(context_dir)
    by_slug = {c.slug: c for c in candidates}

    proposal = by_slug["live-feature"]
    assert proposal.kind is CandidateKind.PROPOSAL
    assert proposal.rel_path == "proposals/live-feature"
    assert proposal.status == "done"
    assert proposal.signals == ()


@pytest.mark.unit
def test_audit_surfaces_with_no_status(context_dir: Path) -> None:
    candidates = enumerate_candidates(context_dir)
    by_slug = {c.slug: c for c in candidates}

    audit = by_slug["auth-review"]
    assert audit.kind is CandidateKind.AUDIT
    assert audit.rel_path == "audits/auth-review"
    assert audit.status is None
    assert audit.signals == ()


@pytest.mark.unit
def test_archive_child_surfaces_as_archived(context_dir: Path) -> None:
    candidates = enumerate_candidates(context_dir)
    by_slug = {c.slug: c for c in candidates}

    archived = by_slug["ponytail-improvements"]
    assert archived.kind is CandidateKind.ARCHIVED
    assert archived.rel_path == "proposals/_archive/ponytail-improvements"
    assert archived.status is None


@pytest.mark.unit
def test_archive_container_is_not_itself_a_candidate(context_dir: Path) -> None:
    slugs = {c.slug for c in enumerate_candidates(context_dir)}
    assert "_archive" not in slugs


@pytest.mark.unit
def test_doc_backups_sentinel_is_not_surfaced(context_dir: Path) -> None:
    slugs = {c.slug for c in enumerate_candidates(context_dir)}
    # Neither the container nor any descendant of a non-archive sentinel surfaces.
    assert "_doc_backups" not in slugs


@pytest.mark.unit
def test_dot_dir_and_stray_file_are_ignored(context_dir: Path) -> None:
    slugs = {c.slug for c in enumerate_candidates(context_dir)}
    assert ".scratch" not in slugs
    assert "stray.md" not in slugs


@pytest.mark.unit
def test_session_memory_is_excluded(context_dir: Path) -> None:
    slugs = {c.slug for c in enumerate_candidates(context_dir)}
    assert "session-memory" not in slugs


@pytest.mark.unit
def test_off_git_is_tracked_true_age_none(context_dir: Path) -> None:
    # No `git init` in the fixture → every candidate reads tracked=True (so an
    # off-git workspace never looks unrecoverable) and age_days=None.
    for candidate in enumerate_candidates(context_dir):
        assert candidate.tracked is True
        assert candidate.age_days is None


@pytest.mark.unit
def test_deterministic_order_by_kind_then_slug(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    (ctx / "proposals").mkdir(parents=True)
    (ctx / "audits").mkdir(parents=True)

    _make_proposal(ctx, "zeta", status="planned")
    _make_proposal(ctx, "alpha", status="planned")
    _make_audit(ctx, "mid-audit")
    _make_archive_child(ctx, "old-thing")

    candidates = enumerate_candidates(ctx)
    order = [(c.kind.value, c.slug) for c in candidates]
    assert order == sorted(order)


@pytest.mark.unit
def test_unreadable_proposal_json_gives_none_status(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    (ctx / "audits").mkdir(parents=True)
    workspace = ctx / "proposals" / "broken"
    workspace.mkdir(parents=True)
    (workspace / "proposal.json").write_text("{ not json", encoding="utf-8")

    (candidate,) = enumerate_candidates(ctx)
    assert candidate.kind is CandidateKind.PROPOSAL
    assert candidate.status is None


@pytest.mark.unit
def test_missing_roots_yield_empty(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True)
    assert enumerate_candidates(ctx) == ()
