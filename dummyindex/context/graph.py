"""Generate a knowledge graph of the codebase under `.context/graph/`.

Builds a NetworkX graph from the AST extraction (the same `extraction` dict
runner.build_all already computes), clusters into communities, and writes
`graph.json` + best-effort `graph.html`. Deterministic — no LLM calls.

Reuses dummyindex's existing pipeline (build, cluster, export) instead of
reimplementing them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dummyindex.analysis.cluster import cluster
from dummyindex.pipeline.build import build_from_json
from dummyindex.pipeline.export import to_html as _export_to_html
from dummyindex.pipeline.export import to_json as _export_to_json


@dataclass(frozen=True)
class GraphResult:
    json_path: Path
    html_path: Optional[Path]
    node_count: int
    edge_count: int
    community_count: int
    html_skipped_reason: Optional[str] = None


def build_graph(
    extraction: dict,
    graph_dir: Path,
    *,
    write_html: bool = True,
) -> GraphResult:
    """Build and write graph.json + optional graph.html under `graph_dir`."""
    graph_dir.mkdir(parents=True, exist_ok=True)

    g = build_from_json(extraction, directed=False)
    communities = cluster(g)

    json_path = graph_dir / "graph.json"
    _export_to_json(g, communities, str(json_path))

    html_path: Optional[Path] = None
    html_skipped_reason: Optional[str] = None
    if write_html:
        target = graph_dir / "graph.html"
        try:
            _export_to_html(g, communities, str(target))
            html_path = target
        except ValueError as exc:
            # Most common: graph too large (MAX_NODES_FOR_VIZ exceeded).
            # JSON is still useful; just skip the HTML viewer.
            html_skipped_reason = str(exc)

    return GraphResult(
        json_path=json_path,
        html_path=html_path,
        node_count=g.number_of_nodes(),
        edge_count=g.number_of_edges(),
        community_count=len(communities),
        html_skipped_reason=html_skipped_reason,
    )
