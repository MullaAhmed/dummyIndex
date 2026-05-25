"""Pipeline-area enums.

Closed-alphabet string constants used by the deterministic backbone.
Every value is a real `str` (via `(str, Enum)`) so it round-trips through
JSON serialisation without conversion. Python 3.10-compatible (no
`enum.StrEnum`, which lands in 3.11).

If a value's set is dynamic (e.g. `uses_<callee_name>` edge relations),
it stays a free string at that one site — but every closed alphabet that
appears in `.context/` artefacts lives here.
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
    PINNED = "PINNED"         # human-curated, do not auto-overwrite
    AMBIGUOUS = "AMBIGUOUS"   # extractor flagged uncertainty


INFERABLE_LEVELS: frozenset[ConfidenceLevel] = frozenset(
    {ConfidenceLevel.EXTRACTED, ConfidenceLevel.INFERRED}
)


class NodeKind(str, Enum):
    """Closed-set kinds for nodes in `structure.json` / `tree.json`."""

    FOLDER = "folder"
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    GLOBAL = "global"


class EdgeRelation(str, Enum):
    """Closed-set edge relations on the backbone graph.

    The `uses_<callee>` family is **dynamic** (one relation per called
    symbol name) and is not listed here — leave those as free strings at
    the call site.
    """

    FOLDER_CONTAINS = "folder_contains"
    CONTAINS = "contains"
    METHOD = "method"
    INHERITS = "inherits"
    IMPORTS = "imports"
    IMPORTS_FROM = "imports_from"
    CALLS = "calls"
    BOUND_TO = "bound_to"


HIERARCHY_RELATIONS: frozenset[EdgeRelation] = frozenset(
    {EdgeRelation.FOLDER_CONTAINS, EdgeRelation.CONTAINS, EdgeRelation.METHOD}
)
