"""Generate the symbol-level knowledge graph under `.context/features/`.

Builds a NetworkX graph from the AST extraction (the same `extraction` dict
runner.build_all already computes), clusters into communities, and writes
`symbol-graph.json`. Deterministic — no LLM calls.

v0.6: the symbol graph moved from `.context/graph/graph.json` to
`.context/features/symbol-graph.json`. The pyvis HTML hairball was dropped
entirely — the feature-level viewer at `.context/features/graph.html` is the
human-facing visualization now (see features.py).

Reuses dummyindex's existing pipeline (build, cluster, export) instead of
reimplementing them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dummyindex.analysis.cluster import cluster
from dummyindex.context.domains.atomic_io import normalize_eof_newline
from dummyindex.export import to_json as _export_to_json
from dummyindex.pipeline.build import build_from_json


@dataclass(frozen=True)
class GraphResult:
    json_path: Path
    node_count: int
    edge_count: int
    community_count: int


def build_graph(extraction: dict, features_dir: Path) -> GraphResult:
    """Build the raw NetworkX symbol graph and write it under ``features_dir``.

    Writes ``<features_dir>/symbol-graph.json`` (NetworkX node-link with Leiden
    communities). The feature scaffolder consumes this as its input.
    """
    features_dir.mkdir(parents=True, exist_ok=True)

    g = build_from_json(extraction, directed=False)
    communities = cluster(g)

    json_path = features_dir / "symbol-graph.json"
    _export_to_json(g, communities, str(json_path))
    # The shared exporter ends without a final newline; this artifact is
    # *committed* in consumer repos, so it must pass end-of-file-fixer.
    normalize_eof_newline(json_path)

    return GraphResult(
        json_path=json_path,
        node_count=g.number_of_nodes(),
        edge_count=g.number_of_edges(),
        community_count=len(communities),
    )
