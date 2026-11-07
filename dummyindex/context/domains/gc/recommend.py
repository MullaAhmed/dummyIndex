"""Deterministic pre-council recommendation per GC candidate.

Pure function: reads the ``Candidate`` fields and two receipt file-existence
checks, never ``retirement_block``. The council's ``Disposition`` stays the
decision of record.
"""

from __future__ import annotations

from pathlib import Path

from ..proposals.retirement import receipt_path
from .constants import PROPOSAL_KINDS, STALE_AGE_DAYS
from .enums import CandidateKind, Recommendation
from .models import Candidate


def recommend(candidate: Candidate, context_dir: Path) -> tuple[Recommendation, str]:
    """Return ``(recommendation, one-line reason)``; first matching rule wins."""
    is_proposal = candidate.kind is CandidateKind.PROPOSAL
    kind = "proposal" if candidate.kind in PROPOSAL_KINDS else "audit"
    receipt = receipt_path(context_dir, kind, candidate.slug)
    pending = receipt.with_suffix(".pending.json")
    signals = candidate.signals

    if is_proposal and candidate.status == "in_progress":
        return Recommendation.KEEP, "build in progress"
    if pending.exists():
        return Recommendation.REVIEW, "interrupted closeout; review and resume"
    if receipt.exists():
        return Recommendation.DELETE, "closeout receipt recorded"
    if is_proposal and "orphan-empty" in signals:
        return Recommendation.DELETE, "scaffold never authored"
    if is_proposal and "checklist-complete" in signals:
        return Recommendation.CLOSE, "checklist complete"
    if candidate.kind == CandidateKind.AUDIT and "report-written" in signals:
        return Recommendation.CLOSE, "audit report written"
    if candidate.kind == CandidateKind.ARCHIVED:
        return Recommendation.REVIEW, "archived workspace"
    if (
        candidate.kind in (CandidateKind.PROPOSAL, CandidateKind.AUDIT)
        and candidate.age_days is not None
        and candidate.age_days >= STALE_AGE_DAYS
    ):
        return Recommendation.REVIEW, f"stale: {candidate.age_days} days old"
    return Recommendation.KEEP, "active or unfinished"
