"""Deterministic graph artifacts: personalized PageRank + community roll-up.

Runs right after `features/symbol-graph.json` is written (wired in
`build.graph.build_graph`) and derives two committed artifacts from the
same in-memory graph:

- ``features/seed-rank.json`` — the ranked shortlist the scan seed
  consumes (`domains/features/scan/rank.py`). Personalized PageRank
  seeded on entry-point symbols and non-test files, with test files
  down-weighted: the bakeoff showed test nodes dominate the raw degree
  signal, and a seed ranked by test plumbing is a seed nobody wants.
- ``features/graph-communities.json`` — one card per community
  (`domains/features/communities.py`), owning feature read from the
  on-disk taxonomy when one exists.

Both are EXTRACTED backbone: `rebuild --changed` regenerates them freely
and neither ever touches the curated `features/graph.json`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

import networkx as nx

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.features.communities import (
    GRAPH_COMMUNITIES_FILENAME,
    rollup_communities,
)
from dummyindex.context.domains.features.scan.rank import (
    SEED_RANK_FILENAME,
    RankEntry,
    SeedRank,
)

# PageRank personalization. Entry points are where a reader starts, so
# they seed hardest; ordinary source keeps full weight; test files keep a
# sliver so they still rank *somewhere* without drowning the signal.
_PAGERANK_ALPHA = 0.85
_PAGERANK_MAX_ITER = 100
_PAGERANK_TOL = 1e-6
_ENTRY_WEIGHT = 3.0
_SOURCE_WEIGHT = 1.0
_TEST_WEIGHT = 0.1

# Shortlist shape: enough depth for the seed's feature aggregation, small
# enough to stay a reviewable committed artifact. Scores are rounded so
# the emitted JSON doesn't churn on float noise.
_RANK_TOP_N = 500
_SCORE_DECIMALS = 8

# Mirrors `features/constants._CALL_RELATIONS` (package-private there):
# the relations that make a node an entry point when nothing calls it.
_CALL_RELATIONS = frozenset({"calls", "uses"})

_RATIONALE_FILE_TYPE = "rationale"
_RATIONALE_RELATION = "rationale_for"

_TEST_DIR_NAMES = frozenset({"tests", "test", "__tests__", "testing"})


def compute_symbol_rank(g: nx.Graph) -> dict[str, float]:
    """Personalized PageRank over the symbol graph. Empty graph → `{}`.

    Pure-Python power iteration, NOT `networkx.pagerank`: NetworkX 3.x
    delegates that to scipy, which dummyindex does not depend on — and the
    same GATE reasoning that pinned committed communities to always-Louvain
    applies here: an optional numeric backend whose presence varies per
    machine must never decide committed bytes. Semantics match
    `nx.pagerank(g, alpha, personalization, weight=None)` on an undirected
    graph; a run that hasn't converged after the iteration cap returns the
    last (still deterministic) iterate rather than raising.
    """
    if g.number_of_nodes() == 0:
        return {}
    return _pagerank(
        g,
        alpha=_PAGERANK_ALPHA,
        personalization=_personalization(g),
        max_iter=_PAGERANK_MAX_ITER,
        tol=_PAGERANK_TOL,
    )


def _pagerank(
    g: nx.Graph,
    *,
    alpha: float,
    personalization: dict[str, float],
    max_iter: int,
    tol: float,
) -> dict[str, float]:
    """Unweighted personalized PageRank by power iteration.

    Iteration walks nodes in graph insertion order, so the float sums —
    and therefore the emitted bytes — are reproducible run to run.
    """
    nodes = list(g)
    total_weight = sum(personalization.get(n, 0.0) for n in nodes)
    if total_weight <= 0.0:
        uniform = 1.0 / len(nodes)
        p = dict.fromkeys(nodes, uniform)
    else:
        p = {n: personalization.get(n, 0.0) / total_weight for n in nodes}

    degree = {n: g.degree(n) for n in nodes}
    x = dict(p)
    for _ in range(max_iter):
        xlast = x
        x = dict.fromkeys(nodes, 0.0)
        dangle_sum = alpha * sum(xlast[n] for n in nodes if degree[n] == 0)
        for n in nodes:
            if degree[n] == 0:
                continue
            share = alpha * xlast[n] / degree[n]
            for neighbour in g.neighbors(n):
                x[neighbour] += share
        for n in nodes:
            x[n] += dangle_sum * p[n] + (1.0 - alpha) * p[n]
        if sum(abs(x[n] - xlast[n]) for n in nodes) < len(nodes) * tol:
            break
    return x


def build_seed_rank(
    scores: dict[str, float],
    node_by_id: dict[str, dict[str, Any]],
    *,
    top_n: int = _RANK_TOP_N,
) -> SeedRank:
    """Round, drop rationale nodes, sort by score-then-id, truncate."""
    rows: list[tuple[float, str]] = []
    for node_id, score in scores.items():
        node = node_by_id.get(node_id) or {}
        if node.get("file_type") == _RATIONALE_FILE_TYPE:
            continue
        rows.append((round(float(score), _SCORE_DECIMALS), node_id))
    rows.sort(key=lambda row: (-row[0], row[1]))
    return SeedRank(
        entries=tuple(RankEntry(id=nid, score=s) for s, nid in rows[:top_n])
    )


def write_graph_artifacts(
    g: nx.Graph,
    communities: dict[int, list[str]],
    features_dir: Path,
    *,
    root: Path | None = None,
) -> tuple[str, ...]:
    """Write both derived artifacts under ``features_dir``.

    ``root`` anchors the `path:line` citations; when the caller doesn't
    have one it falls back to the root ingest recorded in `meta.json`
    (written before the graph step on every build path), then to the
    context dir's parent. Returns the artifact names relative to
    `.context/`, in write order.
    """
    root_abs = (root or _indexed_root(features_dir)).resolve()
    node_by_id: dict[str, dict[str, Any]] = dict(g.nodes(data=True))

    scores = compute_symbol_rank(g)
    seed_rank = build_seed_rank(scores, node_by_id)
    _write_json(features_dir / SEED_RANK_FILENAME, seed_rank.to_dict())
    written = [f"features/{SEED_RANK_FILENAME}"]

    cards = rollup_communities(
        node_by_id,
        communities,
        scores,
        owner_of_symbol=_load_feature_ownership(features_dir),
        rationale_of=_rationales(g),
        root=root_abs,
    )
    _write_json(features_dir / GRAPH_COMMUNITIES_FILENAME, cards.to_dict())
    written.append(f"features/{GRAPH_COMMUNITIES_FILENAME}")
    return tuple(written)


# ----- pagerank inputs -------------------------------------------------------


def _personalization(g: nx.Graph) -> dict[str, float]:
    entry_points = _entry_point_ids(g)
    out: dict[str, float] = {}
    for node_id, data in g.nodes(data=True):
        if _is_test_path(str(data.get("source_file") or "")):
            out[node_id] = _TEST_WEIGHT
        elif node_id in entry_points:
            out[node_id] = _ENTRY_WEIGHT
        else:
            out[node_id] = _SOURCE_WEIGHT
    return out


def _entry_point_ids(g: nx.Graph) -> set[str]:
    """Call-subgraph sources: out-edges but no in-edges.

    The graph is stored undirected, but every edge carries its original
    orientation in `_src`/`_tgt` (see `pipeline.build.build_from_json`),
    so direction survives; fall back to storage order when absent.
    """
    in_deg: dict[str, int] = defaultdict(int)
    out_deg: dict[str, int] = defaultdict(int)
    for u, v, data in g.edges(data=True):
        if data.get("relation") not in _CALL_RELATIONS:
            continue
        src = data.get("_src", u)
        tgt = data.get("_tgt", v)
        out_deg[src] += 1
        in_deg[tgt] += 1
    return {n for n in g.nodes if out_deg.get(n) and not in_deg.get(n)}


def _is_test_path(path: str) -> bool:
    """Heuristic test-file detector over the extraction's source paths."""
    if not path:
        return False
    parts = PurePosixPath(path.replace("\\", "/")).parts
    if any(part in _TEST_DIR_NAMES for part in parts[:-1]):
        return True
    stem = parts[-1].split(".")[0].lower() if parts else ""
    return (
        stem.startswith(("test_", "test-"))
        or stem.endswith(("_test", "-test", ".test", ".spec"))
        or stem == "conftest"
    )


# ----- roll-up inputs --------------------------------------------------------


def _rationales(g: nx.Graph) -> dict[str, str]:
    """`{symbol_id: docstring}` from `rationale_for` edges.

    A symbol can carry several rationale nodes (docstring + `# NOTE:`
    comments); the earliest line wins so the docstring — always first in
    the body — is the one a card quotes.
    """
    best: dict[str, tuple[int, str, str]] = {}
    for u, v, data in g.edges(data=True):
        if data.get("relation") != _RATIONALE_RELATION:
            continue
        src = data.get("_src", u)
        tgt = data.get("_tgt", v)
        node = dict(g.nodes.get(src) or {})
        if node.get("file_type") != _RATIONALE_FILE_TYPE:
            src, tgt = tgt, src
            node = dict(g.nodes.get(src) or {})
        if node.get("file_type") != _RATIONALE_FILE_TYPE:
            continue
        label = str(node.get("label") or "").strip()
        if not label:
            continue
        candidate = (_line_of(node.get("source_location")), src, label)
        if tgt not in best or candidate[:2] < best[tgt][:2]:
            best[tgt] = candidate
    return {tgt: label for tgt, (_line, _src, label) in best.items()}


def _line_of(location: Any) -> int:
    """Parse `L148` / `L148-L160` to its start line; unknown sorts last."""
    if not isinstance(location, str):
        return 1 << 30
    head = location.strip().lstrip("L").split("-", 1)[0].lstrip("L")
    try:
        return int(head)
    except ValueError:
        return 1 << 30


def _load_feature_ownership(features_dir: Path) -> dict[str, str]:
    """`{symbol_id: feature_id}` from the on-disk taxonomy, `{}` when absent.

    `features/INDEX.json` names the features; each `feature.json` carries
    the member ids. Features claim members in sorted-id order so a symbol
    two features list resolves the same way every run. Tolerant by
    design: no taxonomy (a fresh ingest reaches the graph step before
    scaffolding) simply means unowned cards until the next refresh.
    """
    index_path = features_dir / "INDEX.json"
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    entries = payload.get("features")
    if not isinstance(entries, list):
        return {}

    feature_ids = sorted(
        str(entry.get("feature_id"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("feature_id")
    )
    owners: dict[str, str] = {}
    for feature_id in feature_ids:
        for member in _feature_members(features_dir / feature_id / "feature.json"):
            owners.setdefault(member, feature_id)
    return owners


def _feature_members(feature_json: Path) -> tuple[str, ...]:
    try:
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    members = payload.get("members")
    if not isinstance(members, list):
        return ()
    return tuple(m for m in members if isinstance(m, str))


# ----- plumbing --------------------------------------------------------------


def _indexed_root(features_dir: Path) -> Path:
    """The ingest root recorded in `meta.json`, or the context dir's parent."""
    context_dir = features_dir.parent
    fallback = context_dir.parent
    try:
        payload = json.loads((context_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return fallback
    recorded = payload.get("root") if isinstance(payload, dict) else None
    return Path(recorded) if isinstance(recorded, str) and recorded else fallback


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(payload, indent=2) + "\n")
