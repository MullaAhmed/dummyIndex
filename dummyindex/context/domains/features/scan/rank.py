"""The ranked shortlist the scan seed consumes (`features/seed-rank.json`).

Personalized PageRank over `features/symbol-graph.json`, computed by the
deterministic builder in `context/build/communities.py` and written next
to the graph it ranks. `seed_scan` stays pure, so — like `refs.py` — the
file I/O lives here: `load_seed_rank` reads the artifact back and hands
the seed one frozen `SeedRank`.

Degradation is deliberate: a missing or unreadable artifact loads as
``None`` and the seed falls back to its per-feature file-count ordering,
which is what keeps repos without a symbol graph working exactly as
before.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RANK_SCHEMA_VERSION = 1

# Written beside `symbol-graph.json`. Committed and diffed, so the entry
# order (highest score first, id breaking ties) is part of the contract.
SEED_RANK_FILENAME = "seed-rank.json"


@dataclass(frozen=True)
class RankEntry:
    """One ranked symbol: a `symbol-graph.json` node id and its PageRank."""

    id: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "score": self.score}


@dataclass(frozen=True)
class SeedRank:
    """The ranked shortlist, highest score first."""

    entries: tuple[RankEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RANK_SCHEMA_VERSION,
            "ranked": [e.to_dict() for e in self.entries],
        }

    def scores(self) -> dict[str, float]:
        """`{node_id: score}` for O(1) lookups in the seed's sort keys."""
        return {e.id: e.score for e in self.entries}


def load_seed_rank(features_dir: Path) -> SeedRank | None:
    """Read `<features_dir>/seed-rank.json`, or ``None`` when unusable.

    Same contract as `refs.load_symbol_ref_index`: a missing, unreadable,
    or malformed artifact means "no rank signal", never a failed seed.
    Malformed rows are skipped rather than failing the whole shortlist.
    """
    path = features_dir / SEED_RANK_FILENAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    ranked = payload.get("ranked")
    if not isinstance(ranked, list):
        return None
    entries: list[RankEntry] = []
    for row in ranked:
        if not isinstance(row, dict):
            continue
        node_id = row.get("id")
        score = row.get("score")
        if not isinstance(node_id, str) or not node_id:
            continue
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            continue
        entries.append(RankEntry(id=node_id, score=float(score)))
    return SeedRank(entries=tuple(entries))
