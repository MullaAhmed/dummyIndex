"""Closed alphabets for the context-hygiene GC domain."""

from __future__ import annotations

from enum import Enum


class Disposition(str, Enum):
    """What the council decides to do with a single GC candidate.

    ``KEEP`` is the default no-op verdict; the three ``DELETE_*`` /
    ``ROUTE_*`` members are the actionable outcomes the skill executes after
    user confirmation (docs deleted directly, trivially-dead code through
    implementer+tester, broader code routed to a new proposal).
    """

    KEEP = "keep"
    DELETE_DOC = "delete_doc"
    DELETE_CODE = "delete_code"
    ROUTE_TO_PROPOSAL = "route_to_proposal"


class CandidateKind(str, Enum):
    """The shape of a generated-doc workspace surfaced as a GC candidate."""

    PROPOSAL = "proposal"
    AUDIT = "audit"
    ORPHAN_SCAFFOLD = "orphan_scaffold"
    ARCHIVED = "archived"
