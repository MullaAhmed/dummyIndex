"""The id universe a `ScanNode.symbolRef` may resolve into.

A curated scan pins repo-owned nodes to the extraction layer via
`symbolRef` — a `features/symbol-graph.json` node id today, and a
`features/graph-communities.json` community id once the community roll-up
lands. Referential integrity across those artifacts is what keeps a
curated box from silently pointing at a symbol that a refactor renamed.

`validate_scan` stays pure, so the file I/O lives here: the loader walks
the ``REF_ARTIFACTS`` registry, reads whichever artifacts exist under the
`features/` dir, and hands back one frozen `SymbolRefIndex`. Degradation
is deliberate — a missing or unreadable artifact contributes nothing, and
when *none* could be read the loader returns ``None`` so the caller
reports the check as skipped (a warning), never as a scan error.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RefArtifact:
    """One artifact under `features/` that mints resolvable ids."""

    relative_path: str
    extract: Callable[[Any], frozenset[str]]


def _symbol_graph_ids(payload: Any) -> frozenset[str]:
    """Node ids from the NetworkX node-link wire shape (`{"nodes": [...]}`)."""
    if not isinstance(payload, dict):
        return frozenset()
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return frozenset()
    return frozenset(
        node["id"]
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    )


def _community_slugs(payload: Any) -> frozenset[str]:
    """Community slugs from `graph-communities.json` (`{"communities": [...]}`)."""
    if not isinstance(payload, dict):
        return frozenset()
    communities = payload.get("communities")
    if not isinstance(communities, list):
        return frozenset()
    return frozenset(
        card["slug"]
        for card in communities
        if isinstance(card, dict) and isinstance(card.get("slug"), str)
    )


# The registry `load_symbol_ref_index` walks. Adding an artifact is one
# entry here and nothing else.
REF_ARTIFACTS: tuple[RefArtifact, ...] = (
    RefArtifact("symbol-graph.json", _symbol_graph_ids),
    RefArtifact("graph-communities.json", _community_slugs),
)


@dataclass(frozen=True)
class SymbolRefIndex:
    """Every id a `symbolRef` may point at, and which artifacts minted them."""

    ids: frozenset[str]
    sources: tuple[str, ...]

    def resolves(self, ref: str) -> bool:
        return ref in self.ids


def load_symbol_ref_index(features_dir: Path) -> SymbolRefIndex | None:
    """Read every registered artifact under ``features_dir`` into one index.

    Returns ``None`` when no registered artifact could be read at all —
    the caller degrades the `symbolRef` check to a warning. An artifact
    that parses but yields no ids still counts as a source: it is present,
    so refs are expected to resolve against it.
    """
    ids: set[str] = set()
    sources: list[str] = []
    for artifact in REF_ARTIFACTS:
        path = features_dir / artifact.relative_path
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        ids.update(artifact.extract(payload))
        sources.append(artifact.relative_path)
    if not sources:
        return None
    return SymbolRefIndex(ids=frozenset(ids), sources=tuple(sources))
