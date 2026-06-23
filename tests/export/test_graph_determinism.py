"""Determinism guard for ``export.graph.to_json`` (audit finding C3).

``to_json`` must emit ``symbol-graph.json`` byte-identically across runs
regardless of NetworkX-internal node/edge iteration order. These tests build
the same logical graph with the nodes/edges inserted in two different orders
and assert the written JSON is byte-for-byte identical, and that the on-disk
order is the documented sort (nodes by ``id``; links by
``(source, target, relation)`` with ``sort_keys=True``).
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from dummyindex.export.graph import to_json


def _build(edges: list[tuple[str, str, str]]) -> nx.DiGraph:
    """Build a DiGraph from (source, target, relation) triples."""
    G = nx.DiGraph()
    for src, tgt, rel in edges:
        G.add_node(src, label=src)
        G.add_node(tgt, label=tgt)
        G.add_edge(src, tgt, relation=rel)
    return G


_EDGES = [
    ("file.py:a", "file.py:b", "calls"),
    ("file.py:b", "file.py:c", "calls"),
    ("file.py:a", "file.py:c", "imports"),
    ("file.py:c", "file.py:a", "calls"),
]

_COMMUNITIES = {0: ["file.py:a", "file.py:b"], 1: ["file.py:c"]}


def test_to_json_is_byte_identical_across_insertion_orders(tmp_path: Path) -> None:
    forward = _build(_EDGES)
    reverse = _build(list(reversed(_EDGES)))

    out_forward = tmp_path / "forward.json"
    out_reverse = tmp_path / "reverse.json"
    to_json(forward, _COMMUNITIES, str(out_forward))
    to_json(reverse, _COMMUNITIES, str(out_reverse))

    assert out_forward.read_bytes() == out_reverse.read_bytes()


def test_to_json_repeated_runs_are_byte_identical(tmp_path: Path) -> None:
    G = _build(_EDGES)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    to_json(G, _COMMUNITIES, str(first))
    to_json(G, _COMMUNITIES, str(second))

    assert first.read_bytes() == second.read_bytes()


def test_to_json_sorts_nodes_and_links(tmp_path: Path) -> None:
    out = tmp_path / "graph.json"
    to_json(_build(list(reversed(_EDGES))), _COMMUNITIES, str(out))
    payload = json.loads(out.read_text(encoding="utf-8"))

    node_ids = [n["id"] for n in payload["nodes"]]
    assert node_ids == sorted(node_ids)

    link_keys = [
        (e["source"], e["target"], e.get("relation", "")) for e in payload["links"]
    ]
    assert link_keys == sorted(link_keys)


# An open hyperedge schema: members vary in fields/order so a single-field sort
# can't order them; only a total (canonical-serialization) key can.
_HYPEREDGES = [
    {"kind": "group", "members": ["file.py:b", "file.py:a"], "weight": 2},
    {"kind": "group", "members": ["file.py:a", "file.py:c"]},
    {"kind": "cluster", "members": ["file.py:c"], "weight": 1},
]


def _build_with_hyperedges(
    edges: list[tuple[str, str, str]], hyperedges: list[dict]
) -> nx.DiGraph:
    G = _build(edges)
    G.graph["hyperedges"] = hyperedges
    return G


def test_to_json_hyperedges_byte_identical_across_input_orders(tmp_path: Path) -> None:
    """A non-empty ``hyperedges`` list, fed in two different orders, must emit
    byte-identical output — proving the export sorts by a total key."""
    forward = _build_with_hyperedges(_EDGES, list(_HYPEREDGES))
    reverse = _build_with_hyperedges(_EDGES, list(reversed(_HYPEREDGES)))

    out_forward = tmp_path / "forward.json"
    out_reverse = tmp_path / "reverse.json"
    to_json(forward, _COMMUNITIES, str(out_forward))
    to_json(reverse, _COMMUNITIES, str(out_reverse))

    assert out_forward.read_bytes() == out_reverse.read_bytes()

    payload = json.loads(out_forward.read_text(encoding="utf-8"))
    assert len(payload["hyperedges"]) == len(_HYPEREDGES)
    serialized = [json.dumps(h, sort_keys=True) for h in payload["hyperedges"]]
    assert serialized == sorted(serialized)
