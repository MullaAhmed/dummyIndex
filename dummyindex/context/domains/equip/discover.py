"""Match + rank discovered plugins against needed capabilities and/or a query.

Pure; no I/O. Capability inference reuses the shared Capability vocabulary via
the ``_PLUGIN_CAPABILITY_TOKENS`` table.
"""
from __future__ import annotations

from dataclasses import dataclass

from ._constants import _PLUGIN_CAPABILITY_TOKENS
from .marketplace import MarketplaceCatalog, PluginEntry


@dataclass(frozen=True)
class Candidate:
    """One ranked match: a plugin, where it lives, and why it scored."""

    plugin: PluginEntry
    marketplace: str
    repo: str
    trusted: bool
    is_collection: bool
    capabilities: tuple[str, ...]
    score: int


def capabilities_for(entry: PluginEntry) -> tuple[str, ...]:
    """Infer capabilities from the entry's name/description/keywords/category.

    First match in table order wins per capability; one entry can yield several.
    """
    haystack = " ".join(
        [entry.name, entry.description, entry.category or "", *entry.keywords]
    ).lower()
    found: list[str] = []
    for capability, tokens in _PLUGIN_CAPABILITY_TOKENS:
        if capability in found:
            continue
        if any(tok in haystack for tok in tokens):
            found.append(capability)
    return tuple(found)


def _query_hits(entry: PluginEntry, query: str) -> int:
    haystack = " ".join([entry.name, entry.description, *entry.keywords]).lower()
    return sum(1 for tok in query.lower().split() if tok and tok in haystack)


def match_candidates(
    catalogs: tuple[MarketplaceCatalog, ...],
    *,
    needed_caps: tuple[str, ...] = (),
    query: str | None = None,
) -> tuple[Candidate, ...]:
    """Rank candidates. ``score = 2*(capability overlap) + (query token hits)``.

    Candidates scoring 0 are dropped. Sorted by score desc, then plugin name asc
    — stable and deterministic, so a re-run yields the same plan.
    """
    needed = set(needed_caps)
    out: list[Candidate] = []
    for cat in catalogs:
        for entry in cat.plugins:
            caps = capabilities_for(entry)
            overlap = len(needed & set(caps))
            hits = _query_hits(entry, query) if query else 0
            score = 2 * overlap + hits
            if score <= 0:
                continue
            out.append(
                Candidate(
                    plugin=entry,
                    marketplace=cat.name,
                    repo=cat.repo,
                    trusted=cat.trusted,
                    is_collection=cat.is_collection,
                    capabilities=caps,
                    score=score,
                )
            )
    out.sort(key=lambda c: (-c.score, c.plugin.name))
    return tuple(out)
