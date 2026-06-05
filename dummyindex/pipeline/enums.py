"""Pipeline-area enums.

`ConfidenceLevel` is the one closed-alphabet string-constant set used by the
deterministic backbone. Values are real `str` (via `(str, Enum)`) so they
round-trip through JSON serialisation without conversion. Python
3.10-compatible (no `enum.StrEnum`, which lands in 3.11).

Node kinds and edge relations are emitted as free strings at their call
sites (e.g. `"file"`, `"calls"`, `uses_<callee_name>`), not enumerated here.
"""
from __future__ import annotations

from enum import Enum


class ConfidenceLevel(str, Enum):
    """A graph node's confidence in its name / summary / structure.

    Persisted as the `confidence` field on every node in `tree.json`,
    feature/flow JSON, and surprise/audit reports.
    """

    EXTRACTED = "EXTRACTED"   # deterministic AST output, no LLM
    INFERRED = "INFERRED"     # LLM-enriched, judgment call
    AMBIGUOUS = "AMBIGUOUS"   # extractor flagged uncertainty
