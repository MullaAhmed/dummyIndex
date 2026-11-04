"""Graph export: ``to_json``.

The deterministic build writes ``features/symbol-graph.json`` via this
exporter. The interactive feature viewer (``features/graph.html``) is
generated separately from the ``VIEWER_HTML`` template in
``context/output/viewer.py`` — not from this module.
"""

from __future__ import annotations

import json
import os
import warnings

import networkx as nx
from networkx.readwrite import json_graph

from dummyindex.pipeline.enums import ConfidenceLevel

from .common import (
    _CONFIDENCE_SCORE_DEFAULTS,
    _node_community_map,
    _strip_diacritics,
)

# Byte size at which ``to_json`` warns. GitHub's hard limit is 100 MB; 50 MB
# leaves room for several doublings of repo growth before a push can fail.
GRAPH_SIZE_WARN_BYTES = 50 * 1024 * 1024


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
    # Sort nodes/links before dump so the emitted JSON is byte-identical
    # across runs regardless of NetworkX-internal iteration order, matching
    # the sort-before-write convention the other artifact writers enforce.
    data["nodes"].sort(key=lambda n: n["id"])
    data["links"].sort(key=lambda e: (e["source"], e["target"], e.get("relation", "")))
    # Surface hyperedges at the top level, sorted by a total key. The hyperedge
    # schema is open (``validate.py`` does not constrain its fields), so any
    # single field is insufficient to order them stably — a full canonical
    # serialization is. ``node_link_data`` also copies ``G.graph`` (including
    # ``hyperedges``) into ``data["graph"]``; re-sort that copy too so the
    # whole emitted JSON is byte-identical across runs.
    hyperedges = sorted(
        getattr(G, "graph", {}).get("hyperedges", []),
        key=lambda h: json.dumps(h, sort_keys=True),
    )
    data["hyperedges"] = hyperedges
    if isinstance(data.get("graph"), dict) and "hyperedges" in data["graph"]:
        data["graph"]["hyperedges"] = hyperedges
    # Compact separators, not indent=2: pretty-printing inflates the bytes
    # (~1.3x measured on a 20k-node/80k-edge graph; the Oct session's manual
    # compaction of a real graph measured 104.41 MB -> 85.64 MiB) and
    # repeatedly pushed real symbol graphs past GitHub's 100 MB file-size
    # limit (issue: generated symbol graphs block Git pushes). Sorting is
    # unchanged, so output stays byte-identical across runs.
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), sort_keys=True)
    # Compaction only halves the growth rate; a large enough repo still
    # outgrows the limit. Warn with headroom so a too-big graph is caught at
    # generation time instead of at the next failed `git push`.
    size = os.path.getsize(output_path)
    if size > GRAPH_SIZE_WARN_BYTES:
        warnings.warn(
            f"symbol graph is {size / 1024 / 1024:.1f} MiB "
            f"(warn threshold {GRAPH_SIZE_WARN_BYTES // 1024 // 1024} MiB); "
            "GitHub rejects files over 100 MB — gitignore the graph, split "
            "it, or trim scope before it blocks a push",
            stacklevel=2,
        )
