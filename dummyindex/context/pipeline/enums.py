"""Pipeline-area enums.

`ConfidenceLevel` is a `(str, Enum)` so values round-trip through JSON
unchanged; not `enum.StrEnum`, which needs 3.11 (3.10 is supported). Node kinds
and edge relations stay free strings at their call sites, not enumerated here.
"""

from __future__ import annotations

from enum import Enum


class ConfidenceLevel(str, Enum):
    """A graph node's confidence in its name / summary / structure.

    Persisted as the `confidence` field on every node in `tree.json`,
    feature/flow JSON, and surprise/audit reports.
    """

    EXTRACTED = "EXTRACTED"  # deterministic AST output, no LLM
    INFERRED = "INFERRED"  # LLM-enriched, judgment call
    AMBIGUOUS = "AMBIGUOUS"  # extractor flagged uncertainty
