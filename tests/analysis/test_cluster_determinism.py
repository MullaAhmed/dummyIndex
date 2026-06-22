"""Determinism guard for ``analysis.cluster.cluster`` (audit finding C2).

Community-ID assignment must be stable run-to-run. The Leiden (graspologic)
path is now seeded with ``_RANDOM_SEED`` (matching the Louvain fallback), and
the final size-descending re-index breaks ties on the lexicographically
smallest member so equal-size communities get a content-determined order
rather than a partition-dependent one. These tests assert the same input
yields an identical ``{community_id: [node_ids]}`` mapping across repeated
runs, on whichever backend is installed.
"""
from __future__ import annotations

import networkx as nx

from dummyindex.analysis.cluster import cluster


def _three_equal_triangles() -> nx.Graph:
    """Three disjoint, equal-size triangle communities.

    Equal sizes force the size-descending sort onto its secondary key, so a
    missing/length-only sort would leave the inter-community order
    partition-dependent.
    """
    G = nx.Graph()
    for prefix in ("c", "a", "b"):  # insert out of lexical order on purpose
        n0, n1, n2 = f"{prefix}0", f"{prefix}1", f"{prefix}2"
        G.add_edge(n0, n1)
        G.add_edge(n1, n2)
        G.add_edge(n2, n0)
    return G


def test_cluster_is_stable_across_runs() -> None:
    G = _three_equal_triangles()
    first = cluster(G)
    second = cluster(G)
    assert first == second


def test_equal_size_communities_ordered_by_smallest_member() -> None:
    result = cluster(_three_equal_triangles())
    # Three equal-size communities → IDs assigned by smallest member.
    first_members = [sorted(members)[0] for _cid, members in sorted(result.items())]
    assert first_members == sorted(first_members)


def test_cluster_members_are_sorted_within_community() -> None:
    result = cluster(_three_equal_triangles())
    for members in result.values():
        assert members == sorted(members)
