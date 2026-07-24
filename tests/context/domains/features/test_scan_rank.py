"""`scan/rank.py` — the seed's ranked shortlist and its tolerant loader.

Degradation is the contract (same as `refs.py`): a missing, unreadable,
or malformed `seed-rank.json` loads as ``None`` and the seed falls back
to its pre-rank ordering; malformed rows are skipped, never fatal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.features.scan import (
    RankEntry,
    SeedRank,
    load_seed_rank,
)


def _write(features_dir: Path, payload: object) -> None:
    features_dir.mkdir(parents=True, exist_ok=True)
    (features_dir / "seed-rank.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.unit
def test_missing_artifact_loads_as_none(tmp_path: Path) -> None:
    assert load_seed_rank(tmp_path) is None


@pytest.mark.unit
def test_loader_roundtrips_what_the_model_serializes(tmp_path: Path) -> None:
    rank = SeedRank(
        entries=(RankEntry(id="auth_login", score=0.5), RankEntry(id="b", score=0.25))
    )
    _write(tmp_path, rank.to_dict())
    loaded = load_seed_rank(tmp_path)
    assert loaded == rank
    assert loaded.scores() == {"auth_login": 0.5, "b": 0.25}


@pytest.mark.unit
def test_unreadable_json_loads_as_none(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "seed-rank.json").write_text("{ not json", encoding="utf-8")
    assert load_seed_rank(tmp_path) is None


@pytest.mark.unit
def test_wrong_shape_loads_as_none(tmp_path: Path) -> None:
    _write(tmp_path, {"ranked": "nope"})
    assert load_seed_rank(tmp_path) is None


@pytest.mark.unit
def test_malformed_rows_are_skipped_not_fatal(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "schema_version": 1,
            "ranked": [
                {"id": "good", "score": 0.5},
                {"id": "no-score"},
                {"score": 0.4},
                {"id": "bool-score", "score": True},
                "junk",
            ],
        },
    )
    loaded = load_seed_rank(tmp_path)
    assert loaded is not None
    assert [e.id for e in loaded.entries] == ["good"]


@pytest.mark.unit
def test_rank_is_frozen_data() -> None:
    rank = SeedRank(entries=(RankEntry(id="a", score=1.0),))
    with pytest.raises(AttributeError):
        rank.entries = ()  # type: ignore[misc]
