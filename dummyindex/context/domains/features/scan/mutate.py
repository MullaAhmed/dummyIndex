"""Surgical edits to an on-disk scan, for the feature ops.

`rename_feature`, `merge_feature` and `remove_flow` all have to keep
`graph.json` in step without re-deriving it — a curated scan can't be
re-derived, so "just rebuild it" is not available to them. Each edit lives
here rather than inline at the three call sites so the wire shape is known
in exactly one place.

Every function returns a **new** payload, or `None` when nothing matched.
`None` is what lets a caller skip the write (and skip claiming it touched
a file it didn't).

All three tolerate a payload that isn't a v2 scan — a legacy v1 graph, a
half-written file — by returning `None`. An op that renames a feature
should not be the thing that fails on an artifact it doesn't own.
"""

from __future__ import annotations

import copy
from typing import Any

from dummyindex.context.enums import ScanNodeKind


def _graph_of(payload: Any) -> tuple[list[Any], list[Any]] | None:
    """Pull `(nodes, edges)` out of a v2 payload, or None if it isn't one."""
    if not isinstance(payload, dict):
        return None
    graph = payload.get("graph")
    if not isinstance(graph, dict):
        return None
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    return nodes, edges


def _rebuilt(
    payload: dict[str, Any], nodes: list[Any], edges: list[Any]
) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    out["graph"] = {**out.get("graph", {}), "nodes": nodes, "edges": edges}
    return out


def rename_node(
    payload: Any, *, from_id: str, to_id: str, new_label: str | None = None
) -> dict[str, Any] | None:
    """Rename node ``from_id`` to ``to_id``, rewriting every edge endpoint.

    ``new_label`` replaces the display label. When it is omitted, a label
    that merely echoed the old id is updated to echo the new one, and a
    label someone actually wrote is left alone.
    """
    parts = _graph_of(payload)
    if parts is None:
        return None
    nodes, edges = parts

    changed = False
    new_nodes: list[Any] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("id") != from_id:
            new_nodes.append(node)
            continue
        updated = {**node, "id": to_id}
        if new_label is not None:
            updated["label"] = new_label
        elif node.get("label") == from_id:
            updated["label"] = to_id
        new_nodes.append(updated)
        changed = True

    new_edges: list[Any] = []
    for edge in edges:
        if not isinstance(edge, dict):
            new_edges.append(edge)
            continue
        updated = dict(edge)
        for side in ("from", "to"):
            if updated.get(side) == from_id:
                updated[side] = to_id
                changed = True
        new_edges.append(updated)

    return _rebuilt(payload, new_nodes, new_edges) if changed else None


def drop_nodes(payload: Any, ids: set[str]) -> dict[str, Any] | None:
    """Remove ``ids`` and every edge that touches one of them."""
    parts = _graph_of(payload)
    if parts is None or not ids:
        return None
    nodes, edges = parts

    new_nodes = [n for n in nodes if not (isinstance(n, dict) and n.get("id") in ids)]
    new_edges = [
        e
        for e in edges
        if not (isinstance(e, dict) and (e.get("from") in ids or e.get("to") in ids))
    ]
    if len(new_nodes) == len(nodes) and len(new_edges) == len(edges):
        return None
    return _rebuilt(payload, new_nodes, new_edges)


def drop_feature(payload: Any, feature_id: str) -> dict[str, Any] | None:
    """Remove a feature node, plus any entry point that fed only that feature.

    An `entry` whose sole reason to exist was triggering the removed
    feature becomes an orphan box the moment the feature goes — but an
    entry that also triggers something else is still doing a job, so it
    stays and only the edge disappears.
    """
    parts = _graph_of(payload)
    if parts is None:
        return None
    nodes, edges = parts

    orphans = {
        node["id"]
        for node in nodes
        if isinstance(node, dict)
        and node.get("kind") == ScanNodeKind.ENTRY.value
        and isinstance(node.get("id"), str)
        and _neighbours(node["id"], edges) == {feature_id}
    }
    return drop_nodes(payload, {feature_id} | orphans)


def _neighbours(node_id: str, edges: list[Any]) -> set[str]:
    """Every other node this one shares an edge with, in either direction."""
    out: set[str] = set()
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src, dst = edge.get("from"), edge.get("to")
        if src == node_id and isinstance(dst, str):
            out.add(dst)
        elif dst == node_id and isinstance(src, str):
            out.add(src)
    return out
