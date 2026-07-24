"""Frozen result models for the graph-query domain (wire via ``to_dict``)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx


def _put(payload: dict[str, Any], key: str, value: Any) -> None:
    """Optional-means-absent: only emit a key that carries a value."""
    if value is not None:
        payload[key] = value


@dataclass(frozen=True)
class GraphRow:
    """One cited answer row. ``depth`` is hops from the subject (0 = itself)."""

    node_id: str
    label: str
    citation: str  # definition site, repo-relative "path.py:L42"
    community: int
    depth: int
    relation: str | None = None
    direction: str | None = None
    site: str | None = None  # the connecting edge's own file:line
    docstring: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "node_id": self.node_id,
            "label": self.label,
            "citation": self.citation,
            "community": self.community,
            "depth": self.depth,
        }
        _put(payload, "relation", self.relation)
        _put(payload, "direction", self.direction)
        _put(payload, "site", self.site)
        _put(payload, "docstring", self.docstring)
        return payload


@dataclass(frozen=True)
class GraphQueryResult:
    """One verb's bounded answer. ``total`` counts rows before ``--limit``."""

    schema_version: int
    verb: str
    args: tuple[str, ...]
    subject: GraphRow | None
    total: int
    truncated: bool
    rows: tuple[GraphRow, ...]
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "verb": self.verb,
            "args": list(self.args),
            "total": self.total,
            "truncated": self.truncated,
            "rows": [r.to_dict() for r in self.rows],
        }
        _put(payload, "subject", self.subject.to_dict() if self.subject else None)
        _put(payload, "note", self.note)
        return payload


@dataclass(frozen=True)
class SymbolGraph:
    """Loaded artifact (internal carrier, not a wire model).

    ``digraph`` edges run true-direction ``_src → _tgt`` with ``relation``
    and pre-relativized ``site`` data; ``docstrings`` maps a symbol node id
    to its ``rationale_for`` neighbor's text.
    """

    context_dir: Path
    repo_root: Path
    digraph: nx.MultiDiGraph
    nodes: dict[str, dict[str, Any]]
    docstrings: dict[str, str]
