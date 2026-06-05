"""Closed alphabet for the proposal lifecycle."""
from __future__ import annotations

from enum import Enum


class ProposalStatus(str, Enum):
    """The on-disk status a proposal can carry in ``proposal.json``."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
