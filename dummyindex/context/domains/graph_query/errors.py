"""Typed exception hierarchy for the graph-query domain."""

from __future__ import annotations

from pathlib import Path


class GraphQueryError(Exception):
    """Base for every graph-query failure."""


class GraphArtifactMissingError(GraphQueryError):
    """``features/symbol-graph.json`` is not on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"symbol graph not found: {path}")


class GraphArtifactInvalidError(GraphQueryError):
    """The artifact exists but is not readable node-link JSON."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"symbol graph at {path} is invalid: {reason}")


class UnknownSymbolError(GraphQueryError):
    """No node matches the symbol query."""

    def __init__(self, query: str) -> None:
        self.query = query
        super().__init__(f"unknown symbol: {query!r}")


class AmbiguousSymbolError(GraphQueryError):
    """More than one node matches; ``candidates`` are cited descriptions."""

    def __init__(self, query: str, candidates: tuple[str, ...], total: int) -> None:
        self.query = query
        self.candidates = candidates
        self.total = total
        super().__init__(f"ambiguous symbol {query!r}: {total} candidates")
