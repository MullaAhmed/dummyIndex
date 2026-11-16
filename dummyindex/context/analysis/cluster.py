"""Community detection on NetworkX graphs; splits oversized communities.

The committed ``community`` field uses NetworkX-Louvain only, so it is
byte-reproducible across machines; Leiden (graspologic) is available off-path for
non-committed use.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import sys

import networkx as nx

# Fixed seed, shared by the Louvain and Leiden paths, so community IDs are stable
# run-to-run.
_RANDOM_SEED = 42


def _suppress_output():
    """Context manager that captures stdout in a ``StringIO`` during library calls.

    graspologic's leiden() emits ANSI escapes (progress bars, colored warnings)
    that corrupt PowerShell 5.1's scroll buffer on Windows (issue #19). Only
    stdout is redirected here; the caller swaps ``sys.stderr`` itself.
    """
    return contextlib.redirect_stdout(io.StringIO())


def _louvain_partition(G: nx.Graph) -> dict[str, int]:
    """Community detection via NetworkX-Louvain only. Returns {node_id: community_id}.

    The committed ``community`` field in ``symbol-graph.json`` MUST come from seeded,
    pure-Python Louvain so its bytes reproduce on any machine, with or without
    graspologic. Leiden is never consulted: the committed path ``cluster`` →
    ``_partition`` → ``_split_community`` calls only this. ``max_level`` is passed
    only where NetworkX supports it; it prevents hangs on large sparse graphs.
    """
    kwargs: dict = {"seed": _RANDOM_SEED, "threshold": 1e-4}
    if "max_level" in inspect.signature(nx.community.louvain_communities).parameters:
        kwargs["max_level"] = 10
    communities = nx.community.louvain_communities(G, **kwargs)
    return {node: cid for cid, nodes in enumerate(communities) for node in nodes}


def _leiden_partition(G: nx.Graph) -> dict[str, int]:
    """Community detection via Leiden (graspologic), for NON-committed use only.

    MUST NOT feed the committed ``community`` field (only ``_louvain_partition``
    does). Raises ``ImportError`` if graspologic is not installed. Its output is
    suppressed: ANSI escapes corrupt PowerShell 5.1's scroll buffer on Windows.
    """
    from graspologic.partition import leiden

    old_stderr = sys.stderr
    try:
        sys.stderr = io.StringIO()
        with _suppress_output():
            result = leiden(G, random_seed=_RANDOM_SEED)
    finally:
        sys.stderr = old_stderr
    return result


def _partition(G: nx.Graph) -> dict[str, int]:
    """Partition for the COMMITTED-bytes path. Returns {node_id: community_id}.

    Always Louvain (see ``_louvain_partition``); Leiden is never called here, so
    graspologic's presence cannot change the committed ``community`` bytes.
    """
    return _louvain_partition(G)


_MAX_COMMUNITY_FRACTION = 0.25  # communities larger than 25% of graph get split
_MIN_SPLIT_SIZE = 10  # only split if community has at least this many nodes


def cluster(G: nx.Graph) -> dict[int, list[str]]:
    """Run community detection. Returns {community_id: [node_ids]}.

    IDs are stable across runs AND machines (0 = largest after splitting): the
    committed ``community`` field is NetworkX-Louvain only, never Leiden (see
    ``_louvain_partition``). Communities larger than max(10, 25% of nodes) get a
    second Louvain pass. DiGraphs are made undirected first (Louvain needs that).
    """
    if G.number_of_nodes() == 0:
        return {}
    if G.is_directed():
        G = G.to_undirected()
    if G.number_of_edges() == 0:
        return {i: [n] for i, n in enumerate(sorted(G.nodes))}

    # Partition only connected nodes; isolates are appended below.
    isolates = [n for n in G.nodes() if G.degree(n) == 0]
    connected_nodes = [n for n in G.nodes() if G.degree(n) > 0]
    connected = G.subgraph(connected_nodes)

    raw: dict[int, list[str]] = {}
    if connected.number_of_nodes() > 0:
        partition = _partition(connected)
        for node, cid in partition.items():
            raw.setdefault(cid, []).append(node)

    # Each isolate becomes its own single-node community
    next_cid = max(raw.keys(), default=-1) + 1
    for node in isolates:
        raw[next_cid] = [node]
        next_cid += 1

    # Split oversized communities
    max_size = max(_MIN_SPLIT_SIZE, int(G.number_of_nodes() * _MAX_COMMUNITY_FRACTION))
    final_communities: list[list[str]] = []
    for nodes in raw.values():
        if len(nodes) > max_size:
            final_communities.extend(_split_community(G, nodes))
        else:
            final_communities.append(nodes)

    # Re-index by size descending, breaking ties on the lexicographically
    # smallest member so equal-size communities get a content-determined
    # (not partition-determined) order — community IDs stay stable run-to-run.
    final_communities.sort(key=lambda c: (-len(c), sorted(c)[0]))
    return {i: sorted(nodes) for i, nodes in enumerate(final_communities)}


def _split_community(G: nx.Graph, nodes: list[str]) -> list[list[str]]:
    """Run a second Louvain pass on a community subgraph to split it further.

    Committed-bytes path — calls ``_partition`` (Louvain only).
    """
    subgraph = G.subgraph(nodes)
    if subgraph.number_of_edges() == 0:
        # No edges - split into individual nodes
        return [[n] for n in sorted(nodes)]
    try:
        sub_partition = _partition(subgraph)
        sub_communities: dict[int, list[str]] = {}
        for node, cid in sub_partition.items():
            sub_communities.setdefault(cid, []).append(node)
        if len(sub_communities) <= 1:
            return [sorted(nodes)]
        return [sorted(v) for v in sub_communities.values()]
    except Exception:
        return [sorted(nodes)]
