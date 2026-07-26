"""The `graph-extras` island: tier-2 community cards + tier-3 expansion index.

The viewer's second data island, built in Python at render time so the
emitted `graph.html` stays a single self-contained file:

- **Tier 2** — one supernode per `features/graph-communities.json` card,
  with cross-community call volume (from `symbol-graph.json` links) as
  edge weights.
- **Tier 3** — a bounded, precomputed expansion index: for every curated
  node whose `symbolRef` resolves to a symbol-graph node, its top-k
  neighbors ranked by the seed's PageRank (`seed-rank.json`), each with a
  `path:line` citation. The full 11MB symbol graph is **never** inlined —
  entries are truncated whole, by rank, under a hard byte budget enforced
  here at embed time.

Degradation is deliberate, mirroring `scan/refs.py`: a missing or
unreadable artifact contributes nothing, and an empty result leaves the
viewer's placeholder island untouched (tier 2 hidden, nothing expands).

Deliberately **stdlib-only**: `domains/features` imports this package's
`render_viewer_html` (via `builder`/`indexes`/`ops`), so importing
`domains.features.*` or `context.build.*` from here would be a cycle.
The few tolerant-loader helpers duplicated below (`_indexed_root`,
`_rel`, `_start_line`) note their canonical twins.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Neighbors revealed per expanded node, and the hard cap on the serialized
# expansion index (measured exactly as `to_dict()["expansion"]` embeds:
# `ensure_ascii=False, indent=2, sort_keys=True`, utf-8 bytes).
EXPANSION_TOP_K = 8
EXPANSION_BUDGET_BYTES = 300 * 1024

# Symbol labels come from arbitrary extracted identifiers; the ghost box
# they render into is one line tall.
_MAX_LABEL = 160

# Canonical names live beside their writers (`scan/rank.py`,
# `domains/features/communities.py`, `build/graph.py`); duplicated here to
# stay import-cycle-free (see module docstring).
_SYMBOL_GRAPH_FILENAME = "symbol-graph.json"
_GRAPH_COMMUNITIES_FILENAME = "graph-communities.json"
_SEED_RANK_FILENAME = "seed-rank.json"

# Mirrors `build/communities.py`: the relations that count as call volume,
# and the docstring/comment nodes that annotate symbols without being one.
_CALL_RELATIONS = frozenset({"calls", "uses"})
_RATIONALE_FILE_TYPE = "rationale"
_RATIONALE_RELATION = "rationale_for"

_DIR_OUT = "out"
_DIR_IN = "in"


@dataclass(frozen=True)
class ExpansionNeighbor:
    """One revealed symbol-graph neighbor of an expanded curated node."""

    id: str
    label: str
    relation: str
    direction: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "relation": self.relation,
            "dir": self.direction,
        }
        if self.path:
            out["path"] = self.path
        return out


@dataclass(frozen=True)
class CommunityMemberView:
    """One top symbol on a tier-2 card, as the viewer needs it."""

    id: str
    label: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "label": self.label}
        if self.path:
            out["path"] = self.path
        return out


@dataclass(frozen=True)
class CommunityCardView:
    """One tier-2 supernode: a `graph-communities.json` card, trimmed."""

    slug: str
    size: int
    members: tuple[CommunityMemberView, ...] = ()
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
class CommunityLink:
    """Cross-community call volume between two tier-2 supernodes."""

    from_slug: str
    to_slug: str
    weight: int

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.from_slug, "to": self.to_slug, "weight": self.weight}


@dataclass(frozen=True)
class ViewerExtras:
    """Everything the viewer's tier-2/tier-3 behavior consumes."""

    communities: tuple[CommunityCardView, ...] = ()
    community_links: tuple[CommunityLink, ...] = ()
    expansion: tuple[tuple[str, tuple[ExpansionNeighbor, ...]], ...] = ()

    def is_empty(self) -> bool:
        return not (self.communities or self.community_links or self.expansion)

    def to_dict(self) -> dict[str, Any]:
        return {
            "communities": [c.to_dict() for c in self.communities],
            "communityLinks": [link.to_dict() for link in self.community_links],
            "expansion": {
                ref: [n.to_dict() for n in neighbors]
                for ref, neighbors in self.expansion
            },
        }


def build_viewer_extras(
    scan: Mapping[str, Any],
    cards_payload: Any,
    graph_payload: Any,
    rank_payload: Any,
    *,
    root: Path | None = None,
    top_k: int = EXPANSION_TOP_K,
    budget_bytes: int = EXPANSION_BUDGET_BYTES,
) -> ViewerExtras:
    """Derive the extras island from already-loaded artifact payloads.

    Pure — the file I/O lives in `load_viewer_extras`. Any payload may be
    ``None`` (artifact absent) and each tier degrades independently.
    """
    cards = _cards(cards_payload)
    node_by_id, links = _graph_parts(graph_payload)
    scores = _scores(rank_payload)
    root_abs = root.resolve() if root is not None else None
    return ViewerExtras(
        communities=cards,
        community_links=_community_links(cards, node_by_id, links),
        expansion=_expansion(
            scan,
            node_by_id,
            links,
            scores,
            root_abs,
            top_k=top_k,
            budget_bytes=budget_bytes,
        ),
    )


def load_viewer_extras(scan: Mapping[str, Any], features_dir: Path) -> ViewerExtras:
    """Read the on-disk artifacts under ``features_dir`` and build the extras.

    Missing or unreadable artifacts contribute nothing — a repo without a
    community roll-up still renders its curated map exactly as before.
    """
    return build_viewer_extras(
        scan,
        _read_json(features_dir / _GRAPH_COMMUNITIES_FILENAME),
        _read_json(features_dir / _SYMBOL_GRAPH_FILENAME),
        _read_json(features_dir / _SEED_RANK_FILENAME),
        root=_indexed_root(features_dir),
    )


# ----- tier 2: cards + cross-community call volume ---------------------------


def _cards(payload: Any) -> tuple[CommunityCardView, ...]:
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("communities")
    if not isinstance(raw, list):
        return ()
    cards: list[CommunityCardView] = []
    for card in raw:
        if not isinstance(card, dict):
            continue
        slug = card.get("slug")
        if not isinstance(slug, str) or not slug:
            continue
        size = card.get("size")
        cards.append(
            CommunityCardView(
                slug=slug,
                size=size
                if isinstance(size, int) and not isinstance(size, bool)
                else 0,
                members=_card_members(card.get("members")),
                feature=_opt_str(card.get("feature")),
                summary=_opt_str(card.get("summary")),
            )
        )
    cards.sort(key=lambda c: c.slug)
    return tuple(cards)


def _card_members(raw: Any) -> tuple[CommunityMemberView, ...]:
    if not isinstance(raw, list):
        return ()
    members: list[CommunityMemberView] = []
    for member in raw:
        if not isinstance(member, dict):
            continue
        member_id = member.get("id")
        if not isinstance(member_id, str) or not member_id:
            continue
        members.append(
            CommunityMemberView(
                id=member_id,
                label=_clip(_opt_str(member.get("label")) or member_id),
                path=_opt_str(member.get("path")),
            )
        )
    return tuple(members)


def _community_links(
    cards: Sequence[CommunityCardView],
    node_by_id: Mapping[str, Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
) -> tuple[CommunityLink, ...]:
    """Aggregate `calls`/`uses` volume between the partitions the cards name.

    Cards deliberately dropped the raw partition int (it renumbers between
    runs), so each card is re-anchored to a partition by majority vote over
    its listed members; first card (in slug order) to claim a partition
    keeps it.
    """
    partition_of = {
        node_id: node.get("community")
        for node_id, node in node_by_id.items()
        if isinstance(node.get("community"), int)
        and not isinstance(node.get("community"), bool)
    }
    slug_of: dict[int, str] = {}
    for card in cards:
        counts = Counter(
            partition_of[m.id] for m in card.members if m.id in partition_of
        )
        if not counts:
            continue
        dominant = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        slug_of.setdefault(dominant, card.slug)

    weights: dict[tuple[str, str], int] = defaultdict(int)
    for link in links:
        if link.get("relation") not in _CALL_RELATIONS:
            continue
        src = link.get("_src", link.get("source"))
        tgt = link.get("_tgt", link.get("target"))
        from_slug = slug_of.get(partition_of.get(src, -1))  # type: ignore[arg-type]
        to_slug = slug_of.get(partition_of.get(tgt, -1))  # type: ignore[arg-type]
        if not from_slug or not to_slug or from_slug == to_slug:
            continue
        weights[(from_slug, to_slug)] += 1

    return tuple(
        CommunityLink(from_slug=a, to_slug=b, weight=weights[(a, b)])
        for a, b in sorted(weights)
    )


# ----- tier 3: the bounded expansion index -----------------------------------


def _expansion(
    scan: Mapping[str, Any],
    node_by_id: Mapping[str, Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    scores: Mapping[str, float],
    root_abs: Path | None,
    *,
    top_k: int,
    budget_bytes: int,
) -> tuple[tuple[str, tuple[ExpansionNeighbor, ...]], ...]:
    refs = _scan_refs(scan, node_by_id)
    if not refs:
        return ()
    adjacency = _adjacency(node_by_id, links)

    # Highest-ranked curated symbols first, so the byte budget below always
    # truncates a rank-ordered prefix — never an arbitrary subset.
    ranked_refs = sorted(refs, key=lambda ref: (-scores.get(ref, 0.0), ref))

    kept: list[tuple[str, tuple[ExpansionNeighbor, ...]]] = []
    for ref in ranked_refs:
        neighbors = _neighbors_for(ref, adjacency, node_by_id, scores, root_abs, top_k)
        if not neighbors:
            continue
        candidate = [*kept, (ref, neighbors)]
        if _expansion_bytes(candidate) > budget_bytes:
            break
        kept = candidate
    return tuple(kept)


def _scan_refs(
    scan: Mapping[str, Any], node_by_id: Mapping[str, Mapping[str, Any]]
) -> set[str]:
    """`symbolRef` values that resolve to a real (non-rationale) symbol node.

    A ref pointing at a community slug or at nothing degrades to "this node
    doesn't expand" — the same tolerance `scan/refs.py` extends.
    """
    graph = scan.get("graph")
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(nodes, list):
        return set()
    refs: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ref = node.get("symbolRef")
        if not isinstance(ref, str) or ref not in node_by_id:
            continue
        if node_by_id[ref].get("file_type") == _RATIONALE_FILE_TYPE:
            continue
        refs.add(ref)
    return refs


def _adjacency(
    node_by_id: Mapping[str, Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
) -> dict[str, list[tuple[str, str, str]]]:
    """``{node_id: [(neighbor_id, relation, direction), ...]}``.

    Direction reflects the original orientation (`_src`/`_tgt`, falling
    back to storage order). Rationale nodes and their `rationale_for`
    edges never appear — they annotate symbols, they are not neighbors.
    """
    out: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for link in links:
        relation = link.get("relation")
        if not isinstance(relation, str) or relation == _RATIONALE_RELATION:
            continue
        src = link.get("_src", link.get("source"))
        tgt = link.get("_tgt", link.get("target"))
        if not isinstance(src, str) or not isinstance(tgt, str) or src == tgt:
            continue
        if src not in node_by_id or tgt not in node_by_id:
            continue
        if (
            node_by_id[src].get("file_type") == _RATIONALE_FILE_TYPE
            or node_by_id[tgt].get("file_type") == _RATIONALE_FILE_TYPE
        ):
            continue
        out[src].append((tgt, relation, _DIR_OUT))
        out[tgt].append((src, relation, _DIR_IN))
    return out


def _neighbors_for(
    ref: str,
    adjacency: Mapping[str, list[tuple[str, str, str]]],
    node_by_id: Mapping[str, Mapping[str, Any]],
    scores: Mapping[str, float],
    root_abs: Path | None,
    top_k: int,
) -> tuple[ExpansionNeighbor, ...]:
    candidates = sorted(
        adjacency.get(ref, []),
        key=lambda c: (-scores.get(c[0], 0.0), c[0], c[1], c[2]),
    )
    picked: list[ExpansionNeighbor] = []
    seen: set[str] = set()
    for neighbor_id, relation, direction in candidates:
        if neighbor_id in seen:
            continue
        seen.add(neighbor_id)
        node = node_by_id[neighbor_id]
        picked.append(
            ExpansionNeighbor(
                id=neighbor_id,
                label=_clip(_opt_str(node.get("label")) or neighbor_id),
                relation=relation,
                direction=direction,
                path=_cite(node, root_abs),
            )
        )
        if len(picked) >= top_k:
            break
    return tuple(picked)


def _expansion_bytes(
    entries: Sequence[tuple[str, tuple[ExpansionNeighbor, ...]]],
) -> int:
    """Size of the expansion map exactly as `_embed` will serialize it."""
    wire = {ref: [n.to_dict() for n in neighbors] for ref, neighbors in entries}
    return len(
        json.dumps(wire, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    )


# ----- tolerant loaders (canonical twins noted; duplicated for cycle-freedom) --


def _read_json(path: Path) -> Any:
    """Read a JSON artifact, or ``None`` when missing/unreadable/malformed."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _graph_parts(
    payload: Any,
) -> tuple[dict[str, dict[str, Any]], tuple[dict[str, Any], ...]]:
    if not isinstance(payload, dict):
        return {}, ()
    nodes = payload.get("nodes")
    links = payload.get("links") or payload.get("edges")
    node_by_id = {
        node["id"]: node
        for node in (nodes if isinstance(nodes, list) else ())
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    return node_by_id, tuple(
        link
        for link in (links if isinstance(links, list) else ())
        if isinstance(link, dict)
    )


def _scores(payload: Any) -> dict[str, float]:
    """Mirror of `scan/rank.load_seed_rank`'s tolerance, on a loaded payload."""
    if not isinstance(payload, dict):
        return {}
    ranked = payload.get("ranked")
    if not isinstance(ranked, list):
        return {}
    out: dict[str, float] = {}
    for row in ranked:
        if not isinstance(row, dict):
            continue
        node_id = row.get("id")
        score = row.get("score")
        if not isinstance(node_id, str) or not node_id:
            continue
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            continue
        out.setdefault(node_id, float(score))
    return out


def _indexed_root(features_dir: Path) -> Path:
    """Twin of `build/communities._indexed_root` (duplicated: import cycle)."""
    context_dir = features_dir.parent
    fallback = context_dir.parent
    payload = _read_json(context_dir / "meta.json")
    recorded = payload.get("root") if isinstance(payload, dict) else None
    return Path(recorded) if isinstance(recorded, str) and recorded else fallback


def _cite(node: Mapping[str, Any], root_abs: Path | None) -> str | None:
    path = _rel(node.get("source_file"), root_abs)
    if not path:
        return None
    line = _start_line(node.get("source_location"))
    return f"{path}:{line}" if line is not None else path


def _rel(p: Any, root_abs: Path | None) -> str | None:
    """Twin of `domains/features/helpers._rel` (duplicated: import cycle)."""
    if not isinstance(p, str) or not p:
        return None
    if root_abs is None:
        return p
    try:
        return Path(p).resolve().relative_to(root_abs).as_posix()
    except (ValueError, OSError):
        return p


def _start_line(location: Any) -> int | None:
    """Parse `L148` / `L148-L160` to its start line, or ``None``."""
    if not isinstance(location, str):
        return None
    head = location.strip().lstrip("L").split("-", 1)[0].lstrip("L")
    try:
        return int(head)
    except ValueError:
        return None


def _opt_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value or None


def _clip(text: str) -> str:
    return text if len(text) <= _MAX_LABEL else text[:_MAX_LABEL]
