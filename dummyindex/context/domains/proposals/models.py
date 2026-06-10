"""Frozen dataclasses for the proposal artifact.

A ``Proposal`` is the machine-readable head of a ``.context/proposals/<slug>/``
folder. The human-authored ``spec.md`` / ``plan.md`` / ``checklist.md`` siblings
carry the prose; ``proposal.json`` carries the structured fields that tooling
(consistency scan, later slices) reads and writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants import SCHEMA_VERSION
from .enums import ProposalStatus


@dataclass(frozen=True)
class Proposal:
    """The structured head of a proposal folder, persisted as ``proposal.json``."""

    slug: str
    title: str
    status: ProposalStatus = ProposalStatus.PLANNED
    related_features: tuple[str, ...] = ()
    conventions: tuple[str, ...] = ()
    # Populated later by the `/dummyindex-plan` skill (intentional forward schema).
    reused_symbols: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "slug": self.slug,
            "title": self.title,
            "status": self.status,
            "related_features": list(self.related_features),
            "conventions": list(self.conventions),
            "reused_symbols": list(self.reused_symbols),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Proposal":
        return cls(
            slug=str(payload.get("slug", "")),
            title=str(payload.get("title", "")),
            status=ProposalStatus(payload.get("status", ProposalStatus.PLANNED)),
            related_features=tuple(
                str(x) for x in (payload.get("related_features") or ())
            ),
            conventions=tuple(str(x) for x in (payload.get("conventions") or ())),
            reused_symbols=tuple(
                str(x) for x in (payload.get("reused_symbols") or ())
            ),
        )


@dataclass(frozen=True)
class ConsistencyHits:
    """What the deterministic consistency scan found for a proposal title.

    ``related_features`` are ``feature_id`` strings ranked by token overlap
    with the title; ``conventions`` are repo-relative POSIX paths of
    ``.context/conventions/*.md`` files that exist.
    """

    related_features: tuple[str, ...] = ()
    conventions: tuple[str, ...] = ()
