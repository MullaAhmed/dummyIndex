"""Bounded, cited query verbs over ``features/symbol-graph.json``.

`dummyindex context graph <verb>` answers caller / callee / impact / path /
neighborhood / dead-code / community questions from the full extracted
symbol graph — the node-link artifact the curated scan deliberately keeps
off-screen. No database, no LLM, no new store: the artifact is loaded
read-only into a directed multigraph and every answer is bounded
(``--limit`` / depth caps) and cited (``source_file:source_location``),
with docstrings attached from co-located ``rationale_for`` nodes.

Wire notes (pinned by tests): the artifact is an **undirected** networkx
node-link export whose links live under the ``links`` key. networkx
normalises ``source``/``target`` on undirected graphs, so the true
direction of every link is carried in its ``_src``/``_tgt`` attributes —
``_src calls _tgt``, ``_src rationale_for _tgt`` — and the loader reads
only those (``load.py``).

**Dead-code is purely graph-driven.** A code node is reported when it has
zero incoming dependency edges (``calls`` / ``uses`` / ``imports_from`` /
``inherits``); the structural relations (``contains``, ``method``,
``rationale_for``) never count as usage. Precision is therefore exactly
the extractor's: symbols reached only through enum-keyed dispatch-dict
values or function-body imports show up as false positives today. The A4
extractor fix emits real ``calls`` / ``imports_from`` edges for those
idioms, and because the verb re-derives from edges on every run, those
new edges remove the false positives automatically — no change needed
here.
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
