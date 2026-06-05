"""Grounded planning: scaffold a consistency-checked proposal artifact.

``dummyindex context propose --slug S --title "..."`` turns a natural-language
feature request into a ``.context/proposals/<slug>/`` folder (``proposal.json``
plus ``spec.md`` / ``plan.md`` / ``checklist.md`` templates), then runs a
deterministic consistency scan (reusing the ``query`` retrieval domain) to
record related features + conventions into the proposal.

Public surface (the test + CLI import target):

- ``Proposal``, ``ConsistencyHits`` — frozen dataclasses
- ``ProposalStatus`` — enum for on-disk status values
- ``SCHEMA_VERSION``
- ``proposal_dir``, ``ensure_proposal``,
  ``apply_consistency``, ``read_proposal``, ``validate_slug``, ``PROPOSALS_REL``
- ``scan_consistency``
- ``ProposalError``, ``ProposalExistsError``, ``ProposalSlugError``
"""
from __future__ import annotations

from .enums import ProposalStatus
from .errors import ProposalError, ProposalExistsError, ProposalSlugError
from .models import SCHEMA_VERSION, ConsistencyHits, Proposal
from .scan import scan_consistency
from .store import (
    PROPOSALS_REL,
    apply_consistency,
    ensure_proposal,
    proposal_dir,
    read_proposal,
    validate_slug,
)

__all__ = [
    "PROPOSALS_REL",
    "SCHEMA_VERSION",
    "ConsistencyHits",
    "Proposal",
    "ProposalError",
    "ProposalExistsError",
    "ProposalSlugError",
    "ProposalStatus",
    "apply_consistency",
    "ensure_proposal",
    "proposal_dir",
    "read_proposal",
    "scan_consistency",
    "validate_slug",
]
