"""Generate the symbol-level knowledge graph under `.context/features/`.

Builds a NetworkX graph from the AST extraction `runner.build_all` already computes,
clusters it into communities and writes `symbol-graph.json`; deterministic, no LLM
calls. It then derives `seed-rank.json` and `graph-communities.json` from the same graph
(`build.communities`); their failure never blocks the symbol graph itself.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from dummyindex.analysis.cluster import cluster
from dummyindex.context.build.communities import write_graph_artifacts
from dummyindex.context.build.portable_graph import normalize_extraction_paths
from dummyindex.context.domains.atomic_io import normalize_eof_newline
from dummyindex.export import to_json as _export_to_json
from dummyindex.pipeline.build import build_from_json


@dataclass(frozen=True)
class GraphResult:
    json_path: Path
    node_count: int
    edge_count: int
    community_count: int
    # `.context/`-relative names of the derived artifacts written after the
    # graph (seed-rank + graph-communities); empty when their step failed.
    artifacts: tuple[str, ...] = ()


def build_graph(
    extraction: dict, features_dir: Path, *, root: Path | None = None
) -> GraphResult:
    """Build the raw NetworkX symbol graph and write it under ``features_dir``.

    Writes ``<features_dir>/symbol-graph.json`` (NetworkX node-link with Louvain
    communities). The feature scaffolder consumes this as its input. Then
    derives ``seed-rank.json`` + ``graph-communities.json`` from the same
    graph (see `build.communities`); ``root`` anchors their `path:line`
    citations and defaults to the ingest root recorded in `meta.json`.
    """
    features_dir.mkdir(parents=True, exist_ok=True)

    if (
        root is None
        and features_dir.name == "features"
        and features_dir.parent.name == ".context"
    ):
        root = features_dir.parent.parent
    if root is not None:
        extraction = normalize_extraction_paths(extraction, root)
    g = build_from_json(extraction, directed=False)
    communities = cluster(g)

    json_path = features_dir / "symbol-graph.json"
    _export_to_json(g, communities, str(json_path))
    # The shared exporter ends without a final newline; this artifact is
    # *committed* in consumer repos, so it must pass end-of-file-fixer.
    normalize_eof_newline(json_path)

    artifacts: tuple[str, ...] = ()
    try:
        artifacts = write_graph_artifacts(g, communities, features_dir, root=root)
    except Exception as exc:
        # Same tolerance the callers extend to this module: the derived
        # artifacts are secondary to the graph they derive from.
        warnings.warn(
            f"graph artifact generation failed: {exc!r}; "
            "continuing without seed-rank/graph-communities",
            stacklevel=2,
        )

    return GraphResult(
        json_path=json_path,
        node_count=g.number_of_nodes(),
        edge_count=g.number_of_edges(),
        community_count=len(communities),
        artifacts=artifacts,
    )
