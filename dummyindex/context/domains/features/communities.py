"""`features/graph-communities.json` — the community mid-tier, rolled up.

One card per symbol-graph community: a **stable slug** (dominant owning
feature + top member name — never the raw partition integer, which
renumbers between runs), the community's size, its top members by
personalized PageRank with `path:line` citations, the owning feature from
the curated taxonomy, and a deterministic one-line summary lifted from
the top member's docstring (`rationale_for` nodes).

Frozen dataclasses with `to_dict()` beside them — the same contract as
`scan/models.py`. The roll-up here is pure (plain dicts in, frozen data
out); the builder that computes PageRank, gathers the inputs and writes
the artifact lives in `context/build/communities.py`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .helpers import _range_from_location, _rel
from .scan import slugify

COMMUNITIES_SCHEMA_VERSION = 1

# Written beside `symbol-graph.json`. Committed and diffed, so cards are
# sorted by slug and members by rank — ordering is part of the contract.
GRAPH_COMMUNITIES_FILENAME = "graph-communities.json"

# Top members listed per community card.
COMMUNITY_TOP_K = 10

# The card is a mid-tier headline, not a spec.
_MAX_COMMUNITY_SLUG = 60
_MAX_COMMUNITY_SUMMARY = 120

# Node `file_type` minted by the docstring/comment post-pass — these nodes
# annotate symbols, they are not symbols, so they never count as members.
_RATIONALE_FILE_TYPE = "rationale"


@dataclass(frozen=True)
class CommunityMember:
    """One top-ranked symbol on a community card."""

    id: str
    label: str
    score: float
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "label": self.label, "score": self.score}
        if self.path:
            out["path"] = self.path
        return out


@dataclass(frozen=True)
class GraphCommunity:
    """One community card. `slug` is the stable identity, never the int."""

    slug: str
    size: int
    members: tuple[CommunityMember, ...]
    feature: str | None = None
    summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"slug": self.slug, "size": self.size}
        if self.feature:
            out["feature"] = self.feature
        if self.summary:
            out["summary"] = self.summary
        out["members"] = [m.to_dict() for m in self.members]
        return out


@dataclass(frozen=True)
class GraphCommunities:
    """The whole artifact, cards sorted by slug."""

    communities: tuple[GraphCommunity, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": COMMUNITIES_SCHEMA_VERSION,
            "communities": [c.to_dict() for c in self.communities],
        }


def rollup_communities(
    node_by_id: Mapping[str, Mapping[str, Any]],
    communities: Mapping[int, Sequence[str]],
    scores: Mapping[str, float],
    *,
    owner_of_symbol: Mapping[str, str] | None = None,
    rationale_of: Mapping[str, str] | None = None,
    root: Path | None = None,
    top_k: int = COMMUNITY_TOP_K,
) -> GraphCommunities:
    """Roll the raw partition up into stable, feature-owned cards.

    ``communities`` is `analysis.cluster`'s `{int: [node_ids]}` output —
    the int is dropped on the floor, deliberately: partition ids renumber
    between runs, so identity comes from what the community *contains*.
    ``owner_of_symbol`` maps symbol ids to `features/INDEX.json` feature
    ids (empty when no taxonomy exists yet). ``rationale_of`` maps a
    symbol id to its docstring text. Output is fully sorted so the
    committed artifact is byte-stable for identical inputs.
    """
    owners = owner_of_symbol or {}
    rationales = rationale_of or {}

    cards: list[GraphCommunity] = []
    for community_id in sorted(communities, key=str):
        member_ids = communities[community_id]
        symbols = [
            m
            for m in member_ids
            if m in node_by_id
            and node_by_id[m].get("file_type") != _RATIONALE_FILE_TYPE
        ]
        if not symbols:
            continue
        ranked = sorted(symbols, key=lambda m: (-scores.get(m, 0.0), m))
        dominant = _dominant_feature(ranked, owners)
        cards.append(
            GraphCommunity(
                slug=_community_slug(dominant, node_by_id[ranked[0]]),
                size=len(symbols),
                members=tuple(
                    _member(m, node_by_id[m], scores.get(m, 0.0), root)
                    for m in ranked[:top_k]
                ),
                feature=dominant,
                summary=_community_summary(ranked, rationales),
            )
        )

    # Sort on content (slug, then size, then top member id) *before* slug
    # dedup so the ordinal a colliding card receives is itself stable.
    cards.sort(key=lambda c: (c.slug, -c.size, c.members[0].id if c.members else ""))
    return GraphCommunities(communities=tuple(_dedupe_slugs(cards)))


def _dominant_feature(
    symbols: Sequence[str], owner_of_symbol: Mapping[str, str]
) -> str | None:
    """The feature owning the plurality of members; count then id breaks ties."""
    counts = Counter(owner_of_symbol[m] for m in symbols if owner_of_symbol.get(m))
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _community_slug(dominant: str | None, top_node: Mapping[str, Any]) -> str:
    """`<dominant-feature>-<top-member-name>`, slugified and capped.

    Never the raw partition int: the Leiden/Louvain ids renumber between
    runs, and this artifact is committed — a renumbered identity would be
    pure diff noise and would break every `symbolRef` pinned to it.
    """
    label = str(top_node.get("label") or "").strip()
    base = f"{dominant} {label}" if dominant else label
    slug = slugify(base, fallback="community")
    return slug[:_MAX_COMMUNITY_SLUG].rstrip("-") or "community"


def _community_summary(
    ranked: Sequence[str], rationale_of: Mapping[str, str]
) -> str | None:
    """First line of the best-ranked member docstring, or nothing at all."""
    for member in ranked:
        text = rationale_of.get(member, "").strip()
        if not text:
            continue
        line = text.splitlines()[0].strip()
        if len(line) > _MAX_COMMUNITY_SUMMARY:
            line = line[: _MAX_COMMUNITY_SUMMARY - 1].rstrip() + "…"
        return line or None
    return None


def _member(
    member_id: str,
    node: Mapping[str, Any],
    score: float,
    root: Path | None,
) -> CommunityMember:
    path = _rel(node.get("source_file"), root)
    span = _range_from_location(node.get("source_location"))
    if path and span:
        path = f"{path}:{span[0]}"
    return CommunityMember(
        id=member_id,
        label=str(node.get("label") or member_id),
        score=score,
        path=path,
    )


def _dedupe_slugs(cards: Sequence[GraphCommunity]) -> list[GraphCommunity]:
    """Append a deterministic ordinal to repeated slugs (`x`, `x-2`, `x-3`).

    Probes against everything emitted so far, so an ordinal never collides
    with a slug another card holds naturally.
    """
    emitted: set[str] = set()
    out: list[GraphCommunity] = []
    for card in cards:
        slug = card.slug
        ordinal = 1
        while slug in emitted:
            ordinal += 1
            slug = f"{card.slug}-{ordinal}"
        emitted.add(slug)
        if slug == card.slug:
            out.append(card)
        else:
            out.append(
                GraphCommunity(
                    slug=slug,
                    size=card.size,
                    members=card.members,
                    feature=card.feature,
                    summary=card.summary,
                )
            )
    return out
