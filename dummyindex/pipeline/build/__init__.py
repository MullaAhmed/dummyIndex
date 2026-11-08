"""Build the structure / NetworkX graph from extraction output.

- ``build_from_json`` (this module) — assemble a NetworkX graph from extraction
  node + edge dicts, validating via ``.validate`` first.
- ``build_structure`` (``.structure``) — the folder/file/class/function
  hierarchy behind ``tree.json`` and ``map/symbols.json``.
- ``validate_extraction`` (``.validate``) — schema-check an extraction dict.
"""

from __future__ import annotations

import re
import sys

import networkx as nx

from .structure import build_structure
from .validate import validate_extraction

__all__ = [
    "build",
    "build_from_json",
    "build_structure",
    "validate_extraction",
]


def _normalize_id(s: str) -> str:
    """Normalize an ID string the same way extract._make_id does.

    Used to reconcile edge endpoints when the LLM generates IDs with slightly
    different punctuation or casing than the AST extractor.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return cleaned.strip("_").lower()


def build_from_json(extraction: dict, *, directed: bool = False) -> nx.Graph:
    """Build a NetworkX graph from an extraction dict.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    """
    if "edges" not in extraction and "links" in extraction:
        extraction = dict(extraction, edges=extraction["links"])

    for node in extraction.get("nodes", []):
        if isinstance(node, dict) and "source" in node and "source_file" not in node:
            node["source_file"] = node.pop("source")

    errors = validate_extraction(extraction)
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(
            f"[dummyindex] Extraction warning ({len(real_errors)} issues): {real_errors[0]}",
            file=sys.stderr,
        )
    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for node in extraction.get("nodes", []):
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    node_set = set(G.nodes())
    norm_to_id: dict[str, str] = {_normalize_id(nid): nid for nid in node_set}
    for edge in extraction.get("edges", []):
        if "source" not in edge and "from" in edge:
            edge["source"] = edge["from"]
        if "target" not in edge and "to" in edge:
            edge["target"] = edge["to"]
        if "source" not in edge or "target" not in edge:
            continue
        src, tgt = edge["source"], edge["target"]
        if src not in node_set:
            src = norm_to_id.get(_normalize_id(src), src)
        if tgt not in node_set:
            tgt = norm_to_id.get(_normalize_id(tgt), tgt)
        if src not in node_set or tgt not in node_set:
            continue
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        G.add_edge(src, tgt, **attrs)
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        G.graph["hyperedges"] = hyperedges
    return G


def build(extractions: list[dict], *, directed: bool = False) -> nx.Graph:
    """Merge multiple extraction results into one graph.

    ``directed`` is as in :func:`build_from_json`. Extractions merge in order:
    for a shared node ID the last one's attributes win (NetworkX add_node
    overwrites), so pass AST results first to let semantic labels win.
    """
    combined: dict = {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    return build_from_json(combined, directed=directed)
