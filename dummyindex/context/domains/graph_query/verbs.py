"""The seven bounded query verbs (see the package docstring for the contract).

Every verb returns a :class:`GraphQueryResult` whose rows are
deterministically ordered, cited (``path:line``), depth-annotated, and
truncated to ``limit`` with the pre-truncation ``total`` preserved.
**Dead-code is purely graph-driven**: a code node is dead iff it has zero
incoming ``DEPENDENCY_RELATIONS`` edges; structural relations never count.
"""

from __future__ import annotations

import json
from typing import Any

import networkx as nx

from .constants import (
    COMMUNITIES_ARTIFACT,
    DEFAULT_DEAD_CODE_LIMIT,
    DEFAULT_IMPACT_DEPTH,
    DEFAULT_LIMIT,
    DEFAULT_NEIGHBOR_HOPS,
    DOCSTRING_CLIP_CHARS,
    FILE_TYPE_CODE,
    SCHEMA_VERSION,
)
from .enums import DEPENDENCY_RELATIONS, EdgeDirection, GraphRelation, GraphVerb
from .errors import UnknownSymbolError
from .load import node_citation
from .models import GraphQueryResult, GraphRow, SymbolGraph
from .resolve import _describe_candidates, resolve_symbol

# --- row / result helpers


def _clip_docstring(text: str | None) -> str | None:
    if text is None:
        return None
    flat = " ".join(text.split())
    if len(flat) > DOCSTRING_CLIP_CHARS:
        return flat[: DOCSTRING_CLIP_CHARS - 1].rstrip() + "…"
    return flat


def _community_of(node: dict[str, Any]) -> int:
    try:
        return int(node.get("community", -1))
    except (TypeError, ValueError):
        return -1


def _row(
    graph: SymbolGraph,
    node_id: str,
    *,
    depth: int,
    relation: str | None = None,
    direction: str | None = None,
    site: str | None = None,
) -> GraphRow:
    node = graph.nodes[node_id]
    ambiguous = node.get("file_type") == "ambiguity"
    candidates = (
        sorted(n for n in node.get("candidate_ids", []) if n in graph.nodes)
        if ambiguous
        else []
    )
    return GraphRow(
        node_id=node_id,
        label=str(node.get("label", node_id)),
        citation="unresolved reference" if ambiguous else node_citation(graph, node),
        community=_community_of(node),
        depth=depth,
        relation=relation,
        direction=direction,
        site=site,
        docstring=_clip_docstring(graph.docstrings.get(node_id)),
        resolution=node.get("resolution") if ambiguous else None,
        candidates=_describe_candidates(graph, candidates),
        candidate_total=len(candidates),
    )


def _require_node(graph: SymbolGraph, node_id: str) -> None:
    if node_id not in graph.nodes:
        raise UnknownSymbolError(node_id)


def _result(
    verb: GraphVerb,
    args: tuple[str, ...],
    subject: GraphRow | None,
    rows: list[GraphRow],
    limit: int,
    *,
    note: str | None = None,
) -> GraphQueryResult:
    shown = tuple(rows[: max(1, limit)])
    return GraphQueryResult(
        schema_version=SCHEMA_VERSION,
        verb=verb.value,
        args=args,
        subject=subject,
        total=len(rows),
        truncated=len(rows) > len(shown),
        rows=shown,
        note=note,
    )


# --- verbs


def callers_of(
    graph: SymbolGraph, node_id: str, *, limit: int = DEFAULT_LIMIT
) -> GraphQueryResult:
    """Direct incoming ``calls`` edges — who calls this symbol, and where."""
    return _direct_calls(
        graph,
        node_id,
        direction=EdgeDirection.IN,
        verb=GraphVerb.CALLERS_OF,
        limit=limit,
    )


def callees_of(
    graph: SymbolGraph, node_id: str, *, limit: int = DEFAULT_LIMIT
) -> GraphQueryResult:
    """Direct outgoing ``calls`` edges — what this symbol calls, and where."""
    return _direct_calls(
        graph,
        node_id,
        direction=EdgeDirection.OUT,
        verb=GraphVerb.CALLEES_OF,
        limit=limit,
    )


def _direct_calls(
    graph: SymbolGraph,
    node_id: str,
    *,
    direction: EdgeDirection,
    verb: GraphVerb,
    limit: int,
) -> GraphQueryResult:
    _require_node(graph, node_id)
    inbound = direction is EdgeDirection.IN
    adjacency = graph.digraph.pred[node_id] if inbound else graph.digraph.succ[node_id]
    found: dict[str, str | None] = {}
    for other, edges in adjacency.items():
        for data in edges.values():
            if data.get("relation") != GraphRelation.CALLS.value:
                continue
            site = data.get("site")
            prev = found.get(other)
            if other not in found or (
                site is not None and (prev is None or site < prev)
            ):
                found[other] = site
    rows = [
        _row(
            graph,
            nid,
            depth=1,
            relation=GraphRelation.CALLS.value,
            direction=direction.value,
            site=found[nid],
        )
        for nid in sorted(found)
    ]
    uncertain = sorted(
        nid
        for nid, node in graph.nodes.items()
        if node.get("file_type") == "ambiguity"
        and node_id in node.get("candidate_ids", [])
    )
    note = (
        (
            "References may also target this symbol through ambiguous nodes: "
            + ", ".join(uncertain[:10])
        )
        if uncertain
        else None
    )
    return _result(
        verb, (node_id,), _row(graph, node_id, depth=0), rows, limit, note=note
    )


def impact(
    graph: SymbolGraph,
    node_id: str,
    *,
    depth: int = DEFAULT_IMPACT_DEPTH,
    limit: int = DEFAULT_LIMIT,
) -> GraphQueryResult:
    """Transitive dependents: reverse walk over dependency edges, depth-capped."""
    _require_node(graph, node_id)
    seen: set[str] = {node_id}
    frontier: list[str] = [node_id]
    discovered: list[tuple[int, str, str]] = []  # (depth, node, relation)
    for d in range(1, max(1, depth) + 1):
        found: dict[str, str] = {}
        for cur in frontier:
            for pred, _cur, data in graph.digraph.in_edges(cur, data=True):
                rel = data.get("relation")
                if rel not in DEPENDENCY_RELATIONS or pred in seen:
                    continue
                if pred not in found or rel < found[pred]:
                    found[pred] = rel
        if not found:
            break
        frontier = sorted(found)
        for nid in frontier:
            discovered.append((d, nid, found[nid]))
            seen.add(nid)
    rows = [
        _row(graph, nid, depth=d, relation=rel, direction=EdgeDirection.IN.value)
        for d, nid, rel in discovered
    ]
    return _result(
        GraphVerb.IMPACT, (node_id,), _row(graph, node_id, depth=0), rows, limit
    )


def _edge_between(
    graph: SymbolGraph, prev: str, cur: str
) -> tuple[str, str, str | None]:
    """Deterministic (relation, direction, site) annotating the hop prev→cur."""
    out_data = graph.digraph.get_edge_data(prev, cur) or {}
    in_data = graph.digraph.get_edge_data(cur, prev) or {}
    return min(
        (
            (str(data.get("relation", "")), direction, data.get("site"))
            for edge_data, direction in (
                (out_data, EdgeDirection.OUT.value),
                (in_data, EdgeDirection.IN.value),
            )
            for data in edge_data.values()
        ),
        key=lambda o: (o[0], o[1], o[2] or ""),
    )


def path_between(
    graph: SymbolGraph, a_id: str, b_id: str, *, limit: int = DEFAULT_LIMIT
) -> GraphQueryResult:
    """Shortest undirected chain between two symbols (rationale edges excluded)."""
    _require_node(graph, a_id)
    _require_node(graph, b_id)
    undirected: nx.Graph = nx.Graph()
    undirected.add_nodes_from(graph.nodes)
    for u, v, data in graph.digraph.edges(data=True):
        if data.get("relation") == GraphRelation.RATIONALE_FOR.value:
            continue
        undirected.add_edge(u, v)
    try:
        chain: list[str] | None = nx.shortest_path(undirected, a_id, b_id)
    except nx.NetworkXNoPath:
        chain = None
    if not chain:
        return _result(
            GraphVerb.PATH,
            (a_id, b_id),
            None,
            [],
            limit,
            note=f"no path between {a_id} and {b_id}",
        )
    rows: list[GraphRow] = [_row(graph, chain[0], depth=0)]
    for i in range(1, len(chain)):
        relation, direction, site = _edge_between(graph, chain[i - 1], chain[i])
        rows.append(
            _row(
                graph,
                chain[i],
                depth=i,
                relation=relation,
                direction=direction,
                site=site,
            )
        )
    return _result(GraphVerb.PATH, (a_id, b_id), None, rows, limit)


def neighbors(
    graph: SymbolGraph,
    node_id: str,
    *,
    hops: int = DEFAULT_NEIGHBOR_HOPS,
    limit: int = DEFAULT_LIMIT,
) -> GraphQueryResult:
    """Every node within N hops over any relation except ``rationale_for``."""
    _require_node(graph, node_id)
    seen: set[str] = {node_id}
    frontier: list[str] = [node_id]
    discovered: list[tuple[int, str, str, str, str | None]] = []
    for d in range(1, max(1, hops) + 1):
        found: dict[str, tuple[str, str, str | None]] = {}
        for cur in frontier:
            for pred, _cur, data in graph.digraph.in_edges(cur, data=True):
                rel = str(data.get("relation", ""))
                if rel == GraphRelation.RATIONALE_FOR.value or pred in seen:
                    continue
                cand = (rel, EdgeDirection.IN.value, data.get("site"))
                if pred not in found or cand[:2] < found[pred][:2]:
                    found[pred] = cand
            for _cur, succ, data in graph.digraph.out_edges(cur, data=True):
                rel = str(data.get("relation", ""))
                if rel == GraphRelation.RATIONALE_FOR.value or succ in seen:
                    continue
                cand = (rel, EdgeDirection.OUT.value, data.get("site"))
                if succ not in found or cand[:2] < found[succ][:2]:
                    found[succ] = cand
        if not found:
            break
        frontier = sorted(found)
        for nid in frontier:
            rel, direction, site = found[nid]
            discovered.append((d, nid, rel, direction, site))
            seen.add(nid)
    rows = [
        _row(graph, nid, depth=d, relation=rel, direction=direction, site=site)
        for d, nid, rel, direction, site in discovered
    ]
    return _result(
        GraphVerb.NEIGHBORS, (node_id,), _row(graph, node_id, depth=0), rows, limit
    )


def dead_code(
    graph: SymbolGraph, *, limit: int = DEFAULT_DEAD_CODE_LIMIT
) -> GraphQueryResult:
    """Code nodes with zero incoming dependency edges (see module docstring)."""
    dead: list[str] = []
    uncertain = {
        candidate
        for node in graph.nodes.values()
        if node.get("file_type") == "ambiguity"
        and node.get("resolution") == "ambiguous"
        for candidate in node.get("candidate_ids", [])
    }
    for nid, node in graph.nodes.items():
        if node.get("file_type") != FILE_TYPE_CODE or nid in uncertain:
            continue
        has_dependent = any(
            data.get("relation") in DEPENDENCY_RELATIONS
            for _u, _v, data in graph.digraph.in_edges(nid, data=True)
        )
        if not has_dependent:
            dead.append(nid)
    dead.sort(key=lambda nid: _location_sort_key(graph.nodes[nid], nid))
    rows = [_row(graph, nid, depth=0) for nid in dead]
    note = (
        "graph-driven precision: symbols reached only via dispatch-dict values "
        "or function-body imports may be false positives until those edges are "
        "extracted"
    )
    return _result(GraphVerb.DEAD_CODE, (), None, rows, limit, note=note)


def _location_sort_key(node: dict[str, Any], nid: str) -> tuple[str, int, str]:
    source_file = node.get("source_file")
    path = source_file if isinstance(source_file, str) else "~"
    loc = node.get("source_location")
    line = 0
    if isinstance(loc, str) and loc.startswith("L"):
        try:
            line = int(loc[1:])
        except ValueError:
            pass
    return (path, line, nid)


def community(
    graph: SymbolGraph, key: str, *, limit: int = DEFAULT_LIMIT
) -> GraphQueryResult:
    """Members of one graph community, ranked by dependency degree.

    ``key`` is a community integer, a slug/name from the (optional)
    ``features/graph-communities.json`` artifact, or any symbol form
    accepted by :func:`resolve_symbol` (falls back to that symbol's own
    community).
    """
    cid = _resolve_community_key(graph, key)
    members = sorted(
        (
            nid
            for nid, node in graph.nodes.items()
            if node.get("file_type") == FILE_TYPE_CODE and _community_of(node) == cid
        ),
        key=lambda nid: (-_dependency_degree(graph, nid), nid),
    )
    rows = [_row(graph, nid, depth=0) for nid in members]
    return _result(
        GraphVerb.COMMUNITY,
        (str(key),),
        None,
        rows,
        limit,
        note=f"community {cid}: {len(members)} member(s)",
    )


def _dependency_degree(graph: SymbolGraph, node_id: str) -> int:
    return sum(
        data.get("relation") in DEPENDENCY_RELATIONS
        for adjacency in (graph.digraph.pred[node_id], graph.digraph.succ[node_id])
        for edges in adjacency.values()
        for data in edges.values()
    )


def _resolve_community_key(graph: SymbolGraph, key: str) -> int:
    try:
        return int(key)
    except ValueError:
        pass
    from_slug = _community_from_slug(graph, key)
    if from_slug is not None:
        return from_slug
    node_id = resolve_symbol(graph, key)
    return _community_of(graph.nodes[node_id])


def _community_from_slug(graph: SymbolGraph, key: str) -> int | None:
    """Look ``key`` up in ``features/graph-communities.json`` when present.

    The artifact **deliberately carries no partition integer** (raw partition
    ids renumber between runs), so a card's identity is its slug and
    *members*; the int is recovered from the first card member still in the
    loaded graph. ``None`` when the artifact is absent or unreadable.
    """
    path = graph.context_dir / "features" / COMMUNITIES_ARTIFACT
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = payload.get("communities") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return None
    wanted = key.strip().lower()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        names = {
            str(entry[k]).lower() for k in ("slug", "name") if entry.get(k) is not None
        }
        if wanted not in names:
            continue
        cid = _community_of_members(graph, entry.get("members"))
        if cid is not None:
            return cid
    return None


def _community_of_members(graph: SymbolGraph, members: Any) -> int | None:
    """Community int of the first card member present in the loaded graph.

    Members are ranked on the card, so the first hit is the top-ranked
    surviving symbol; stale ids (renamed since the artifact was written)
    are skipped rather than failing the whole lookup.
    """
    if not isinstance(members, list):
        return None
    for member in members:
        member_id = member.get("id") if isinstance(member, dict) else None
        if not isinstance(member_id, str) or member_id not in graph.nodes:
            continue
        cid = _community_of(graph.nodes[member_id])
        if cid >= 0:
            return cid
    return None
