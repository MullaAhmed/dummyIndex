"""Deterministic backbone for `features/graph.json`.

`scaffold_features` writes this the moment a repo is ingested, long before
any model has looked at it. It is a real map — every feature is a node,
every flow entry point is a trigger, every cross-feature file reach is a
call edge — just an unopinionated one: it knows the shape of the code, not
what the code is *for*.

Everything here is pure and sorted, so two runs on the same input produce
byte-identical JSON. The authoring stage
(`skills/council/55-codebase-scan.md`) rewrites the result into the curated
scan and flips `confidence` to `INFERRED`, which is what stops a later
rebuild from overwriting it.

Deliberately absent: any attempt to detect models, tools, or integrations.
Grepping for `@ai-sdk/openai` would find the import and still not know
whether it is the product's core loop or a dead experiment. That call is
judgment; the seed leaves `stats` at zero and the chip rows empty.
"""

from __future__ import annotations

import re
from typing import Any

from dummyindex.context.enums import ScanEdgeKind, ScanEvidence, ScanNodeKind

from ..constants import (
    _CALL_RELATIONS,
    _SEED_SERVICE_SHARE,
    MAX_NODE_DETAIL,
    MAX_NODE_LABEL,
    MAX_NODE_SOURCE_REF,
    MAX_NODE_SUB,
    MAX_NODE_SYMBOL_REF,
    MAX_SCAN_EDGES,
    MAX_SCAN_NODES,
)
from ..models import Feature, Flow
from .models import Scan, ScanEdge, ScanNode, ScanProject, ScanStats
from .rank import SeedRank

# What survives in a slug. Anything else collapses to a single dash.
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, fallback: str = "project") -> str:
    """Lowercase-dashed slug for `project.slug`, or ``fallback`` if nothing survives."""
    slug = _SLUG_STRIP.sub("-", text.strip().lower()).strip("-")
    return slug or fallback


def _clip(text: str | None, limit: int) -> str | None:
    """Truncate to ``limit`` characters, marking the cut with an ellipsis."""
    if text is None:
        return None
    text = text.strip()
    if len(text) <= limit:
        return text or None
    return text[: limit - 1].rstrip() + "…"


def _clip_path(path: str | None, limit: int) -> str | None:
    """Truncate a `path[:line]` ref from the *front*.

    Clipping a path's tail destroys the only part anyone reads — the
    filename and line. `…text/domains/features/scan/seed.py:41` still lets
    a teammate find the file; `dummyindex/context/domai…` does not.
    """
    if path is None:
        return None
    path = path.strip()
    if len(path) <= limit:
        return path or None
    return "…" + path[-(limit - 1) :]


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _service_budget(feature_count: int, has_flows: bool, max_nodes: int) -> int:
    """How many `service` nodes to emit before entry points get the rest.

    With no flows there is nothing else to spend the budget on. With flows,
    features keep a fixed majority share: a repo with 200 deterministic
    flows and 12 features must not render as 60 entry points and no
    features.
    """
    if not has_flows:
        return min(feature_count, max_nodes)
    return min(feature_count, max(1, int(max_nodes * _SEED_SERVICE_SHARE)))


def seed_scan(
    features: tuple[Feature, ...],
    flows: tuple[Flow, ...],
    *,
    project_name: str,
    slug: str,
    links: tuple[dict[str, Any], ...] = (),
    rank: SeedRank | None = None,
    max_nodes: int = MAX_SCAN_NODES,
    max_edges: int = MAX_SCAN_EDGES,
) -> Scan:
    """Build the deterministic scan seed from extracted features and flows.

    ``rank`` is the personalized-PageRank shortlist from
    `features/seed-rank.json` (see `rank.load_seed_rank`). When present it
    drives selection and ordering — features by the summed rank of their
    members, entries by their entry point's rank — and every emitted node
    carries `evidence: EXTRACTED` plus, where a member resolves, a
    `symbolRef` into the symbol graph. When absent (no symbol graph),
    features fall back to ranking by file count (biggest first,
    `feature_id` breaking ties) so that when the cap bites, what survives
    is the part of the codebase someone would actually name first — the
    pre-rank behaviour, byte for byte.

    ``links`` is the raw node-link edge list from the symbol graph. It is the
    load-bearing edge signal: flows would be the obvious one, but council
    stage 4 discards most flows on purpose and a fully enriched repo can have
    none left, which would leave the seed a field of disconnected boxes.
    Calls between symbols never go away.
    """
    scores = rank.scores() if rank is not None else None
    ranked = sorted(features, key=_feature_sort_key(scores))
    kept = ranked[: _service_budget(len(ranked), bool(flows), max_nodes)]
    kept_ids = {f.feature_id for f in kept}

    nodes: list[ScanNode] = [_service_node(f, scores) for f in kept]

    # A file can be claimed by more than one feature; rank order decides the
    # owner so the edge set doesn't flip between runs.
    owner_of_file: dict[str, str] = {}
    for feat in ranked:
        for path in feat.files:
            owner_of_file.setdefault(path, feat.feature_id)

    owner_of_symbol: dict[str, str] = {}
    for feat in ranked:
        for member in feat.members:
            owner_of_symbol.setdefault(member, feat.feature_id)

    entry_budget = max_nodes - len(nodes)
    entries = _entry_flows(flows, kept_ids, entry_budget, scores)
    nodes.extend(_entry_node(fl, scores) for fl in entries)

    edges = _edges(
        entries, flows, kept_ids, owner_of_file, owner_of_symbol, links, max_edges
    )

    return Scan(
        project=ScanProject(name=_clip(project_name, 48) or "project", slug=slug),
        stats=ScanStats(),
        nodes=tuple(nodes),
        edges=edges,
    )


def _feature_sort_key(scores: dict[str, float] | None):
    """Feature ordering: summed member rank when there is one, size otherwise.

    File count and `feature_id` stay in the key as tie-breakers so features
    whose members all fell off the truncated shortlist (summed rank 0.0)
    keep the exact pre-rank order.
    """
    if scores is None:
        return lambda f: (-len(f.files), f.feature_id)

    def key(feat: Feature) -> tuple[float, int, str]:
        total = sum(scores.get(m, 0.0) for m in feat.members)
        return (-total, -len(feat.files), feat.feature_id)

    return key


def _top_member_ref(members: tuple[str, ...], scores: dict[str, float]) -> str | None:
    """The feature's best-ranked member, as a resolvable `symbolRef`.

    Only members the shortlist actually ranked qualify — a made-up ref is
    worse than none — and a ref that would blow the wire cap is dropped
    rather than clipped, because a clipped id resolves to nothing.
    """
    ranked = [m for m in members if m in scores]
    if not ranked:
        return None
    top = min(ranked, key=lambda m: (-scores[m], m))
    return top if len(top) <= MAX_NODE_SYMBOL_REF else None


def _service_node(feat: Feature, scores: dict[str, float] | None) -> ScanNode:
    """A feature is a `service`: an internal module the project owns."""
    parts = [_plural(len(feat.files), "file")]
    if feat.flow_ids:
        parts.append(_plural(len(feat.flow_ids), "flow"))
    return ScanNode(
        id=feat.feature_id,
        label=_clip(feat.name, MAX_NODE_LABEL) or feat.feature_id,
        kind=ScanNodeKind.SERVICE,
        sub=_clip(" · ".join(parts), MAX_NODE_SUB),
        detail=_clip(feat.summary, MAX_NODE_DETAIL),
        # Lowest-sorted file, not `files[0]`: feature.json preserves author
        # order, and a ref that moves when a file is added is a bad ref.
        source_ref=_clip_path(
            min(feat.files) if feat.files else None, MAX_NODE_SOURCE_REF
        ),
        symbol_ref=_top_member_ref(feat.members, scores)
        if scores is not None
        else None,
        evidence=ScanEvidence.EXTRACTED if scores is not None else None,
    )


def _entry_flows(
    flows: tuple[Flow, ...],
    kept_ids: set[str],
    budget: int,
    scores: dict[str, float] | None,
) -> tuple[Flow, ...]:
    """The flows that earn an `entry` node.

    Best-ranked entry point first when a shortlist exists; trace length and
    `flow_id` break ties (and carry the whole ordering in the fallback).
    """
    if budget <= 0:
        return ()
    candidates = sorted(
        (f for f in flows if f.feature_id in kept_ids), key=_entry_sort_key(scores)
    )
    return tuple(candidates[:budget])


def _entry_sort_key(scores: dict[str, float] | None):
    if scores is None:
        return lambda f: (-len(f.steps), f.flow_id)
    return lambda f: (-scores.get(f.entry_point, 0.0), -len(f.steps), f.flow_id)


def _entry_node(flow: Flow, scores: dict[str, float] | None) -> ScanNode:
    symbol_ref = None
    if scores is not None and flow.entry_point:
        ep = flow.entry_point
        symbol_ref = ep if len(ep) <= MAX_NODE_SYMBOL_REF else None
    return ScanNode(
        id=flow.flow_id,
        label=_clip(flow.entry_point_label, MAX_NODE_LABEL) or flow.flow_id,
        kind=ScanNodeKind.ENTRY,
        sub=_clip(_plural(len(flow.steps), "step"), MAX_NODE_SUB),
        source_ref=_clip_path(flow.entry_point_path, MAX_NODE_SOURCE_REF),
        symbol_ref=symbol_ref,
        evidence=ScanEvidence.EXTRACTED if scores is not None else None,
    )


def _edges(
    entries: tuple[Flow, ...],
    flows: tuple[Flow, ...],
    kept_ids: set[str],
    owner_of_file: dict[str, str],
    owner_of_symbol: dict[str, str],
    links: tuple[dict[str, Any], ...],
    max_edges: int,
) -> tuple[ScanEdge, ...]:
    """Trigger edges first, then cross-feature calls, then truncate.

    Triggers outrank calls because an entry node with no edge is an orphan
    box, whereas a missing call edge only makes the map sparser. Calls are
    ranked by how many symbol-level calls they collapse, so if the cap bites
    it keeps the connections the code leans on hardest.
    """
    triggers = [
        ScanEdge(
            from_id=fl.flow_id,
            to_id=fl.feature_id,
            kind=ScanEdgeKind.TRIGGERS,
        )
        for fl in entries
    ]

    weights = _call_weights(links, owner_of_symbol, kept_ids)

    # A flow reaching into another feature's file is the same relationship the
    # call graph describes, so it merges into the same edge at weight 1 rather
    # than drawing a second one.
    for flow in flows:
        if flow.feature_id not in kept_ids:
            continue
        for path in flow.files:
            owner = owner_of_file.get(path)
            if owner and owner != flow.feature_id and owner in kept_ids:
                weights.setdefault((flow.feature_id, owner), 1)

    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    calls = [
        ScanEdge(from_id=src, to_id=dst, kind=ScanEdgeKind.CALLS)
        for (src, dst), _weight in ranked
    ]
    return tuple((triggers + calls)[:max_edges])


def _call_weights(
    links: tuple[dict[str, Any], ...],
    owner_of_symbol: dict[str, str],
    kept_ids: set[str],
) -> dict[tuple[str, str], int]:
    """Collapse symbol-level calls into feature-to-feature edges with weights.

    Only `calls` / `uses` count — `contains`, `imports_from`, `inherits` and
    `rationale_for` describe structure, not one part of the system asking
    another to do something. A symbol the feature set does not claim is
    skipped rather than guessed at.
    """
    weights: dict[tuple[str, str], int] = {}
    for link in links:
        if not isinstance(link, dict) or link.get("relation") not in _CALL_RELATIONS:
            continue
        src = owner_of_symbol.get(link.get("source"))
        dst = owner_of_symbol.get(link.get("target"))
        if not src or not dst or src == dst:
            continue
        if src not in kept_ids or dst not in kept_ids:
            continue
        weights[(src, dst)] = weights.get((src, dst), 0) + 1
    return weights
