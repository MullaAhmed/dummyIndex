"""Bounded, cited query verbs over ``features/symbol-graph.json``.

`dummyindex context graph <verb>` answers caller / callee / impact / path /
neighborhood / dead-code / community questions from the symbol graph, loaded
read-only into a directed multigraph. Answers are bounded (``--limit`` / depth
caps) and cited; link direction comes from ``_src``/``_tgt`` (``load.py``).
Dead-code is purely graph-driven, so its precision is the extractor's.
"""

from __future__ import annotations

from .constants import (
    DEFAULT_DEAD_CODE_LIMIT,
    DEFAULT_IMPACT_DEPTH,
    DEFAULT_LIMIT,
    DEFAULT_NEIGHBOR_HOPS,
    SCHEMA_VERSION,
)
from .enums import DEPENDENCY_RELATIONS, EdgeDirection, GraphRelation, GraphVerb
from .errors import (
    AmbiguousSymbolError,
    GraphArtifactInvalidError,
    GraphArtifactMissingError,
    GraphQueryError,
    UnknownSymbolError,
)
from .load import load_symbol_graph
from .models import GraphQueryResult, GraphRow, SymbolGraph
from .render import render_json, render_markdown
from .resolve import resolve_symbol
from .verbs import (
    callees_of,
    callers_of,
    community,
    dead_code,
    impact,
    neighbors,
    path_between,
)

__all__ = [
    "DEFAULT_DEAD_CODE_LIMIT",
    "DEFAULT_IMPACT_DEPTH",
    "DEFAULT_LIMIT",
    "DEFAULT_NEIGHBOR_HOPS",
    "DEPENDENCY_RELATIONS",
    "SCHEMA_VERSION",
    "AmbiguousSymbolError",
    "EdgeDirection",
    "GraphArtifactInvalidError",
    "GraphArtifactMissingError",
    "GraphQueryError",
    "GraphQueryResult",
    "GraphRelation",
    "GraphRow",
    "GraphVerb",
    "SymbolGraph",
    "UnknownSymbolError",
    "callees_of",
    "callers_of",
    "community",
    "dead_code",
    "impact",
    "load_symbol_graph",
    "neighbors",
    "path_between",
    "render_json",
    "render_markdown",
    "resolve_symbol",
]
