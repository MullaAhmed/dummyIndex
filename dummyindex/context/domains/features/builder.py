"""`scaffold_features` — turn a clustered graph into per-feature folders.

Two passes (both deterministic):
  1. **Community-based features** — every Leiden community becomes one.
  2. **Entry-point-based flows** — in-degree-0 functions in the call
     sub-graph are likely user-facing entry points; a BFS over the call
     graph captures the ordered flow of calls; the flow gets attached to
     the community that contains its entry point.

`_trace_flow` is the BFS. `_write_all` writes the on-disk scaffolding.
"""
from __future__ import annotations
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from dummyindex.context.output.viewer import VIEWER_HTML

from ._constants import _CALL_RELATIONS, _DEFAULT_FLOW_DEPTH, SCHEMA_VERSION
from ._helpers import _rel, _range_from_location, _unique_paths, _write_json, _write_text
from .docs import _write_feature_docs
from .models import Feature, Flow, FlowStep, ScaffoldResult
from .render import (
    _stub_feature_readme,
    _stub_flow_md,
    _index_md,
    _how_to_navigate_md,
    _graph_view,
)

if TYPE_CHECKING:
    from dummyindex.context.domains.source_docs import DocCatalog


def scaffold_features(
    context_dir: Path,
    graph_data: dict[str, Any],
    *,
    root: Optional[Path] = None,
    flow_depth: int = _DEFAULT_FLOW_DEPTH,
    doc_catalog: Optional["DocCatalog"] = None,
) -> ScaffoldResult:
    """Build feature + flow scaffolding from a NetworkX node-link graph.

    Caller owns `graph_data` (the same dict already written to
    `.context/graph/graph.json`). This function does not re-read it.

    `root`, when given, is the project root used to rewrite the absolute
    `source_file` values that come out of `graph_data` into repo-relative
    POSIX paths (so `feature.json` / `flow.json` match `tree.json` and
    `map/symbols.json`).

    ``doc_catalog``, when given, is consulted to write a per-feature
    ``docs.md`` pointer list — each entry is a relative link to a
    catalogued doc that mentions one of the feature's files or symbols.
    Docs are stored as pointers (not copied content) so the catalog's
    staleness signals stay authoritative.
    """
    root_abs = root.resolve() if root is not None else None

    nodes = graph_data.get("nodes", []) or []
    edges = graph_data.get("links", graph_data.get("edges", [])) or []
    if not nodes:
        return ScaffoldResult(
            features_dir=context_dir / "features",
            features=(),
            flows=(),
            written=(),
        )

    node_by_id = {n["id"]: n for n in nodes if "id" in n}
    by_community: dict[Any, list[str]] = defaultdict(list)
    for n in nodes:
        if "id" not in n:
            continue
        by_community[n.get("community", -1)].append(n["id"])

    call_edges = [e for e in edges if e.get("relation") in _CALL_RELATIONS]
    in_deg: dict[str, int] = defaultdict(int)
    out_neighbors: dict[str, list[str]] = defaultdict(list)
    for e in call_edges:
        s, t = e.get("source"), e.get("target")
        if not s or not t:
            continue
        in_deg[t] += 1
        out_neighbors[s].append(t)

    # Entry points: have out-edges but no in-edges in the call subgraph.
    entry_points = sorted(
        nid
        for nid in node_by_id
        if out_neighbors.get(nid) and in_deg.get(nid, 0) == 0
    )

    features: list[Feature] = []
    flows: list[Flow] = []
    flow_counter = 0
    for community_id, member_ids in sorted(
        by_community.items(), key=lambda kv: str(kv[0])
    ):
        member_ids_sorted = sorted(member_ids)
        community_files = _unique_paths(
            _rel(node_by_id[m].get("source_file"), root_abs)
            for m in member_ids_sorted
        )
        members_set = set(member_ids_sorted)
        community_eps = [ep for ep in entry_points if ep in members_set]

        feature_id = f"community-{community_id}" if community_id != -1 else "community-unassigned"
        feature_name = feature_id  # deterministic; skill renames later

        feature_flows: list[Flow] = []
        for ep in community_eps:
            flow_counter += 1
            flow_id = f"flow-{flow_counter:03d}"
            steps = _trace_flow(
                ep, out_neighbors, node_by_id, max_depth=flow_depth, root_abs=root_abs
            )
            flow_files = _unique_paths(s.path for s in steps)
            ep_node = node_by_id[ep]
            flow = Flow(
                flow_id=flow_id,
                feature_id=feature_id,
                entry_point=ep,
                entry_point_label=ep_node.get("label", ep),
                entry_point_path=_rel(ep_node.get("source_file"), root_abs),
                steps=steps,
                files=flow_files,
            )
            feature_flows.append(flow)

        feature = Feature(
            feature_id=feature_id,
            kind="community",
            name=feature_name,
            summary=None,
            members=tuple(member_ids_sorted),
            files=community_files,
            entry_points=tuple(community_eps),
            flow_ids=tuple(f.flow_id for f in feature_flows),
        )
        features.append(feature)
        flows.extend(feature_flows)

    features_dir = context_dir / "features"
    written = _write_all(features_dir, tuple(features), tuple(flows))

    # Per-feature docs.md pointer list. The catalog stays authoritative
    # for confidence/staleness — features/<id>/docs.md is just a routing
    # convenience.
    if doc_catalog is not None and doc_catalog.docs:
        feature_docs_written = _write_feature_docs(
            features_dir, tuple(features), doc_catalog, node_by_id
        )
        written = written + feature_docs_written

    return ScaffoldResult(
        features_dir=features_dir,
        features=tuple(features),
        flows=tuple(flows),
        written=written,
    )


# ----- atomic rename + metadata update --------------------------------------
def _trace_flow(
    entry: str,
    out_neighbors: dict[str, list[str]],
    node_by_id: dict[str, dict],
    *,
    max_depth: int,
    root_abs: Optional[Path] = None,
) -> tuple[FlowStep, ...]:
    """BFS over the call graph from `entry`, recording each visited
    node with its discovery depth. Cap at `max_depth` to keep flows
    bounded on cyclic / deeply nested call graphs.
    """
    seen: set[str] = {entry}
    steps: list[FlowStep] = []
    queue: deque[tuple[str, int]] = deque([(entry, 0)])
    while queue:
        nid, depth = queue.popleft()
        node = node_by_id.get(nid, {})
        steps.append(
            FlowStep(
                depth=depth,
                node_id=nid,
                label=node.get("label", nid),
                path=_rel(node.get("source_file"), root_abs),
                range=_range_from_location(node.get("source_location")),
            )
        )
        if depth >= max_depth:
            continue
        for nb in out_neighbors.get(nid, []):
            if nb not in seen:
                seen.add(nb)
                queue.append((nb, depth + 1))
    return tuple(steps)

def _write_all(
    features_dir: Path,
    features: tuple[Feature, ...],
    flows: tuple[Flow, ...],
) -> tuple[str, ...]:
    features_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    # Per-feature folders + flow files.
    flows_by_feature: dict[str, list[Flow]] = defaultdict(list)
    for f in flows:
        flows_by_feature[f.feature_id].append(f)

    for feat in features:
        f_dir = features_dir / feat.feature_id
        f_dir.mkdir(parents=True, exist_ok=True)
        _write_json(f_dir / "feature.json", feat.to_dict())
        written.append(f"features/{feat.feature_id}/feature.json")

        _write_text(
            f_dir / "README.md",
            _stub_feature_readme(feat, flows_by_feature.get(feat.feature_id, [])),
        )
        written.append(f"features/{feat.feature_id}/README.md")

        if flows_by_feature.get(feat.feature_id):
            flows_dir = f_dir / "flows"
            flows_dir.mkdir(parents=True, exist_ok=True)
            for flow in flows_by_feature[feat.feature_id]:
                _write_json(flows_dir / f"{flow.flow_id}.json", flow.to_dict())
                _write_text(
                    flows_dir / f"{flow.flow_id}.md",
                    _stub_flow_md(flow),
                )
                written.append(
                    f"features/{feat.feature_id}/flows/{flow.flow_id}.json"
                )
                written.append(
                    f"features/{feat.feature_id}/flows/{flow.flow_id}.md"
                )

    # Top-level INDEX.json (the canonical agent-readable map).
    _write_json(
        features_dir / "INDEX.json",
        {
            "schema_version": SCHEMA_VERSION,
            "features": [
                {
                    "feature_id": f.feature_id,
                    "kind": f.kind,
                    "name": f.name,
                    "summary": f.summary,
                    "member_count": len(f.members),
                    "file_count": len(f.files),
                    "entry_point_count": len(f.entry_points),
                    "flow_count": len(f.flow_ids),
                    "confidence": f.confidence,
                    "path": f"features/{f.feature_id}/",
                }
                for f in features
            ],
            "flow_count": len(flows),
        },
    )
    written.append("features/INDEX.json")

    # Human-readable index.
    _write_text(features_dir / "INDEX.md", _index_md(features, flows))
    written.append("features/INDEX.md")

    # Navigation guide for the agent.
    _write_text(
        features_dir / "HOW_TO_NAVIGATE.md", _how_to_navigate_md()
    )
    written.append("features/HOW_TO_NAVIGATE.md")

    # Denormalized data for the HTML viewer.
    _write_json(features_dir / "graph.json", _graph_view(features, flows))
    written.append("features/graph.json")

    # Static HTML viewer (human-facing visualization).
    _write_text(features_dir / "graph.html", VIEWER_HTML)
    written.append("features/graph.html")

    return tuple(written)

