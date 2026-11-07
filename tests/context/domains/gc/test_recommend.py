"""Unit tests for ``domains/gc/recommend.py:recommend`` (one case per rule row)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.gc import Recommendation, recommend
from dummyindex.context.domains.gc.enums import CandidateKind
from dummyindex.context.domains.gc.models import Candidate
from dummyindex.context.domains.proposals.retirement import receipt_path

pytestmark = pytest.mark.unit

PROPOSAL = CandidateKind.PROPOSAL
AUDIT = CandidateKind.AUDIT
ARCHIVED = CandidateKind.ARCHIVED


def _context(tmp_path: Path) -> Path:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    return context_dir


def _candidate(kind: CandidateKind, slug: str = "p", **fields) -> Candidate:
    return Candidate(kind=kind, slug=slug, rel_path=f"{kind.value}s/{slug}", **fields)


def _place(
    context_dir: Path, kind: CandidateKind, slug: str, *, receipt=False, pending=False
) -> Path:
    receipt_kind = "proposal" if kind in (PROPOSAL, ARCHIVED) else "audit"
    path = receipt_path(context_dir, receipt_kind, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    if receipt:
        path.write_text("{}", encoding="utf-8")
    if pending:
        path.with_suffix(".pending.json").write_text("{}", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("fields", "marker", "expected"),
    [
        ({"kind": PROPOSAL, "status": "in_progress"}, None, Recommendation.KEEP),
        ({"kind": PROPOSAL}, "pending", Recommendation.REVIEW),
        ({"kind": PROPOSAL}, "receipt", Recommendation.DELETE),
        ({"kind": PROPOSAL, "signals": ("orphan-empty",)}, None, Recommendation.DELETE),
        (
            {"kind": PROPOSAL, "signals": ("checklist-complete",)},
            None,
            Recommendation.CLOSE,
        ),
        ({"kind": AUDIT, "signals": ("report-written",)}, None, Recommendation.CLOSE),
        ({"kind": ARCHIVED}, None, Recommendation.REVIEW),
        ({"kind": AUDIT, "age_days": 30}, None, Recommendation.REVIEW),
        ({"kind": PROPOSAL, "age_days": 5}, None, Recommendation.KEEP),
    ],
    ids=[
        "in-progress-keep",
        "pending-review",
        "receipt-delete",
        "orphan-empty-delete",
        "checklist-complete-close",
        "report-written-close",
        "archived-review",
        "stale-review",
        "active-keep",
    ],
)
def test_each_rule_row(
    tmp_path: Path, fields: dict, marker: str | None, expected: Recommendation
) -> None:
    context_dir = _context(tmp_path)
    candidate = _candidate(**fields)
    if marker:
        _place(context_dir, candidate.kind, candidate.slug, **{marker: True})
    verdict, reason = recommend(candidate, context_dir)
    assert verdict == expected
    assert reason


def test_in_progress_beats_receipt(tmp_path: Path) -> None:
    context_dir = _context(tmp_path)
    _place(context_dir, PROPOSAL, "p", receipt=True)
    candidate = _candidate(PROPOSAL, status="in_progress")
    assert recommend(candidate, context_dir)[0] == Recommendation.KEEP


def test_pending_beats_receipt(tmp_path: Path) -> None:
    context_dir = _context(tmp_path)
    _place(context_dir, PROPOSAL, "p", receipt=True, pending=True)
    assert recommend(_candidate(PROPOSAL), context_dir)[0] == Recommendation.REVIEW


def test_orphan_empty_beats_stale(tmp_path: Path) -> None:
    context_dir = _context(tmp_path)
    candidate = _candidate(PROPOSAL, signals=("orphan-empty",), age_days=90)
    assert recommend(candidate, context_dir)[0] == Recommendation.DELETE


def test_archived_receipt_maps_to_proposal_file(tmp_path: Path) -> None:
    context_dir = _context(tmp_path)
    receipt = _place(context_dir, ARCHIVED, "old", receipt=True)
    assert receipt.name == "proposal-old.json"
    verdict, _ = recommend(_candidate(ARCHIVED, slug="old"), context_dir)
    assert verdict == Recommendation.DELETE


def test_archived_signals_still_review(tmp_path: Path) -> None:
    context_dir = _context(tmp_path)
    candidate = _candidate(
        ARCHIVED, status="in_progress", signals=("orphan-empty", "checklist-complete")
    )
    assert recommend(candidate, context_dir)[0] == Recommendation.REVIEW


def test_done_without_receipt_with_complete_checklist_closes(tmp_path: Path) -> None:
    context_dir = _context(tmp_path)
    candidate = _candidate(PROPOSAL, status="done", signals=("checklist-complete",))
    assert recommend(candidate, context_dir)[0] == Recommendation.CLOSE


def test_package_import_smoke() -> None:
    from dummyindex.context.domains import gc

    assert gc.Recommendation is Recommendation
    assert gc.recommend is recommend
