"""Closed alphabets of the symbol graph and its query surface."""

from __future__ import annotations

from enum import Enum


class GraphRelation(str, Enum):
    """The closed edge-relation alphabet of ``symbol-graph.json``."""

    CALLS = "calls"
    USES = "uses"
    CONTAINS = "contains"
    IMPORTS_FROM = "imports_from"
    INHERITS = "inherits"
    METHOD = "method"
    RATIONALE_FOR = "rationale_for"

    __str__ = str.__str__


# Incoming edges of these relations mean "someone depends on this symbol".
DEPENDENCY_RELATIONS: frozenset[str] = frozenset(
    {
        GraphRelation.CALLS.value,
        GraphRelation.USES.value,
        GraphRelation.IMPORTS_FROM.value,
        GraphRelation.INHERITS.value,
    }
)


class GraphVerb(str, Enum):
    """`dummyindex context graph <verb>` — the closed verb alphabet."""

    CALLERS_OF = "callers-of"
    CALLEES_OF = "callees-of"
    IMPACT = "impact"
    PATH = "path"
    NEIGHBORS = "neighbors"
    DEAD_CODE = "dead-code"
    COMMUNITY = "community"

    __str__ = str.__str__


class EdgeDirection(str, Enum):
    """Which way an edge points relative to the row's anchor node.

    ``IN`` — the row's node points at the anchor (it calls / uses /
    inherits the subject). ``OUT`` — the anchor points at the row's node.
    """

    IN = "in"
    OUT = "out"

    __str__ = str.__str__
