"""Frozen data records for the reality checker — data only, with ``to_dict()``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Claim:
    text: str
    source_file: str               # which canonical doc the claim came from
    kind: str                      # calls / uses / file:line / has_method
    subject: str
    object: str                    # for file:line claims, this is the line number as a string
    status: str                    # verified / contradicted / ambiguous
    reason: Optional[str] = None   # human-readable note when not verified

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source_file": self.source_file,
            "kind": self.kind,
            "subject": self.subject,
            "object": self.object,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RealityReport:
    schema_version: int
    feature_id: str
    claims_total: int
    verified: int
    contradicted: int
    ambiguous: int
    claims: tuple[Claim, ...]

    @property
    def has_contradictions(self) -> bool:
        return self.contradicted > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "feature_id": self.feature_id,
            "claims_total": self.claims_total,
            "verified": self.verified,
            "contradicted": self.contradicted,
            "ambiguous": self.ambiguous,
            "claims": [c.to_dict() for c in self.claims],
        }
