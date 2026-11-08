"""`scaffold_features` — turn a clustered graph into per-feature folders.

Each graph community becomes a feature; each in-degree-0 call-graph node seeds
a BFS flow (`_trace_flow`) attached to its community. `_write_all` writes disk.
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dummyindex.context.output.viewer import render_viewer_html

from .constants import _CALL_RELATIONS, _DEFAULT_FLOW_DEPTH, SCHEMA_VERSION
from .docs import _write_feature_docs
from .helpers import (
    _project_name,
    _range_from_location,
    _rel,
    _unique_paths,
    _write_json,
    _write_text,
)
from .models import Feature, Flow, FlowStep, ScaffoldResult
from .render import (
    _graph_view,
    _how_to_navigate_md,
    _index_md,
    _stub_feature_spec,
    _stub_flow_md,
)
from .scan import SeedRank, load_seed_rank

if TYPE_CHECKING:
    from dummyindex.context.domains.source_docs import DocCatalog


def scaffold_features(
    context_dir: Path,
    graph_data: dict[str, Any],
    *,
    root: Path | None = None,
    flow_depth: int = _DEFAULT_FLOW_DEPTH,
    doc_catalog: DocCatalog | None = None,
) -> ScaffoldResult:
    """Build feature + flow scaffolding from a NetworkX node-link graph.

    Caller owns `graph_data` (already on disk; not re-read). `root`, when given,
    rewrites absolute `source_file` values to repo-relative POSIX paths so
    `feature.json`/`flow.json` match `tree.json` and `map/symbols.json`.
    `doc_catalog`, when given, adds a per-feature `docs.md` of links to catalogued
    docs mentioning the feature — pointers, so the catalog stays authoritative.
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
        s = e.get("_src", e.get("source"))
        t = e.get("_tgt", e.get("target"))
        if not s or not t:
            continue
        in_deg[t] += 1
        out_neighbors[s].append(t)

    # Entry points: have out-edges but no in-edges in the call subgraph.
    entry_points = sorted(
        nid for nid in node_by_id if out_neighbors.get(nid) and in_deg.get(nid, 0) == 0
    )

    features: list[Feature] = []
    flows: list[Flow] = []
    flow_counter = 0
    for community_id, member_ids in sorted(
        by_community.items(), key=lambda kv: str(kv[0])
    ):
        member_ids_sorted = sorted(member_ids)
        community_files = _unique_paths(
            _rel(node_by_id[m].get("source_file"), root_abs) for m in member_ids_sorted
        )
        members_set = set(member_ids_sorted)
        community_eps = [ep for ep in entry_points if ep in members_set]

        # All-`__init__.py` communities with no entry points are empty
        # re-export hubs clustered by isolated parse-time edges; drop them
        # here so the trivial filter and the architect never see them.
        if _is_parser_artifact(community_files, community_eps):
            continue

        feature_id = (
            f"community-{community_id}"
            if community_id != -1
            else "community-unassigned"
        )
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
    written = _write_all(
        features_dir,
        tuple(features),
        tuple(flows),
        project_name=_project_name(context_dir, root),
        # The caller's node-link graph is already in memory; the scan seed
        # uses its call edges to connect features that no surviving flow
        # happens to cross.
        links=tuple(graph_data.get("links") or ()),
        # The ranked shortlist is read from disk, not recomputed: the
        # rebuild path (`rebuild_features_graph`) reads the same artifact,
        # and two sources for one fact is how the two paths would drift.
        rank=load_seed_rank(features_dir),
    )

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


# --- parser-artifact filter
def _is_parser_artifact(
    files: tuple[str, ...] | list[str],
    entry_points: list[str] | tuple[str, ...],
) -> bool:
    """True when a community is just empty-`__init__.py` noise.

    Requires every file to be ``__init__.py`` (a re-export hub or rationale
    fragment) and no entry points (an init that defines callables has some).
    """
    if not files:
        return False
    if entry_points:
        return False
    return all(p.endswith("__init__.py") for p in files)


# --- flow tracing
def _trace_flow(
    entry: str,
    out_neighbors: dict[str, list[str]],
    node_by_id: dict[str, dict],
    *,
    max_depth: int,
    root_abs: Path | None = None,
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
    *,
    project_name: str,
    links: tuple[dict[str, Any], ...] = (),
    rank: SeedRank | None = None,
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
            f_dir / "spec.md",
            _stub_feature_spec(feat, flows_by_feature.get(feat.feature_id, [])),
        )
        written.append(f"features/{feat.feature_id}/spec.md")

        if flows_by_feature.get(feat.feature_id):
            flows_dir = f_dir / "flows"
            flows_dir.mkdir(parents=True, exist_ok=True)
            for flow in flows_by_feature[feat.feature_id]:
                _write_json(flows_dir / f"{flow.flow_id}.json", flow.to_dict())
                _write_text(
                    flows_dir / f"{flow.flow_id}.md",
                    _stub_flow_md(flow),
                )
                written.append(f"features/{feat.feature_id}/flows/{flow.flow_id}.json")
                written.append(f"features/{feat.feature_id}/flows/{flow.flow_id}.md")

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
    _write_text(features_dir / "HOW_TO_NAVIGATE.md", _how_to_navigate_md())
    written.append("features/HOW_TO_NAVIGATE.md")

    # Curated scan (schema v2) + viewer. Deterministic seed only (EXTRACTED,
    # features as `service`, flows as `entry`); the council rewrites it.
    # Per-symbol navigation lives in `map/symbols.json`/`symbol-graph.json`.
    scan = _graph_view(
        features, flows, project_name=project_name, links=links, rank=rank
    )
    _write_json(features_dir / "graph.json", scan)
    written.append("features/graph.json")

    _write_text(
        features_dir / "graph.html",
        render_viewer_html(scan, features_dir=features_dir),
    )
    written.append("features/graph.html")

    return tuple(written)
