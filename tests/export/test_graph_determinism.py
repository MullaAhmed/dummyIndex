"""Determinism guard for ``export.graph.to_json``.

The same logical graph inserted in two orders must write byte-identical
``symbol-graph.json``, sorted nodes by ``id`` and links by
``(source, target, relation)`` with ``sort_keys=True``.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from dummyindex.export.graph import to_json
from dummyindex.export.storage import read_graph_payload


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
    assert "hyperedges" not in payload["graph"]
    assert forward.graph["hyperedges"] == _HYPEREDGES


def test_to_json_retains_multigraph_keys_directions_and_full_attributes(
    tmp_path: Path,
) -> None:
    graph = nx.MultiDiGraph()
    graph.graph.update(description="retained metadata", hyperedges=[{"custom": True}])
    graph.add_node(
        "external://a",
        label="A",
        source_file="src/a.py",
        custom={"items": [1, None, False]},
    )
    graph.add_node("b", label="B", source_file="src/b.py")
    for key in ("second", "first"):
        graph.add_edge(
            "external://a",
            "b",
            key=key,
            relation="calls",
            _src="b",
            _tgt="external://a",
            custom={"edge": key},
        )
    path = tmp_path / "graph.json"
    to_json(graph, {0: ["external://a", "b"]}, str(path))
    payload = read_graph_payload(path)
    assert payload["directed"] and payload["multigraph"]
    assert payload["graph"] == {"description": "retained metadata"}
    assert payload["hyperedges"] == [{"custom": True}]
    assert {edge["key"] for edge in payload["links"]} == {"first", "second"}
    assert all(
        edge["_src"] == "b" and edge["_tgt"] == "external://a"
        for edge in payload["links"]
    )
    assert next(node for node in payload["nodes"] if node["id"] == "external://a")[
        "custom"
    ] == {"items": [1, None, False]}
    assert graph.graph["hyperedges"] == [{"custom": True}]
