"""Match + rank discovered plugins against needed capabilities and/or a query.

Pure; no I/O. Capability inference reuses the shared Capability vocabulary via
the ``_PLUGIN_CAPABILITY_TOKENS`` table, matched on WHOLE WORDS (plus a few
deliberate prefix stems and a plural form) — never bare substrings, which used
to tag a brainstorming plugin as database ('orm' in 'brainstorming') and an
author tool as security ('auth' in 'author').
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..constants import _PLUGIN_CAPABILITY_TOKENS
from .marketplace import MarketplaceCatalog, PluginEntry

# Alphanumeric runs, lowercased — the same word shape proposal extraction uses.
_WORD_RE = re.compile(r"[a-z0-9]+")

# Deliberate prefix stems: 'optimi' catches optimize/optimization/optimizer,
# 'profil' catches profile/profiling/profiler. Everything else matches whole
# words only (or the simple plural), so short tokens never fire inside
# unrelated words ('db' in 'feedback', 'ui' in 'build').
_PREFIX_STEMS = frozenset({"optimi", "profil"})

# Grammatical stopwords stripped from queries: 'design to code bridge' must not
# match every plugin whose prose contains the word 'to'.
_QUERY_STOPWORDS = frozenset(
    {"a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with"}
)


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


def _words(text: str) -> frozenset[str]:
    return frozenset(_WORD_RE.findall(text.lower()))


def _token_matches(token: str, words: frozenset[str]) -> bool:
    if token in words or f"{token}s" in words:
        return True
    if token in _PREFIX_STEMS:
        return any(word.startswith(token) for word in words)
    return False


def capabilities_for(entry: PluginEntry) -> tuple[str, ...]:
    """Infer capabilities from the entry's name/description/keywords/category.

    First match in table order wins per capability; one entry can yield several.
    Whole-word matching keeps the tags deterministic and honest — the same
    plugin no longer collects different capability sets per marketplace just
    because one listing's prose happens to contain an unlucky substring.
    """
    words = _words(
        " ".join([entry.name, entry.description, entry.category or "", *entry.keywords])
    )
    found: list[str] = []
    for capability, tokens in _PLUGIN_CAPABILITY_TOKENS:
        if capability in found:
            continue
        if any(_token_matches(token, words) for token in tokens):
            found.append(capability)
    return tuple(found)


def _content_words(query: str) -> tuple[str, ...]:
    """Query words minus grammatical stopwords."""
    return tuple(
        w for w in _WORD_RE.findall(query.lower()) if w not in _QUERY_STOPWORDS
    )


def _query_hits(entry: PluginEntry, query: str) -> int:
    """Weighted whole-word query score: a name hit (2) outranks prose (1)."""
    name_words = _words(entry.name)
    other_words = _words(" ".join([entry.description, *entry.keywords]))
    score = 0
    for token in _content_words(query):
        if token in name_words:
            score += 2
        elif token in other_words:
            score += 1
    return score


def match_candidates(
    catalogs: tuple[MarketplaceCatalog, ...],
    *,
    needed_caps: tuple[str, ...] = (),
    query: str | None = None,
    force_repos: frozenset[str] = frozenset(),
) -> tuple[Candidate, ...]:
    """Rank candidates. ``score = 2*(capability overlap) + (query hits)``.

    With a query, an entry must score at least 2 query hits when the query has
    two or more content words (1 otherwise) unless it also overlaps a needed
    capability — a single incidental word no longer floods the results.
    Candidates from ``force_repos`` (explicit ``--repo``) are always kept and
    sorted first: the user named that repo, so its plugins are the answer even
    when they score 0. Sorted by (forced, score desc, plugin name asc) — stable
    and deterministic, so a re-run yields the same plan.
    """
    needed = set(needed_caps)
    required_hits = 2 if query and len(_content_words(query)) >= 2 else 1
    out: list[Candidate] = []
    for cat in catalogs:
        forced = cat.repo in force_repos
        for entry in cat.plugins:
            caps = capabilities_for(entry)
            overlap = len(needed & set(caps))
            hits = _query_hits(entry, query) if query else 0
            score = 2 * overlap + hits
            if not forced:
                if query and overlap == 0 and hits < required_hits:
                    continue
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
    out.sort(key=lambda c: (0 if c.repo in force_repos else 1, -c.score, c.plugin.name))
    return tuple(out)
