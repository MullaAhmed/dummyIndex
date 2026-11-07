"""Determinism guard for ``analysis.cluster.cluster``.

Community IDs must be stable run-to-run: partitioning is seeded with
``_RANDOM_SEED``, and the size-descending re-index breaks ties on the smallest
member, so equal-size communities get a content-determined order.
"""

from __future__ import annotations

import networkx as nx
import pytest

from dummyindex.analysis.cluster import (
    _MAX_COMMUNITY_FRACTION,
    _MIN_SPLIT_SIZE,
    cluster,
)


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


# --- always-Louvain for committed bytes
# The committed ``community`` field is NetworkX-Louvain only, so its bytes are
# reproducible with or without graspologic. The primary proof is byte-identical
# output across two runs; the "Leiden never called" spy is secondary and skips.


def _barbell_with_oversized_community() -> nx.Graph:
    """A graph whose largest community exceeds the split threshold.

    A 24-node clique (> 25% of nodes, ≥ ``_MIN_SPLIT_SIZE``) forces ``cluster``
    onto the recursive ``_split_community`` branch. Two satellite triangles
    keep the clique a clear majority so the oversize split fires.
    """
    G = nx.Graph()
    clique = [f"k{i:02d}" for i in range(24)]
    for i, a in enumerate(clique):
        for b in clique[i + 1 :]:
            G.add_edge(a, b)
    # A couple of small, weakly attached satellite communities.
    for prefix in ("z", "y"):
        n0, n1, n2 = f"{prefix}0", f"{prefix}1", f"{prefix}2"
        G.add_edge(n0, n1)
        G.add_edge(n1, n2)
        G.add_edge(n2, n0)
    # One thin bridge so the satellites are not isolates of the clique.
    G.add_edge("k00", "z0")
    G.add_edge("k01", "y0")
    return G


def test_committed_community_bytes_identical_across_two_runs() -> None:
    """Primary proof: serialized ``community`` is byte-identical across runs.

    The graph hits the recursive ``_split_community`` branch; output is compared
    as JSON to mirror what gets committed to ``symbol-graph.json``.
    """
    import json

    G = _barbell_with_oversized_community()

    # Sanity: the clique must exceed the split threshold so the split path runs.
    max_size = max(_MIN_SPLIT_SIZE, int(G.number_of_nodes() * _MAX_COMMUNITY_FRACTION))
    assert max_size < 24  # the 24-clique is oversized → split path runs

    first = cluster(G)
    second = cluster(G)

    first_bytes = json.dumps({k: v for k, v in sorted(first.items())}, sort_keys=True)
    second_bytes = json.dumps({k: v for k, v in sorted(second.items())}, sort_keys=True)
    assert first_bytes == second_bytes


def test_committed_path_uses_louvain_not_leiden() -> None:
    """Guarded Leiden spy: the committed path never calls ``_leiden_partition``.

    Vacuous without graspologic, so it skips then; with graspologic installed it
    spies on ``_leiden_partition`` and asserts zero calls.
    """
    pytest.importorskip("graspologic")

    from dummyindex.analysis import cluster as cluster_mod

    calls: list[object] = []
    original = cluster_mod._leiden_partition

    def _spy(G):  # pragma: no cover - only runs when graspologic present
        calls.append(G)
        return original(G)

    cluster_mod._leiden_partition = _spy  # type: ignore[assignment]
    try:
        cluster(_barbell_with_oversized_community())
    finally:
        cluster_mod._leiden_partition = original  # type: ignore[assignment]

    assert calls == []  # committed path must never call Leiden
