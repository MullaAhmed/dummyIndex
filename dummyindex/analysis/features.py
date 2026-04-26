"""Feature Hypergraph synthesis — Feature 3 (capstone).

Pure deterministic synthesis of capability-level hyperedges from the
combined signals already produced by dummyindex:

- Leiden communities + cohesion (existing)
- God nodes (existing)
- Flows + flow memberships (Feature 2)
- Folder / file structure (Feature 1)
- Documents, papers, rationale comments (existing)

Features differ from communities in two essential ways:

1. **Hypergraph membership.** A node can belong to many features (a logger
   used by Auth, Payments, and Notifications appears in all three with
   ``role="shared"``). Communities partition; features overlap.
2. **Named, product-level groupings.** Stage A (this module) produces
   deterministic candidates. Stage B (``feature_naming.py``) renames them
   via subagents using LLM judgment.

Public entry points:

- ``synthesize_features(G, communities, flows=None, ...)`` — Stage A end-to-end
- ``derive_feature_dependencies(G, features, flows)`` — feature → feature deps
- ``signal_pack(G, communities, flows, ...)`` — assemble the canonical
  input snapshot (used by both this module and ``feature_naming.py``)
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable

import networkx as nx


SCHEMA_VERSION = "1.3"

VALID_FEATURE_ROLES = ("core", "entry", "terminal", "shared", "rationale", "data")

_DEFAULT_MIN_FEATURE_SIZE = 3
_DEFAULT_FEATURE_LIMIT = 20
_DEFAULT_MERGE_JACCARD = 0.75
_DEFAULT_FLOW_OVERLAP = 0.7
_DEFAULT_DEP_THRESHOLD = 0.1
_DEFAULT_COHESION_FLOOR = 0.0  # accept any community by default; tunable

_ROLE_DEFAULT_WEIGHT = {
    "core": 1.0,
    "entry": 0.9,
    "terminal": 0.9,
    "rationale": 0.7,
    "data": 0.6,
    "shared": 0.3,
}

_DATA_FILE_EXTS = (".yaml", ".yml", ".toml", ".json", ".env", ".ini", ".cfg")


@dataclass(frozen=True)
class FeatureConfig:
    """Knobs for synthesis. Stable defaults; expose via CLI later."""

    min_feature_size: int = _DEFAULT_MIN_FEATURE_SIZE
    feature_limit: int = _DEFAULT_FEATURE_LIMIT
    merge_jaccard_threshold: float = _DEFAULT_MERGE_JACCARD
    flow_enrichment_overlap: float = _DEFAULT_FLOW_OVERLAP
    dep_threshold: float = _DEFAULT_DEP_THRESHOLD
    cohesion_floor: float = _DEFAULT_COHESION_FLOOR


@dataclass(frozen=True)
class SignalPack:
    """Immutable snapshot of every signal that feeds feature synthesis.

    Same shape passed to deterministic derivation and the LLM prompt.
    Reproducibility depends on this being the *only* input."""

    communities: dict[int, list[str]]
    cohesion: dict[int, float]
    god_nodes: list[dict]
    flows: list[dict]
    flow_memberships: dict[str, list[str]]
    docs_by_file: dict[str, list[str]]
    rationales_by_target: dict[str, list[str]]
    folder_summary: dict[str, list[str]]
    community_labels: dict[int, str]


# --------------------------------------------------------------------------- #
# Signal aggregation.
# --------------------------------------------------------------------------- #


def signal_pack(
    G: nx.Graph,
    communities: dict[int, list[str]],
    flows: list[dict] | None = None,
    *,
    cohesion: dict[int, float] | None = None,
    god_nodes_data: list[dict] | None = None,
    community_labels: dict[int, str] | None = None,
) -> SignalPack:
    """Assemble the canonical signal snapshot. Pure; deterministic."""
    flows = flows or []
    cohesion = cohesion or {}
    god_nodes_data = god_nodes_data or []
    community_labels = community_labels or {}

    # Per-node flow memberships (sorted for determinism).
    membership: dict[str, list[str]] = defaultdict(list)
    for f in flows:
        fid = f.get("id", "")
        for nid in f.get("nodes", []) or []:
            membership[nid].append(fid)
    for nid in membership:
        membership[nid].sort()

    docs_by_file: dict[str, list[str]] = defaultdict(list)
    rationales_by_target: dict[str, list[str]] = defaultdict(list)
    for nid in sorted(G.nodes()):
        attrs = G.nodes[nid]
        ft = attrs.get("file_type")
        sf = attrs.get("source_file") or ""
        if ft in ("document", "paper", "image"):
            docs_by_file[sf].append(nid)
        elif ft == "rationale":
            # rationale_for edges point from the rationale node to its target
            for _, v, data in _outgoing_edges(G, nid):
                if data.get("relation") == "rationale_for":
                    rationales_by_target[v].append(nid)

    folder_summary: dict[str, list[str]] = defaultdict(list)
    for nid in sorted(G.nodes()):
        sf = G.nodes[nid].get("source_file") or ""
        if not sf:
            continue
        parts = PurePosixPath(sf).parts
        # Use top-level folder as the bucket; "" if the file sits at root.
        top = parts[0] if len(parts) > 1 else ""
        folder_summary[top].append(nid)

    return SignalPack(
        communities={int(k): sorted(v) for k, v in communities.items()},
        cohesion={int(k): float(v) for k, v in cohesion.items()},
        god_nodes=list(god_nodes_data),
        flows=list(flows),
        flow_memberships=dict(membership),
        docs_by_file=dict(docs_by_file),
        rationales_by_target=dict(rationales_by_target),
        folder_summary=dict(folder_summary),
        community_labels=dict(community_labels),
    )


def _outgoing_edges(G: nx.Graph, node_id: str):
    if G.is_directed():
        yield from G.out_edges(node_id, data=True)
    else:
        for u, v, d in G.edges(node_id, data=True):
            if u == node_id:
                yield u, v, d


# --------------------------------------------------------------------------- #
# Stage A — deterministic candidate generation.
# --------------------------------------------------------------------------- #


def synthesize_features(
    G: nx.Graph,
    communities: dict[int, list[str]],
    *,
    flows: list[dict] | None = None,
    cohesion: dict[int, float] | None = None,
    god_nodes_data: list[dict] | None = None,
    community_labels: dict[int, str] | None = None,
    config: FeatureConfig | None = None,
) -> list[dict]:
    """Stage A end-to-end: seed → enrich → attract → attach → merge/split → role/weight.

    Returns a list of feature hyperedge dicts ready for naming and export.
    Names are provisional (slug + community ids); ``feature_naming`` replaces
    them with human-readable strings via subagents."""
    config = config or FeatureConfig()
    pack = signal_pack(G, communities, flows or [], cohesion=cohesion,
                       god_nodes_data=god_nodes_data, community_labels=community_labels)

    candidates = _seed_from_communities(pack, config)
    candidates = _enrich_with_flows(candidates, pack, config)
    candidates = _attract_god_nodes(candidates, G, pack)
    candidates = _attach_documentation(candidates, G, pack)
    candidates = _merge_split(candidates, G, config)
    candidates = _assign_roles_weights(candidates, G, pack)

    # Filter under min size, cap by salience, sort.
    sized = [c for c in candidates if len(c["nodes"]) >= config.min_feature_size]
    sized.sort(key=lambda c: (-_salience(c, pack), c["id"]))
    if config.feature_limit > 0:
        sized = sized[: config.feature_limit]
    return sized


def _seed_from_communities(pack: SignalPack, config: FeatureConfig) -> list[dict]:
    """Each community above the cohesion floor seeds one candidate feature."""
    out: list[dict] = []
    for cid in sorted(pack.communities.keys()):
        nodes = pack.communities[cid]
        if not nodes:
            continue
        score = pack.cohesion.get(cid, 1.0)
        if score < config.cohesion_floor:
            continue
        label = pack.community_labels.get(cid) or f"community_{cid}"
        out.append({
            "id": _provisional_id(label, [cid]),
            "label": label,  # provisional; naming step replaces
            "kind": "feature",
            "nodes": list(nodes),
            "communities": [cid],
            "evidence": {
                "community_ids": [cid],
                "representative_nodes": nodes[:5],
                "doc_node_ids": [],
                "flow_ids": [],
                "override_applied": False,
                "llm_reasoning": "",
            },
            "members": [],  # populated in _assign_roles_weights
            "flows": [],
            "confidence": "INFERRED",
            "description": "",
        })
    return out


def _enrich_with_flows(
    candidates: list[dict],
    pack: SignalPack,
    config: FeatureConfig,
) -> list[dict]:
    """For each candidate, pull in any flow whose participants mostly already
    belong (≥ flow_enrichment_overlap). Add the flow's nodes to the feature
    and record the flow id."""
    out = [_clone_feature(c) for c in candidates]
    for c in out:
        member_set = set(c["nodes"])
        for flow in pack.flows:
            flow_nodes = flow.get("nodes") or []
            if not flow_nodes:
                continue
            overlap = sum(1 for n in flow_nodes if n in member_set)
            if overlap / len(flow_nodes) >= config.flow_enrichment_overlap:
                c["flows"].append(flow["id"])
                for n in flow_nodes:
                    if n not in member_set:
                        member_set.add(n)
                        c["nodes"].append(n)
        c["flows"] = sorted(set(c["flows"]))
        c["nodes"] = sorted(set(c["nodes"]))
        c["evidence"] = dict(c["evidence"], flow_ids=list(c["flows"]))
    return out


def _attract_god_nodes(
    candidates: list[dict],
    G: nx.Graph,
    pack: SignalPack,
) -> list[dict]:
    """Attach god nodes to every feature whose member set has ≥ 3 edges to
    that god node. The role for an attracted god node will be derived later
    (typically ``shared``)."""
    out = [_clone_feature(c) for c in candidates]
    member_snapshots = {c["id"]: set(c["nodes"]) for c in out}
    for god in pack.god_nodes:
        gid = god.get("id")
        if not gid or gid not in G.nodes:
            continue
        # On DiGraph, neighbors() returns only successors. We need every node
        # the god is connected to in either direction — utilities are typically
        # *called*, so the in-edges matter most.
        all_neighbors: set[str] = set()
        if G.is_directed():
            all_neighbors.update(G.predecessors(gid))
            all_neighbors.update(G.successors(gid))
        else:
            all_neighbors.update(G.neighbors(gid))
        for c in out:
            if gid in c["nodes"]:
                continue
            edges_into = sum(1 for nbr in all_neighbors if nbr in member_snapshots[c["id"]])
            if edges_into >= 3:
                c["nodes"].append(gid)
    for c in out:
        c["nodes"] = sorted(set(c["nodes"]))
    return out


def _attach_documentation(
    candidates: list[dict],
    G: nx.Graph,
    pack: SignalPack,
) -> list[dict]:
    """For each candidate, attach doc/rationale nodes that mention ≥ 3 of
    its members, plus rationales whose target is a member."""
    out = [_clone_feature(c) for c in candidates]
    label_index = {nid: G.nodes[nid].get("label", "") for nid in G.nodes()}
    for c in out:
        member_set = set(c["nodes"])
        member_labels = [label_index.get(n, "") for n in c["nodes"] if label_index.get(n)]
        # doc/paper attachment via name matching
        for sf, doc_ids in pack.docs_by_file.items():
            text_blob = " ".join(
                G.nodes[nid].get("label", "") + " " + (G.nodes[nid].get("description") or "")
                for nid in doc_ids
            ).lower()
            if not text_blob:
                continue
            hits = sum(1 for lbl in member_labels if lbl and lbl.lower() in text_blob)
            if hits >= 3:
                for did in doc_ids:
                    if did not in member_set:
                        c["nodes"].append(did)
                        member_set.add(did)
                c["evidence"]["doc_node_ids"].extend(doc_ids)
        # rationale attachment via rationale_for edges
        for tgt in c["nodes"]:
            for rid in pack.rationales_by_target.get(tgt, []):
                if rid not in member_set:
                    c["nodes"].append(rid)
                    member_set.add(rid)
                    c["evidence"]["doc_node_ids"].append(rid)
        c["nodes"] = sorted(set(c["nodes"]))
        c["evidence"]["doc_node_ids"] = sorted(set(c["evidence"]["doc_node_ids"]))
    return out


def _merge_split(
    candidates: list[dict],
    G: nx.Graph,
    config: FeatureConfig,
) -> list[dict]:
    """Merge two candidates if Jaccard ≥ threshold. Skip subgraph splits in
    v1 — Stage B (LLM) can split features when it sees disconnected sub-themes."""
    pool = [_clone_feature(c) for c in candidates]
    changed = True
    while changed:
        changed = False
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                a, b = pool[i], pool[j]
                if not a or not b:
                    continue
                ja = _jaccard(set(a["nodes"]), set(b["nodes"]))
                if ja >= config.merge_jaccard_threshold:
                    pool[i] = _merge_features(a, b)
                    pool[j] = None  # type: ignore[assignment]
                    changed = True
                    break
            if changed:
                break
        pool = [c for c in pool if c]
    return pool


def _assign_roles_weights(
    candidates: list[dict],
    G: nx.Graph,
    pack: SignalPack,
) -> list[dict]:
    """Compute `members` (with role + weight) and `roles` summary for each
    candidate. Run after merge so feature membership is final."""
    # Build node → list-of-feature-ids index across the current candidate set.
    node_to_features: dict[str, list[str]] = defaultdict(list)
    for c in candidates:
        for n in c["nodes"]:
            node_to_features[n].append(c["id"])

    # Index per-flow entry/terminal nodes for role lookup.
    entry_nodes: dict[str, set[str]] = defaultdict(set)  # flow_id → entry node ids
    terminal_nodes: dict[str, set[str]] = defaultdict(set)
    for f in pack.flows:
        fid = f.get("id", "")
        for n in f.get("entry_nodes") or []:
            entry_nodes[fid].add(n)
        for n in f.get("exit_nodes") or []:
            terminal_nodes[fid].add(n)

    out: list[dict] = []
    for c in candidates:
        members: list[dict] = []
        role_counts = {r: 0 for r in VALID_FEATURE_ROLES}
        feature_id = c["id"]
        feature_flows = set(c.get("flows", []))
        for nid in sorted(c["nodes"]):
            attrs = G.nodes.get(nid, {})
            ft = attrs.get("file_type", "code")
            sf = attrs.get("source_file") or ""

            # entry / terminal precedence over core/shared
            is_entry = any(nid in entry_nodes[fid] for fid in feature_flows)
            is_terminal = any(nid in terminal_nodes[fid] for fid in feature_flows)
            in_other_features = [fid for fid in node_to_features[nid] if fid != feature_id]

            if is_entry:
                role = "entry"
            elif is_terminal:
                role = "terminal"
            elif ft in ("document", "paper", "image"):
                role = "rationale"
            elif ft == "rationale":
                role = "rationale"
            elif sf and sf.lower().endswith(_DATA_FILE_EXTS):
                role = "data"
            elif in_other_features:
                role = "shared"
            else:
                role = "core"

            if role == "shared":
                weight = max(0.1, min(0.5, 1.0 / max(1, len(in_other_features) + 1)))
            else:
                weight = _ROLE_DEFAULT_WEIGHT[role]

            members.append({"node_id": nid, "role": role, "weight": round(weight, 3)})
            role_counts[role] += 1

        new = _clone_feature(c)
        new["members"] = members
        new["roles"] = role_counts
        out.append(new)
    return out


# --------------------------------------------------------------------------- #
# Feature-to-feature dependency derivation.
# --------------------------------------------------------------------------- #


def derive_feature_dependencies(
    G: nx.Graph,
    features: list[dict],
    flows: list[dict] | None = None,
    *,
    config: FeatureConfig | None = None,
) -> list[dict]:
    """Return a list of directed feature dependency edges.

    Each dep aggregates evidence from three sources:

    1. **Flow transitions** — a flow whose entry is a member of feature A
       passes through an entry node of feature B.
    2. **Cross-core imports** — a `core` node in A has an edge of relation
       `imports`/`imports_from`/`uses`/`inherits` to a `core` node in B.
    3. **Shared-as-core** — a `shared` node in A is `core` in B.
    """
    config = config or FeatureConfig()
    flows = flows or []
    deps: dict[tuple[str, str], dict] = {}

    # Index (node_id, role) -> list of features that have this node in that role.
    f_by_id = {f["id"]: f for f in features}
    feature_for_node_role: dict[tuple[str, str], list[str]] = defaultdict(list)
    for f in features:
        for m in f.get("members", []):
            feature_for_node_role[(m["node_id"], m["role"])].append(f["id"])

    def add(a: str, b: str, key: str, value):
        if a == b:
            return
        slot = deps.setdefault((a, b), {"via_flows": [], "via_imports": [], "via_shared_nodes": []})
        if value not in slot[key]:
            slot[key].append(value)

    # 1. Flow transitions: a flow is hosted by (a) any feature that lists it
    # in `flows`, and (b) any feature whose `core` members include the flow's
    # entry node. (b) catches flows that didn't meet the strict 70% Stage A
    # enrichment threshold but still clearly belong to a feature.
    flow_features: dict[str, set[str]] = defaultdict(set)
    for fl in flows:
        for fid, feat in f_by_id.items():
            if fl["id"] in (feat.get("flows") or []):
                flow_features[fl["id"]].add(fid)
        for entry in fl.get("entry_nodes") or []:
            for fid in feature_for_node_role.get((entry, "core"), []):
                flow_features[fl["id"]].add(fid)
            for fid in feature_for_node_role.get((entry, "entry"), []):
                flow_features[fl["id"]].add(fid)
    for fl in flows:
        host_features = flow_features.get(fl["id"], set())
        if not host_features:
            continue
        for step in fl.get("sequence") or []:
            target = step.get("target")
            if not target:
                continue
            target_features = (
                feature_for_node_role.get((target, "entry"), [])
                + feature_for_node_role.get((target, "core"), [])
            )
            for fid_b in set(target_features):
                for fid_a in host_features:
                    if fid_a != fid_b:
                        add(fid_a, fid_b, "via_flows", fl["id"])

    # 2. Cross-core imports
    rel_set = {"imports", "imports_from", "uses", "inherits"}
    for u, v, data in G.edges(data=True):
        rel = data.get("relation")
        if rel not in rel_set:
            continue
        cores_u = feature_for_node_role.get((u, "core"), [])
        cores_v = feature_for_node_role.get((v, "core"), [])
        for fa in cores_u:
            for fb in cores_v:
                if fa != fb:
                    add(fa, fb, "via_imports", [u, v])

    # 3. Shared-as-core
    for (nid, role), feature_ids in feature_for_node_role.items():
        if role != "shared":
            continue
        cores = feature_for_node_role.get((nid, "core"), [])
        for fa in feature_ids:
            for fb in cores:
                if fa != fb:
                    add(fa, fb, "via_shared_nodes", nid)

    # Aggregate weight + flag mutual cycles
    out: list[dict] = []
    for (a, b), evidence in deps.items():
        weight = (
            len(evidence["via_flows"]) * 0.6
            + len(evidence["via_imports"]) * 0.3
            + len(evidence["via_shared_nodes"]) * 0.1
        )
        if weight < config.dep_threshold:
            continue
        out.append({
            "source_feature_id": a,
            "target_feature_id": b,
            "weight": round(weight, 3),
            "evidence": evidence,
            "is_mutual": (b, a) in deps,
        })
    out.sort(key=lambda d: (-d["weight"], d["source_feature_id"], d["target_feature_id"]))
    return out


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _clone_feature(c: dict) -> dict:
    out = dict(c)
    for key in ("nodes", "communities", "flows", "members"):
        if key in out and out[key] is not None:
            out[key] = list(out[key])
    if "evidence" in out and out["evidence"] is not None:
        ev = dict(out["evidence"])
        for key in ("community_ids", "representative_nodes", "doc_node_ids", "flow_ids"):
            if key in ev and ev[key] is not None:
                ev[key] = list(ev[key])
        out["evidence"] = ev
    if "roles" in out and out["roles"] is not None:
        out["roles"] = dict(out["roles"])
    return out


def _merge_features(a: dict, b: dict) -> dict:
    new = _clone_feature(a)
    new["nodes"] = sorted(set(a["nodes"]) | set(b["nodes"]))
    new["communities"] = sorted(set(a["communities"]) | set(b["communities"]))
    new["flows"] = sorted(set(a.get("flows", []) + b.get("flows", [])))
    ev_a = a.get("evidence", {})
    ev_b = b.get("evidence", {})
    new["evidence"] = {
        "community_ids": sorted(set(ev_a.get("community_ids", []) + ev_b.get("community_ids", []))),
        "representative_nodes": sorted(set(ev_a.get("representative_nodes", []) + ev_b.get("representative_nodes", [])))[:8],
        "doc_node_ids": sorted(set(ev_a.get("doc_node_ids", []) + ev_b.get("doc_node_ids", []))),
        "flow_ids": new["flows"],
        "override_applied": ev_a.get("override_applied", False) or ev_b.get("override_applied", False),
        "llm_reasoning": ev_a.get("llm_reasoning", "") or ev_b.get("llm_reasoning", ""),
    }
    new["id"] = _provisional_id(new["label"], new["communities"])
    return new


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _provisional_id(label: str, community_ids: list[int]) -> str:
    slug = _slug(label) or "feature"
    payload = "|".join([slug] + [str(c) for c in sorted(community_ids)])
    h = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"feature:{slug}_{h}"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text or "").strip("_").lower()
    return s[:40]


def _salience(feature: dict, pack: SignalPack) -> float:
    """Rank for the ``feature_limit`` cap. Combines size, flow count, and
    documentation coverage so well-attested features outrank thin ones."""
    size = len(feature.get("nodes") or [])
    flow_count = len(feature.get("flows") or [])
    doc_count = len(feature.get("evidence", {}).get("doc_node_ids") or [])
    return round(math.log2(1 + size) + 0.5 * flow_count + 0.25 * doc_count, 4)


def overlap_matrix(features: list[dict]) -> dict[str, list[str]]:
    """node_id -> list of feature_ids that contain it. Sorted, deterministic."""
    idx: dict[str, list[str]] = {}
    for f in features:
        fid = f["id"]
        for n in f.get("nodes") or []:
            idx.setdefault(n, []).append(fid)
    for n in idx:
        idx[n].sort()
    return dict(sorted(idx.items()))


def canonical_hash(feature: dict) -> str:
    """Stable per-feature hash keyed on member node ids. Used by
    ``features.yaml`` overrides to track features across renames."""
    members = sorted(feature.get("nodes") or [])
    return hashlib.sha1("|".join(members).encode("utf-8")).hexdigest()[:12]


def detect_orphans(G: nx.Graph, features: list[dict]) -> list[str]:
    """Nodes belonging to no feature. Sorted, deterministic."""
    covered: set[str] = set()
    for f in features:
        covered.update(f.get("nodes") or [])
    return sorted(n for n in G.nodes() if n not in covered)
