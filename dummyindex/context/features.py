"""Detect features and flows; emit `.context/features/`.

Two passes, both deterministic:

1. **Community-based features** — every Leiden community in
   `graph/graph.json` becomes a candidate feature. Covers the whole
   codebase coarsely.
2. **Entry-point-based flows** — functions with in-degree 0 in the
   call subgraph (`calls` / `uses` edges) are likely user-facing entry
   points (HTTP handlers, CLI commands, public APIs). For each, a BFS
   over the call graph captures the ordered flow of calls. The flow
   gets attached to the community that contains its entry point.

Output:

    .context/features/
    ├── INDEX.json             # machine-readable list (the agent's nav)
    ├── INDEX.md               # human-readable summary
    ├── HOW_TO_NAVIGATE.md     # agent navigation guide
    ├── graph.json             # denormalized graph for the HTML viewer
    └── <feature-id>/
        ├── feature.json       # canonical machine description
        ├── README.md          # human-readable stub
        └── flows/
            ├── <flow-id>.json # ordered call sequence
            └── <flow-id>.md   # human-readable flow doc

The /dummyindex skill enriches names / summaries / flow narratives on
top of this scaffolding (every node carries `confidence: "EXTRACTED"`
initially; enrichment flips to `"INFERRED"`).
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 1

# Hard cap so flows don't blow up on deep call chains. Tunable.
_DEFAULT_FLOW_DEPTH = 6

# Call-like relations that count toward "this function leads to that one".
_CALL_RELATIONS = frozenset({"calls", "uses"})


# ----- data shapes ----------------------------------------------------------


@dataclass(frozen=True)
class FlowStep:
    depth: int
    node_id: str
    label: str
    path: Optional[str]
    range: Optional[list[int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "node_id": self.node_id,
            "label": self.label,
            "path": self.path,
            "range": self.range,
        }


@dataclass(frozen=True)
class Flow:
    flow_id: str
    feature_id: str
    entry_point: str
    entry_point_label: str
    entry_point_path: Optional[str]
    steps: tuple[FlowStep, ...]
    files: tuple[str, ...]
    confidence: str = "EXTRACTED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "flow_id": self.flow_id,
            "feature_id": self.feature_id,
            "entry_point": self.entry_point,
            "entry_point_label": self.entry_point_label,
            "entry_point_path": self.entry_point_path,
            "steps": [s.to_dict() for s in self.steps],
            "files": list(self.files),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Feature:
    feature_id: str
    kind: str  # "community" for now; "entry_point_group" reserved
    name: str
    summary: Optional[str]
    members: tuple[str, ...]
    files: tuple[str, ...]
    entry_points: tuple[str, ...]
    flow_ids: tuple[str, ...]
    confidence: str = "EXTRACTED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "feature_id": self.feature_id,
            "kind": self.kind,
            "name": self.name,
            "summary": self.summary,
            "members": list(self.members),
            "files": list(self.files),
            "entry_points": list(self.entry_points),
            "flow_ids": list(self.flow_ids),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ScaffoldResult:
    features_dir: Path
    features: tuple[Feature, ...]
    flows: tuple[Flow, ...]
    written: tuple[str, ...]


@dataclass(frozen=True)
class RenameResult:
    from_id: str
    to_id: str
    new_name: Optional[str]
    new_summary: Optional[str]
    files_touched: tuple[str, ...]


class FeatureRenameError(ValueError):
    """Raised when `rename_feature` can't safely complete the rename."""


# ----- public entry point ---------------------------------------------------


def scaffold_features(
    context_dir: Path,
    graph_data: dict[str, Any],
    *,
    root: Optional[Path] = None,
    flow_depth: int = _DEFAULT_FLOW_DEPTH,
) -> ScaffoldResult:
    """Build feature + flow scaffolding from a NetworkX node-link graph.

    Caller owns `graph_data` (the same dict already written to
    `.context/graph/graph.json`). This function does not re-read it.

    `root`, when given, is the project root used to rewrite the absolute
    `source_file` values that come out of `graph_data` into repo-relative
    POSIX paths (so `feature.json` / `flow.json` match `tree.json` and
    `map/symbols.json`).
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

    return ScaffoldResult(
        features_dir=features_dir,
        features=tuple(features),
        flows=tuple(flows),
        written=written,
    )


# ----- atomic rename + metadata update --------------------------------------


_SLUG_RE_OK = "abcdefghijklmnopqrstuvwxyz0123456789-_"


def _validate_feature_id(value: str) -> str:
    """Reject feature_ids that aren't safe as folder names."""
    if not value:
        raise FeatureRenameError("feature id must not be empty")
    lowered = value.strip().lower()
    if any(ch not in _SLUG_RE_OK for ch in lowered):
        raise FeatureRenameError(
            f"feature id {value!r} must be lowercase letters, digits, '-', '_'"
        )
    if lowered.startswith("-") or lowered.endswith("-"):
        raise FeatureRenameError(f"feature id {value!r} must not start/end with '-'")
    return lowered


def rename_feature(
    features_dir: Path,
    *,
    from_id: str,
    to_id: str,
    new_name: Optional[str] = None,
    new_summary: Optional[str] = None,
) -> RenameResult:
    """Atomically rename a feature folder and refresh every JSON reference.

    Updates: ``<features_dir>/<from_id>/``  →  ``<features_dir>/<to_id>/``,
    plus the ``feature_id`` / ``name`` / ``summary`` fields in
    ``feature.json``, the ``feature_id`` in every nested ``flows/*.json``,
    and the matching entries in ``INDEX.json`` and ``graph.json``.

    Idempotent: passing ``from_id == to_id`` only refreshes metadata.
    Setting ``new_name`` / ``new_summary`` flips the touched feature's
    ``confidence`` to ``INFERRED``.
    """
    features_dir = features_dir.resolve()
    to_id = _validate_feature_id(to_id)
    from_id = from_id.strip()

    src = features_dir / from_id
    dst = features_dir / to_id
    if not src.is_dir():
        raise FeatureRenameError(
            f"feature folder {src} not found; valid ids: "
            f"{sorted(p.name for p in features_dir.iterdir() if p.is_dir())}"
        )
    if dst.exists() and dst != src:
        raise FeatureRenameError(
            f"target {dst} already exists; pick a different `to` id"
        )

    touched: list[str] = []

    if dst != src:
        src.rename(dst)
        touched.append(f"features/{to_id}/")

    # Refresh feature.json
    feature_json_path = dst / "feature.json"
    if feature_json_path.exists():
        payload = json.loads(feature_json_path.read_text(encoding="utf-8"))
        payload["feature_id"] = to_id
        if new_name is not None:
            payload["name"] = new_name
        elif payload.get("name") == from_id:
            payload["name"] = to_id
        if new_summary is not None:
            payload["summary"] = new_summary
        if new_name is not None or new_summary is not None:
            payload["confidence"] = "INFERRED"
        _write_json(feature_json_path, payload)
        touched.append(f"features/{to_id}/feature.json")

    # Refresh every flow.json under flows/
    flows_dir = dst / "flows"
    if flows_dir.is_dir():
        for flow_path in sorted(flows_dir.glob("*.json")):
            payload = json.loads(flow_path.read_text(encoding="utf-8"))
            if payload.get("feature_id") != to_id:
                payload["feature_id"] = to_id
                _write_json(flow_path, payload)
                touched.append(f"features/{to_id}/flows/{flow_path.name}")

    # Refresh INDEX.json (machine) and INDEX.md (human).
    index_path = features_dir / "INDEX.json"
    if index_path.exists():
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        changed_index = False
        for entry in index_payload.get("features", []):
            if entry.get("feature_id") == from_id or entry.get("feature_id") == to_id:
                entry["feature_id"] = to_id
                entry["path"] = f"features/{to_id}/"
                if new_name is not None:
                    entry["name"] = new_name
                elif entry.get("name") == from_id:
                    entry["name"] = to_id
                if new_summary is not None:
                    entry["summary"] = new_summary
                if new_name is not None or new_summary is not None:
                    entry["confidence"] = "INFERRED"
                changed_index = True
        if changed_index:
            _write_json(index_path, index_payload)
            touched.append("features/INDEX.json")
            # Rebuild the human-readable INDEX.md from the updated INDEX.json
            # so its links don't 404 after a rename.
            _write_text(
                features_dir / "INDEX.md",
                _index_md_from_index_json(index_payload),
            )
            touched.append("features/INDEX.md")

    # Refresh the viewer's graph.json
    graph_view_path = features_dir / "graph.json"
    if graph_view_path.exists():
        gv = json.loads(graph_view_path.read_text(encoding="utf-8"))
        changed_gv = False
        for n in gv.get("nodes", []):
            if n.get("id") == from_id:
                n["id"] = to_id
                if new_name is not None:
                    n["label"] = new_name
                elif n.get("label") == from_id:
                    n["label"] = to_id
                changed_gv = True
            elif n.get("kind") == "flow" and n.get("feature_id") == from_id:
                n["feature_id"] = to_id
                changed_gv = True
        for e in gv.get("edges", []):
            if e.get("source") == from_id:
                e["source"] = to_id
                changed_gv = True
            if e.get("target") == from_id:
                e["target"] = to_id
                changed_gv = True
        if changed_gv:
            _write_json(graph_view_path, gv)
            touched.append("features/graph.json")

    return RenameResult(
        from_id=from_id,
        to_id=to_id,
        new_name=new_name,
        new_summary=new_summary,
        files_touched=tuple(touched),
    )


# ----- flow tracing ---------------------------------------------------------


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


def _rel(p: Any, root_abs: Optional[Path]) -> Optional[str]:
    """Coerce a `source_file` value to a repo-relative POSIX path.

    Returns the raw value if it doesn't look like a string or if it's
    already outside `root_abs`. None if not a string.
    """
    if not isinstance(p, str) or not p:
        return None
    if root_abs is None:
        return p
    try:
        return Path(p).resolve().relative_to(root_abs).as_posix()
    except ValueError:
        return p


def _range_from_location(loc: Any) -> Optional[list[int]]:
    """Parse a source_location like 'L13' or 'L13-L17' into [start, end]."""
    if not isinstance(loc, str):
        return None
    s = loc.strip().lstrip("L")
    if "-" in s:
        a, b = s.split("-", 1)
        try:
            return [int(a.lstrip("L")), int(b.lstrip("L"))]
        except ValueError:
            return None
    try:
        n = int(s)
        return [n, n]
    except ValueError:
        return None


def _unique_paths(paths: Iterable[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if not isinstance(p, str) or not p:
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return tuple(sorted(out))


# ----- writers --------------------------------------------------------------


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
    _write_text(features_dir / "graph.html", _GRAPH_HTML)
    written.append("features/graph.html")

    return tuple(written)


def _write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, body: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


# ----- markdown / json templates --------------------------------------------


def _stub_feature_readme(feat: Feature, flows: list[Flow]) -> str:
    lines: list[str] = []
    lines.append(f"# Feature: {feat.name}")
    lines.append("")
    lines.append(
        f"_Deterministic stub (`confidence: {feat.confidence}`). The `/dummyindex` "
        "skill will rename this folder and rewrite this file with a real summary "
        "based on the source code._"
    )
    lines.append("")
    lines.append("## At a glance")
    lines.append("")
    lines.append(f"- **Members:** {len(feat.members)} symbol(s)")
    lines.append(f"- **Files:** {len(feat.files)}")
    lines.append(f"- **Entry points:** {len(feat.entry_points)}")
    lines.append(f"- **Flows:** {len(flows)}")
    lines.append("")
    if feat.files:
        lines.append("## Files involved")
        lines.append("")
        for fp in feat.files:
            lines.append(f"- `{fp}`")
        lines.append("")
    if flows:
        lines.append("## Flows")
        lines.append("")
        for flow in flows:
            lines.append(
                f"- [`{flow.flow_id}`](./flows/{flow.flow_id}.md) — entry: "
                f"`{flow.entry_point_label}` "
                f"({len(flow.steps)} steps, {len(flow.files)} files)"
            )
        lines.append("")
    if feat.entry_points:
        lines.append("## Entry points")
        lines.append("")
        for ep in feat.entry_points:
            lines.append(f"- `{ep}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def _stub_flow_md(flow: Flow) -> str:
    lines: list[str] = []
    lines.append(f"# Flow: {flow.flow_id}")
    lines.append("")
    lines.append(
        f"_Deterministic trace from a BFS over `calls` edges (`confidence: "
        f"{flow.confidence}`). The `/dummyindex` skill will rewrite this file "
        "with a plain-language narrative._"
    )
    lines.append("")
    lines.append(
        f"**Entry point:** `{flow.entry_point_label}` "
        f"(`{flow.entry_point_path or '?'}`)"
    )
    lines.append("")
    lines.append("## Steps")
    lines.append("")
    for s in flow.steps:
        indent = "  " * s.depth
        loc = ""
        if s.path and s.range:
            loc = f" — `{s.path}:{s.range[0]}`"
        elif s.path:
            loc = f" — `{s.path}`"
        lines.append(f"{indent}- `{s.label}`{loc}")
    lines.append("")
    if flow.files:
        lines.append("## Files touched")
        lines.append("")
        for fp in flow.files:
            lines.append(f"- `{fp}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def _index_md(features: tuple[Feature, ...], flows: tuple[Flow, ...]) -> str:
    lines = [
        "# Features",
        "",
        f"_{len(features)} feature(s), {len(flows)} flow(s). Stubs derived from "
        "graph communities (Leiden) + entry-point traces (in-degree 0 in the "
        "call subgraph). The `/dummyindex` skill renames, regroups, and "
        "summarizes._",
        "",
        "| Feature | Members | Files | Entry points | Flows |",
        "|---|---|---|---|---|",
    ]
    for f in features:
        lines.append(
            f"| [`{f.name}`](./{f.feature_id}/) | {len(f.members)} | "
            f"{len(f.files)} | {len(f.entry_points)} | {len(f.flow_ids)} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def refresh_features_index_md(features_dir: Path) -> Path:
    """Rebuild ``<features_dir>/INDEX.md`` from the canonical INDEX.json.

    Use after a session of `features-rename` calls so the human-readable
    table reflects the renamed features. Raises ``FileNotFoundError`` if
    ``features/INDEX.json`` doesn't exist (no scaffolding to refresh).
    """
    index_json_path = features_dir / "INDEX.json"
    if not index_json_path.exists():
        raise FileNotFoundError(index_json_path)
    payload = json.loads(index_json_path.read_text(encoding="utf-8"))
    out_path = features_dir / "INDEX.md"
    _write_text(out_path, _index_md_from_index_json(payload))
    return out_path


def remove_flow(
    features_dir: Path,
    *,
    feature_id: str,
    flow_id: str,
) -> RenameResult:
    """Atomically delete a flow from a feature.

    Used by the senior-developer council agent to drop noise flows
    (private helpers misdetected as entry points, enum classes,
    trivially-traced sequences). Touches:

    - ``features/<feature_id>/flows/<flow_id>.{json,md}`` — deleted.
    - ``features/<feature_id>/feature.json`` — `flow_ids` filtered.
    - ``features/INDEX.json`` — `flow_count` decremented for the feature,
      top-level `flow_count` decremented.
    - ``features/graph.json`` — flow node + its edges removed.

    Idempotent: re-running on a missing flow is a no-op (no error).
    """
    features_dir = features_dir.resolve()
    feat_dir = features_dir / feature_id
    if not feat_dir.is_dir():
        raise FeatureRenameError(
            f"feature folder {feat_dir} not found"
        )

    touched: list[str] = []

    flow_json = feat_dir / "flows" / f"{flow_id}.json"
    flow_md = feat_dir / "flows" / f"{flow_id}.md"
    removed_anything = False
    for p in (flow_json, flow_md):
        if p.exists():
            p.unlink()
            touched.append(str(p.relative_to(features_dir.parent)))
            removed_anything = True

    # feature.json
    feature_json = feat_dir / "feature.json"
    if feature_json.exists():
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
        old = list(payload.get("flow_ids", []))
        new = [f for f in old if f != flow_id]
        if old != new:
            payload["flow_ids"] = new
            _write_json(feature_json, payload)
            touched.append(f"features/{feature_id}/feature.json")

    # INDEX.json
    index_path = features_dir / "INDEX.json"
    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        changed_idx = False
        for entry in idx.get("features", []):
            if entry.get("feature_id") == feature_id:
                # Use the current flow_ids count from feature.json if available.
                if feature_json.exists():
                    fp = json.loads(feature_json.read_text(encoding="utf-8"))
                    new_count = len(fp.get("flow_ids", []))
                else:
                    new_count = max(0, entry.get("flow_count", 0) - 1)
                if entry.get("flow_count") != new_count:
                    entry["flow_count"] = new_count
                    changed_idx = True
        if removed_anything:
            idx["flow_count"] = max(0, idx.get("flow_count", 0) - 1)
            changed_idx = True
        if changed_idx:
            _write_json(index_path, idx)
            touched.append("features/INDEX.json")
            _write_text(
                features_dir / "INDEX.md",
                _index_md_from_index_json(idx),
            )
            touched.append("features/INDEX.md")

    # graph.json — drop the flow node + every edge touching it.
    gv_path = features_dir / "graph.json"
    if gv_path.exists():
        gv = json.loads(gv_path.read_text(encoding="utf-8"))
        nodes = gv.get("nodes", []) or []
        edges = gv.get("edges", []) or []
        new_nodes = [n for n in nodes if n.get("id") != flow_id]
        new_edges = [
            e for e in edges
            if e.get("source") != flow_id and e.get("target") != flow_id
        ]
        if len(new_nodes) != len(nodes) or len(new_edges) != len(edges):
            gv["nodes"] = new_nodes
            gv["edges"] = new_edges
            _write_json(gv_path, gv)
            touched.append("features/graph.json")

    return RenameResult(
        from_id=flow_id,
        to_id="",
        new_name=None,
        new_summary=None,
        files_touched=tuple(touched),
    )


def write_section(
    features_dir: Path,
    *,
    feature_id: str,
    section: str,
    source_file: Path,
) -> Path:
    """Atomically place a markdown into ``features/<feature_id>/<section>.md``.

    Section names allowed by the council:
    ``README``, ``architecture``, ``implementation``, ``data-model``,
    ``security``, ``product``. Other names are accepted but a warning is
    surfaced via the return path's parent existence — callers should sanity-check.

    Idempotent: writing the same content twice yields the same file. Uses
    a tmp-file + rename for atomicity.
    """
    features_dir = features_dir.resolve()
    feat_dir = features_dir / feature_id
    if not feat_dir.is_dir():
        raise FeatureRenameError(
            f"feature folder {feat_dir} not found"
        )

    section = section.strip()
    if not section or "/" in section or section.startswith("."):
        raise FeatureRenameError(f"invalid section name: {section!r}")

    # Allow .md extension to be either present or absent.
    target_name = section if section.endswith(".md") else f"{section}.md"
    target = feat_dir / target_name

    if not source_file.exists():
        raise FeatureRenameError(f"source file not found: {source_file}")

    content = source_file.read_text(encoding="utf-8")
    _write_text(target, content)
    return target


def rebuild_features_graph(features_dir: Path) -> tuple[Path, Path]:
    """Regenerate ``graph.json`` + ``graph.html`` from disk.

    Walks ``features/<id>/feature.json`` + ``features/<id>/flows/*.json``
    and re-emits the denormalized viewer payload. Use when the schema
    changed (e.g. you upgraded dummyindex and want the richer folder
    hierarchy in the viewer) without forcing a full re-ingest that
    would clobber LLM-enriched names + summaries.

    Raises ``FileNotFoundError`` if ``features_dir`` doesn't exist.
    """
    if not features_dir.is_dir():
        raise FileNotFoundError(features_dir)

    features: list[Feature] = []
    flows: list[Flow] = []

    for feat_dir in sorted(p for p in features_dir.iterdir() if p.is_dir()):
        feature_json = feat_dir / "feature.json"
        if not feature_json.exists():
            continue
        fp = json.loads(feature_json.read_text(encoding="utf-8"))
        features.append(
            Feature(
                feature_id=fp.get("feature_id", feat_dir.name),
                kind=fp.get("kind", "community"),
                name=fp.get("name", feat_dir.name),
                summary=fp.get("summary"),
                members=tuple(fp.get("members", [])),
                files=tuple(fp.get("files", [])),
                entry_points=tuple(fp.get("entry_points", [])),
                flow_ids=tuple(fp.get("flow_ids", [])),
                confidence=fp.get("confidence", "EXTRACTED"),
            )
        )
        flows_dir = feat_dir / "flows"
        if not flows_dir.is_dir():
            continue
        for flow_path in sorted(flows_dir.glob("*.json")):
            fl = json.loads(flow_path.read_text(encoding="utf-8"))
            steps = tuple(
                FlowStep(
                    depth=int(s.get("depth", 0)),
                    node_id=s.get("node_id", ""),
                    label=s.get("label", ""),
                    path=s.get("path"),
                    range=s.get("range"),
                )
                for s in fl.get("steps", [])
            )
            flows.append(
                Flow(
                    flow_id=fl.get("flow_id", flow_path.stem),
                    feature_id=fl.get("feature_id", fp.get("feature_id", feat_dir.name)),
                    entry_point=fl.get("entry_point", ""),
                    entry_point_label=fl.get("entry_point_label", ""),
                    entry_point_path=fl.get("entry_point_path"),
                    steps=steps,
                    files=tuple(fl.get("files", [])),
                    confidence=fl.get("confidence", "EXTRACTED"),
                )
            )

    graph_json_path = features_dir / "graph.json"
    graph_html_path = features_dir / "graph.html"
    _write_json(graph_json_path, _graph_view(tuple(features), tuple(flows)))
    _write_text(graph_html_path, _GRAPH_HTML)
    return graph_json_path, graph_html_path


def _index_md_from_index_json(payload: dict[str, Any]) -> str:
    """Re-render features/INDEX.md from the canonical features/INDEX.json.

    Used by ``rename_feature`` so the human-readable index never lags
    behind the machine-readable one. Falls back to the feature_id when
    a real `name` hasn't been written yet.
    """
    features = payload.get("features", []) or []
    flow_count = int(payload.get("flow_count", 0) or 0)
    lines = [
        "# Features",
        "",
        f"_{len(features)} feature(s), {flow_count} flow(s). The `/dummyindex` "
        "skill names, regroups, and summarizes — stub names are still "
        "`community-N` until enriched._",
        "",
        "| Feature | Members | Files | Entry points | Flows | Confidence |",
        "|---|---|---|---|---|---|",
    ]
    for entry in features:
        name = entry.get("name") or entry.get("feature_id")
        fid = entry.get("feature_id")
        lines.append(
            f"| [`{name}`](./{fid}/) | {entry.get('member_count', 0)} | "
            f"{entry.get('file_count', 0)} | "
            f"{entry.get('entry_point_count', 0)} | "
            f"{entry.get('flow_count', 0)} | "
            f"{entry.get('confidence', 'EXTRACTED')} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def _how_to_navigate_md() -> str:
    return (
        "# How to navigate `features/`\n"
        "\n"
        "This folder is the **feature-oriented** view of the codebase. Use it\n"
        "when the user asks about behavior (\"how does login work?\", \"what\n"
        "happens on checkout?\") rather than about symbols.\n"
        "\n"
        "## Read in this order\n"
        "\n"
        "1. **`INDEX.json`** — the machine-readable list of features. Each\n"
        "   entry has `feature_id`, `name`, `path`, and summary counts. Start\n"
        "   here; it's much smaller than walking every folder.\n"
        "2. **`<feature-id>/feature.json`** — canonical description of one\n"
        "   feature: members (symbol node_ids), files, entry_points, and a\n"
        "   `flow_ids` list pointing into `flows/`.\n"
        "3. **`<feature-id>/flows/<flow-id>.json`** — an ordered call sequence\n"
        "   from a single entry point. Each step has `node_id`, `label`,\n"
        "   `path`, `range`, and `depth`. Use this when the user wants the\n"
        "   sequence of calls that implements a particular flow.\n"
        "4. **`<feature-id>/README.md`** / **`flows/<flow-id>.md`** — human\n"
        "   prose. After the `/dummyindex` skill enriches, these become the\n"
        "   primary docs for someone reading without an agent.\n"
        "\n"
        "## Cross-reference with `tree.json` and `map/`\n"
        "\n"
        "Every `node_id` in feature / flow JSON also appears in\n"
        "`../tree.json` and `../map/symbols.json` — use those to resolve a\n"
        "node to its exact source range when reading code.\n"
        "\n"
        "## Confidence\n"
        "\n"
        "Every feature / flow has a `confidence` field. `EXTRACTED` means\n"
        "deterministic (graph communities, BFS traces). `INFERRED` means an\n"
        "LLM (the Claude session running the `/dummyindex` skill) rewrote\n"
        "the name / summary / narrative based on actual source.\n"
        "\n"
        "## Don't grep `features/`\n"
        "\n"
        "Always start from `INDEX.json` and walk by `feature_id` /\n"
        "`flow_id`. Folder names may be renamed by enrichment; the\n"
        "`feature_id` in JSON is stable.\n"
    )


_GRAPH_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>dummyindex · folder · file · feature · flow</title>
<style>
  html, body { margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f1115; color: #e6e6e6; }
  #app { display: grid; grid-template-columns: 300px 1fr; height: 100vh; }
  aside { padding: 16px; border-right: 1px solid #222; overflow-y: auto; }
  aside h1 { font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: #888; margin: 0 0 10px; }
  aside .feature { padding: 7px 10px; margin-bottom: 5px; border-radius: 6px; cursor: pointer; border: 1px solid #1f242c; background: #161a20; }
  aside .feature:hover { background: #1f242c; }
  aside .feature.active { outline: 2px solid currentColor; }
  aside .feature .name { font-weight: 600; font-size: 12px; }
  aside .feature .meta { font-size: 10px; color: #888; margin-top: 2px; }
  aside .filters { margin-top: 18px; font-size: 12px; color: #ccc; }
  aside .filters label { display: flex; align-items: center; gap: 6px; margin: 4px 0; cursor: pointer; user-select: none; }
  aside .legend { margin-top: 14px; font-size: 11px; color: #888; }
  aside .legend div { display: flex; align-items: center; gap: 8px; margin: 3px 0; }
  aside .legend .dot { width: 10px; height: 10px; border-radius: 50%; }
  aside .legend .ring { width: 10px; height: 10px; border-radius: 50%; border: 2px solid #888; background: transparent; }
  aside button.reset { margin-top: 12px; width: 100%; padding: 6px; background: #1f242c; color: #ddd; border: 1px solid #2a3038; border-radius: 4px; cursor: pointer; font-size: 11px; }
  aside button.reset:hover { background: #2a3038; }
  main { position: relative; }
  svg { width: 100%; height: 100%; display: block; }
  .link { stroke-opacity: 0.5; }
  .link.parent    { stroke: #3a4654; stroke-dasharray: 2 2; }
  .link.contains  { stroke: #4a5568; }
  .link.touches   { stroke: #2a3038; stroke-opacity: 0.35; }
  .node text { fill: #ccc; font-size: 10px; pointer-events: none; }
  .node.folder text { fill: #6b7280; font-size: 9px; }
  .node.file text   { fill: #aab; font-size: 9px; }
  .node.feature text { font-weight: 600; font-size: 12px; }
  .node.feature circle { stroke: #fff; stroke-width: 1.5; }
  .node.flow circle    { stroke: #aaa; stroke-width: 1; }
  .node.file circle    { stroke: #555; stroke-width: 1; }
  .node.folder rect    { fill: transparent; stroke: #4a5568; stroke-dasharray: 3 2; }
  .node.dimmed { opacity: 0.12; }
  .node.highlighted text { font-weight: bold; }
  .tooltip { position: absolute; pointer-events: none; padding: 6px 10px; background: rgba(0,0,0,0.9); border: 1px solid #333; border-radius: 4px; font-size: 12px; color: #fff; max-width: 320px; white-space: pre-wrap; }
</style>
</head>
<body>
<div id="app">
  <aside>
    <h1>Features</h1>
    <div id="feature-list"></div>
    <button class="reset" id="reset">Reset view</button>
    <div class="filters">
      <h1 style="margin-top:18px">Show</h1>
      <label><input type="checkbox" data-kind="folder"  checked /> folders</label>
      <label><input type="checkbox" data-kind="file"    checked /> files</label>
      <label><input type="checkbox" data-kind="feature" checked /> features</label>
      <label><input type="checkbox" data-kind="flow"    checked /> flows</label>
    </div>
    <div class="legend">
      <h1 style="margin-top:18px">Legend</h1>
      <div><span class="ring"></span> folder (dashed)</div>
      <div><span class="dot" style="background:#888"></span> file</div>
      <div><span class="dot" style="background:#a3d977"></span> feature (colored)</div>
      <div><span class="dot" style="background:#7fb8ff"></span> flow (matches feature)</div>
    </div>
  </aside>
  <main>
    <svg id="canvas"></svg>
    <div class="tooltip" id="tooltip" style="display:none"></div>
  </main>
</div>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const PALETTE = ["#a3d977", "#7fb8ff", "#ff9e64", "#c678dd", "#ff6b6b", "#4ade80", "#facc15", "#22d3ee", "#fb7185", "#a78bfa", "#fdba74", "#34d399", "#f472b6", "#60a5fa"];

(async () => {
  let data;
  try {
    data = await fetch("./graph.json").then(r => r.json());
  } catch (err) {
    document.body.innerHTML = '<pre style="padding:24px">Could not load ./graph.json — open this file via a local server (e.g. <code>python3 -m http.server</code>) from inside .context/features/.</pre>';
    return;
  }

  const featureColor = {};
  data.nodes.filter(n => n.kind === "feature").forEach((n, i) => {
    featureColor[n.id] = PALETTE[i % PALETTE.length];
  });
  const flowToFeature = {};
  data.edges.filter(e => e.relation === "contains" && String(e.target).startsWith("flow-")).forEach(e => {
    flowToFeature[e.target] = e.source;
  });

  // Sidebar feature list
  const list = d3.select("#feature-list");
  list.selectAll(".feature")
    .data(data.nodes.filter(n => n.kind === "feature").sort((a,b) => (b.file_count||0) - (a.file_count||0)))
    .enter()
    .append("div")
    .attr("class", "feature")
    .style("color", d => featureColor[d.id])
    .html(d => `<div class="name">${escapeHtml(d.label)}</div><div class="meta">${d.member_count || 0} symbols · ${d.file_count || 0} files · ${d.flow_count || 0} flows</div>`)
    .on("click", function (event, d) {
      d3.selectAll("#feature-list .feature").classed("active", false);
      d3.select(this).classed("active", true);
      highlight(d.id);
    });

  const svg = d3.select("#canvas");
  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;
  const g = svg.append("g");
  const zoom = d3.zoom().scaleExtent([0.15, 5]).on("zoom", (e) => g.attr("transform", e.transform));
  svg.call(zoom);

  // Strength varies by edge kind: folder containment is strongest (pulls the
  // tree together), flow→file is weak (otherwise files clump under the flow).
  const linkDist = e => ({ parent: 35, contains: 50, touches: 80 }[e.relation] || 60);
  const linkStr  = e => ({ parent: 1.1, contains: 0.8, touches: 0.25 }[e.relation] || 0.5);

  const sim = d3.forceSimulation(data.nodes)
    .force("link", d3.forceLink(data.edges).id(d => d.id).distance(linkDist).strength(linkStr))
    .force("charge", d3.forceManyBody().strength(d => d.kind === "feature" ? -350 : (d.kind === "flow" ? -120 : -40)))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide().radius(d => d.kind === "feature" ? 24 : (d.kind === "flow" ? 12 : (d.kind === "file" ? 8 : 14))));

  const link = g.append("g").attr("class", "links").selectAll("line")
    .data(data.edges)
    .enter().append("line")
    .attr("class", d => "link " + (d.relation || ""));

  const node = g.append("g").selectAll("g.node")
    .data(data.nodes)
    .enter().append("g")
    .attr("class", d => "node " + d.kind);

  // Folders use a small dashed rect; everything else is a circle.
  node.filter(d => d.kind === "folder").append("rect")
    .attr("x", -10).attr("y", -7).attr("width", 20).attr("height", 14).attr("rx", 3);
  node.filter(d => d.kind !== "folder").append("circle")
    .attr("r", d => d.kind === "feature" ? 14 : (d.kind === "flow" ? 7 : 4))
    .attr("fill", d => {
      if (d.kind === "feature") return featureColor[d.id];
      if (d.kind === "flow") return featureColor[flowToFeature[d.id]] || "#7fb8ff";
      return "#7c8696";
    });

  node.append("text")
    .text(d => d.label)
    .attr("x", d => (d.kind === "feature" ? 18 : (d.kind === "folder" ? 14 : 8)))
    .attr("dy", "0.32em");

  const tooltip = d3.select("#tooltip");
  node.on("mouseover", (event, d) => {
    const lines = [`${d.kind} · ${d.label}`];
    if (d.path) lines.push(d.path);
    if (d.kind === "feature") {
      if (d.summary) lines.push("");
      if (d.summary) lines.push(d.summary);
      lines.push(`${d.member_count || 0} symbols · ${d.file_count || 0} files · ${d.flow_count || 0} flows`);
    } else if (d.kind === "flow") {
      lines.push(`${d.step_count || 0} steps · ${d.file_count || 0} files`);
    }
    tooltip.style("display", "block")
      .style("left", (event.offsetX + 14) + "px")
      .style("top", (event.offsetY + 14) + "px")
      .text(lines.join("\\n"));
  }).on("mouseout", () => tooltip.style("display", "none"));

  sim.on("tick", () => {
    link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });

  node.call(d3.drag()
    .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
    .on("drag",  (event, d) => { d.fx = event.x; d.fy = event.y; })
    .on("end",   (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

  // Filter checkboxes
  document.querySelectorAll(".filters input").forEach(cb => {
    cb.addEventListener("change", () => {
      const allowed = new Set(Array.from(document.querySelectorAll(".filters input:checked")).map(i => i.dataset.kind));
      node.style("display", d => allowed.has(d.kind) ? null : "none");
      link.style("display", e => {
        const s = typeof e.source === "object" ? e.source : data.nodes.find(n => n.id === e.source);
        const t = typeof e.target === "object" ? e.target : data.nodes.find(n => n.id === e.target);
        return s && t && allowed.has(s.kind) && allowed.has(t.kind) ? null : "none";
      });
    });
  });

  document.getElementById("reset").addEventListener("click", () => {
    d3.selectAll("#feature-list .feature").classed("active", false);
    node.classed("dimmed", false).classed("highlighted", false);
    link.style("opacity", null);
  });

  function highlight(featureId) {
    // Expand the "connected" set by following any edge between known nodes —
    // a 2-pass closure gets us folders (file -> parent folder -> root) and
    // every flow / file the feature touches.
    const connected = new Set([featureId]);
    for (let pass = 0; pass < 4; pass++) {
      data.edges.forEach(e => {
        const s = typeof e.source === "object" ? e.source.id : e.source;
        const t = typeof e.target === "object" ? e.target.id : e.target;
        if (connected.has(s)) connected.add(t);
        if (connected.has(t) && (e.relation === "parent" || e.relation === "contains")) connected.add(s);
      });
    }
    node.classed("dimmed", d => !connected.has(d.id));
    node.classed("highlighted", d => d.id === featureId);
    link.style("opacity", e => {
      const s = typeof e.source === "object" ? e.source.id : e.source;
      const t = typeof e.target === "object" ? e.target.id : e.target;
      return connected.has(s) && connected.has(t) ? 0.9 : 0.05;
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]));
  }
})();
</script>
</body>
</html>
"""


def _graph_view(
    features: tuple[Feature, ...], flows: tuple[Flow, ...]
) -> dict[str, Any]:
    """Denormalized graph for the HTML viewer.

    Four node kinds, full folder → file → feature → flow hierarchy:

    - ``folder`` — every unique directory along the path of any file
      involved in a feature/flow. The repo root is ``folder::.``.
    - ``file`` — every source file touched by at least one feature.
    - ``feature`` — Leiden community wrapping one or more files.
    - ``flow`` — entry-point trace within a feature.

    Edge relations:

    - ``parent`` — folder → folder (containment in the directory tree)
    - ``contains`` — folder → file, feature → flow
    - ``touches`` — feature → file, flow → file
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Collect every file used by any feature.
    all_files: set[str] = set()
    for f in features:
        all_files.update(f.files)
    for flow in flows:
        all_files.update(flow.files)

    # Build the folder hierarchy: every unique directory along every
    # file's path, plus the synthetic root folder.
    folder_paths: set[str] = {"."}
    for fp in all_files:
        parts = fp.split("/")
        for i in range(1, len(parts)):  # exclude the file itself
            folder_paths.add("/".join(parts[:i]))

    for fpath in sorted(folder_paths):
        label = "/" if fpath == "." else fpath.split("/")[-1]
        nodes.append(
            {
                "id": f"folder::{fpath}",
                "label": label,
                "kind": "folder",
                "path": fpath,
            }
        )
        # parent → child folder edge
        if fpath != ".":
            parent = "/".join(fpath.split("/")[:-1]) or "."
            edges.append(
                {
                    "source": f"folder::{parent}",
                    "target": f"folder::{fpath}",
                    "relation": "parent",
                }
            )

    # Files: emit each once and connect to its parent folder.
    for fp in sorted(all_files):
        file_id = f"file::{fp}"
        parts = fp.split("/")
        parent_folder = "/".join(parts[:-1]) or "."
        nodes.append(
            {
                "id": file_id,
                "label": parts[-1],
                "kind": "file",
                "path": fp,
            }
        )
        edges.append(
            {
                "source": f"folder::{parent_folder}",
                "target": file_id,
                "relation": "contains",
            }
        )

    # Features + their file touches.
    for f in features:
        nodes.append(
            {
                "id": f.feature_id,
                "label": f.name,
                "kind": "feature",
                "member_count": len(f.members),
                "file_count": len(f.files),
                "flow_count": len(f.flow_ids),
                "summary": f.summary,
                "confidence": f.confidence,
            }
        )
        for fp in f.files:
            edges.append(
                {
                    "source": f.feature_id,
                    "target": f"file::{fp}",
                    "relation": "touches",
                }
            )

    # Flows: under their feature, touching their files.
    for flow in flows:
        nodes.append(
            {
                "id": flow.flow_id,
                "label": flow.entry_point_label,
                "kind": "flow",
                "feature_id": flow.feature_id,
                "step_count": len(flow.steps),
                "file_count": len(flow.files),
            }
        )
        edges.append(
            {
                "source": flow.feature_id,
                "target": flow.flow_id,
                "relation": "contains",
            }
        )
        for fp in flow.files:
            edges.append(
                {
                    "source": flow.flow_id,
                    "target": f"file::{fp}",
                    "relation": "touches",
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "nodes": nodes,
        "edges": edges,
    }
