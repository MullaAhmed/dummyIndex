"""Load ``features/symbol-graph.json`` into a directed multigraph.

The artifact is an **undirected** networkx node-link export whose links
live under the ``links`` key. networkx normalises ``source``/``target``
on undirected graphs, so the true direction of every link is carried in
its ``_src``/``_tgt`` attributes — ``_src calls _tgt``, ``_src
rationale_for _tgt`` — and this loader reads only those.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from .enums import GraphRelation
from .errors import GraphArtifactInvalidError, GraphArtifactMissingError
from .models import SymbolGraph


def citation_for(repo_root: Path, source_file: Any, source_location: Any) -> str | None:
    """``/abs/pkg/mod.py`` + ``L42`` → ``pkg/mod.py:L42`` (repo-relative)."""
    if not isinstance(source_file, str) or not source_file:
        return None
    p = Path(source_file)
    try:
        rel = p.relative_to(repo_root)
    except ValueError:
        rel = p
    loc = (
        source_location
        if isinstance(source_location, str) and source_location
        else "L?"
    )
    return f"{rel.as_posix()}:{loc}"


def node_citation(graph: SymbolGraph, node: dict[str, Any]) -> str:
    """A node's own definition site; ``?`` when the artifact carries none."""
    cite = citation_for(
        graph.repo_root, node.get("source_file"), node.get("source_location")
    )
    return cite if cite is not None else "?"


def load_symbol_graph(context_dir: Path) -> SymbolGraph:
    """Load ``features/symbol-graph.json`` into a directed multigraph.

    Raises :class:`GraphArtifactMissingError` when the artifact is absent
    and :class:`GraphArtifactInvalidError` when it is unreadable or not
    node-link shaped. Read-only — never writes.
    """
    context_dir = context_dir.resolve()
    path = context_dir / "features" / "symbol-graph.json"
    if not path.is_file():
        raise GraphArtifactMissingError(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GraphArtifactInvalidError(path, f"not valid JSON: {exc}") from exc
    except OSError as exc:
        raise GraphArtifactInvalidError(path, f"unreadable: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("nodes"), list)
        or not isinstance(payload.get("links"), list)
    ):
        raise GraphArtifactInvalidError(
            path, "expected node-link JSON with 'nodes' and 'links' lists"
        )

    repo_root = context_dir.parent
    nodes: dict[str, dict[str, Any]] = {}
    for raw in payload["nodes"]:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            nodes[raw["id"]] = raw

    digraph: nx.MultiDiGraph = nx.MultiDiGraph()
    digraph.add_nodes_from(nodes)
    docstrings: dict[str, str] = {}
    doc_source: dict[str, str] = {}  # symbol id → rationale node id (min wins)
    for link in payload["links"]:
        if not isinstance(link, dict):
            continue
        src = link.get("_src")
        tgt = link.get("_tgt")
        if not isinstance(src, str) or not isinstance(tgt, str):
            continue
        if src not in nodes or tgt not in nodes:
            continue
        relation = str(link.get("relation", ""))
        site = citation_for(
            repo_root, link.get("source_file"), link.get("source_location")
        )
        digraph.add_edge(src, tgt, relation=relation, site=site)
        if relation == GraphRelation.RATIONALE_FOR.value:
            src_file = nodes[src].get("source_file")
            tgt_file = nodes[tgt].get("source_file")
            co_located = (
                isinstance(src_file, str)
                and src_file
                and isinstance(tgt_file, str)
                and src_file == tgt_file
            )
            text = nodes[src].get("label")
            if co_located and isinstance(text, str) and text.strip():
                # Deterministic pick when several co-located rationale nodes
                # attach: the lowest rationale node id wins.
                if tgt not in doc_source or src < doc_source[tgt]:
                    doc_source[tgt] = src
                    docstrings[tgt] = text.strip()

    return SymbolGraph(
        context_dir=context_dir,
        repo_root=repo_root,
        digraph=digraph,
        nodes=nodes,
        docstrings=docstrings,
    )
