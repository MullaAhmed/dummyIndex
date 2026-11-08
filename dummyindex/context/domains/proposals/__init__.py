"""Grounded planning: scaffold a consistency-checked proposal artifact.

``dummyindex context propose --slug S --title "..."`` writes a
``.context/proposals/<slug>/`` folder (``proposal.json`` plus ``spec.md`` /
``plan.md`` / ``checklist.md`` templates), then a deterministic consistency scan
(reusing the ``query`` retrieval domain) records related features + conventions.
``__all__`` is the public surface the tests and CLI import.
"""

from __future__ import annotations

from .closeout import closeout_from_file, closeout_workspace
from .enums import ProposalStatus
from .errors import CloseoutError, ProposalError, ProposalExistsError, ProposalSlugError
from .models import SCHEMA_VERSION, ConsistencyHits, Proposal
from .scan import scan_consistency
from .store import (
    PROPOSALS_REL,
    apply_consistency,
    ensure_proposal,
    proposal_dir,
    read_proposal,
    set_routing,
    validate_slug,
    write_proposal_json,
)

__all__ = [
    "PROPOSALS_REL",
    "SCHEMA_VERSION",
    "ConsistencyHits",
    "CloseoutError",
    "Proposal",
    "ProposalError",
    "ProposalExistsError",
    "ProposalSlugError",
    "ProposalStatus",
    "apply_consistency",
    "closeout_from_file",
    "closeout_workspace",
    "ensure_proposal",
    "proposal_dir",
    "read_proposal",
    "scan_consistency",
    "set_routing",
    "validate_slug",
    "write_proposal_json",
]
