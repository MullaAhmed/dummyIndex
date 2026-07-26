"""Symbol lookup: node id, bare name, ``path:name`` suffix, or prefix."""

from __future__ import annotations

from typing import Any

from .constants import FILE_TYPE_RATIONALE, MAX_CANDIDATES_LISTED
from .errors import AmbiguousSymbolError, UnknownSymbolError
from .load import node_citation
from .models import SymbolGraph


def _bare_name(label: str) -> str:
    """Lookup key for a node label.

    Functions/methods (``helper()``, ``.run()``, ``Cls.run()``) reduce to
    the bare callable name; classes and modules (``Sub``, ``app.py``) keep
    the whole label. Lower-cased for case-insensitive matching.
    """
    if label.endswith("()"):
        return label.removesuffix("()").rsplit(".", 1)[-1].lower()
    return label.lower()


def _code_ids(graph: SymbolGraph) -> list[str]:
    """Lookup targets: every non-rationale node (docstrings aren't symbols)."""
    return [
        nid
        for nid, node in graph.nodes.items()
        if node.get("file_type") != FILE_TYPE_RATIONALE
    ]


def _path_suffix_match(source_file: Any, suffix: str) -> bool:
    """True when ``suffix`` matches ``source_file`` on a path boundary."""
    if not isinstance(source_file, str) or not suffix:
        return False
    sf = source_file.replace("\\", "/").lower()
    suf = suffix.replace("\\", "/").lower().lstrip("/")
    if not sf.endswith(suf):
        return False
    return len(sf) == len(suf) or sf[-len(suf) - 1] == "/"


def _describe_candidates(graph: SymbolGraph, node_ids: list[str]) -> tuple[str, ...]:
    out: list[str] = []
    for nid in node_ids[:MAX_CANDIDATES_LISTED]:
        node = graph.nodes[nid]
        cite = node_citation(graph, node)
        out.append(f"{nid} — {node.get('label', '')} ({cite})")
    return tuple(out)


def resolve_symbol(graph: SymbolGraph, query: str) -> str:
    """Resolve a user-supplied symbol to a node id.

    Accepted forms, tried in order: exact node id, bare name
    (``helper`` / ``app.py``), ``path:name`` suffix
    (``cli/common.py:resolve_context_root``), and finally an unambiguous
    prefix of a node id or bare name. Raises
    :class:`AmbiguousSymbolError` (with cited candidates) when several
    nodes match and :class:`UnknownSymbolError` when none do.
    """
    q = query.strip()
    if not q:
        raise UnknownSymbolError(query)
    if q in graph.nodes:
        return q
    ql = q.lower()
    candidates = _code_ids(graph)

    exact = sorted(
        nid
        for nid in candidates
        if _bare_name(str(graph.nodes[nid].get("label", ""))) == ql
    )
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise AmbiguousSymbolError(q, _describe_candidates(graph, exact), len(exact))

    if ":" in q:
        path_part, _, name_part = q.rpartition(":")
        nl = name_part.strip().lower()
        hits = sorted(
            nid
            for nid in candidates
            if _bare_name(str(graph.nodes[nid].get("label", ""))) == nl
            and _path_suffix_match(graph.nodes[nid].get("source_file"), path_part)
        )
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise AmbiguousSymbolError(q, _describe_candidates(graph, hits), len(hits))

    prefix = sorted(
        nid
        for nid in candidates
        if nid.lower().startswith(ql)
        or _bare_name(str(graph.nodes[nid].get("label", ""))).startswith(ql)
    )
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        raise AmbiguousSymbolError(q, _describe_candidates(graph, prefix), len(prefix))
    raise UnknownSymbolError(q)
