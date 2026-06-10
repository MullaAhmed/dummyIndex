"""Graph export: ``to_json``.

The deterministic build writes ``features/symbol-graph.json`` via this
exporter. The interactive feature viewer (``features/graph.html``) is
generated separately from the ``VIEWER_HTML`` template in
``context/output/viewer.py`` — not from this module.
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

import json

import networkx as nx
from networkx.readwrite import json_graph

from .common import (
    _CONFIDENCE_SCORE_DEFAULTS,
    _node_community_map,
    _strip_diacritics,
)


def to_json(G: nx.Graph, communities: dict[int, list[str]], output_path: str) -> None:
    node_community = _node_community_map(communities)
    try:
        data = json_graph.node_link_data(G, edges="links")
    except TypeError:
        data = json_graph.node_link_data(G)
    for node in data["nodes"]:
        node["community"] = node_community.get(node["id"])
        node["norm_label"] = _strip_diacritics(node.get("label", "")).lower()
    for link in data["links"]:
        if "confidence_score" not in link:
            conf = link.get("confidence", ConfidenceLevel.EXTRACTED)
            link["confidence_score"] = _CONFIDENCE_SCORE_DEFAULTS.get(conf, 1.0)
    data["hyperedges"] = getattr(G, "graph", {}).get("hyperedges", [])
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
