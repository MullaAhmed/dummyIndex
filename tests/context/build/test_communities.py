"""Deterministic graph artifacts — PageRank shortlist + community roll-up.

`build_graph` derives `features/seed-rank.json` and
`features/graph-communities.json` from the same in-memory graph it just
exported. Both are committed EXTRACTED backbone, so what's under test is
the personalization policy (test files down-weighted, entry points
boosted), the rationale/member filtering, and byte-stability across runs.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import networkx as nx
import pytest

from dummyindex.context.build.communities import (
    build_seed_rank,
    compute_symbol_rank,
    write_graph_artifacts,
)
from dummyindex.context.build.graph import build_graph

_EXTRACTION = {
    "nodes": [
        {
            "id": "auth_login",
            "label": "login()",
            "file_type": "code",
            "source_file": "/repo/app/auth.py",
            "source_location": "L1",
        },
        {
            "id": "auth_verify",
            "label": "verify()",
            "file_type": "code",
            "source_file": "/repo/app/auth.py",
            "source_location": "L20",
        },
        {
            "id": "auth_rationale_2",
            "label": "Check the password before charging.",
            "file_type": "rationale",
            "source_file": "/repo/app/auth.py",
            "source_location": "L2",
        },
        {
            "id": "billing_charge",
            "label": "charge()",
            "file_type": "code",
            "source_file": "/repo/app/billing.py",
            "source_location": "L1",
        },
    ],
    "edges": [
        {"source": "auth_login", "target": "auth_verify", "relation": "calls"},
        {"source": "auth_login", "target": "billing_charge", "relation": "calls"},
        {
            "source": "auth_rationale_2",
            "target": "auth_login",
            "relation": "rationale_for",
        },
    ],
}


def _symmetric_graph_with_test_twin() -> nx.Graph:
    """`main` and `test_main` sit in identical structure; only the path differs."""
    g = nx.Graph()
    g.add_node("app_main", file_type="code", source_file="/repo/app/main.py")
    g.add_node("app_helper", file_type="code", source_file="/repo/app/helper.py")
    g.add_node(
        "tests_test_main",
        file_type="code",
        source_file="/repo/tests/test_main.py",
    )
    g.add_edge(
        "app_main", "app_helper", relation="calls", _src="app_main", _tgt="app_helper"
    )
    g.add_edge(
        "tests_test_main",
        "app_helper",
        relation="calls",
        _src="tests_test_main",
        _tgt="app_helper",
    )
    return g


# ----- pagerank --------------------------------------------------------------


@pytest.mark.unit
def test_pagerank_of_an_empty_graph_is_empty() -> None:
    assert compute_symbol_rank(nx.Graph()) == {}


@pytest.mark.unit
def test_pagerank_downweights_test_files() -> None:
    """Same structure, different path: the test twin must rank below source."""
    scores = compute_symbol_rank(_symmetric_graph_with_test_twin())
    assert scores["app_main"] > scores["tests_test_main"]


@pytest.mark.unit
def test_pagerank_handles_a_graph_with_no_edges() -> None:
    g = nx.Graph()
    g.add_node("a", file_type="code", source_file="/repo/a.py")
    g.add_node("b", file_type="code", source_file="/repo/b.py")
    scores = compute_symbol_rank(g)
    assert set(scores) == {"a", "b"}


# ----- shortlist -------------------------------------------------------------


@pytest.mark.unit
def test_seed_rank_excludes_rationale_nodes_and_breaks_ties_on_id() -> None:
    scores = {"b": 0.2, "docstring": 0.9, "a": 0.2}
    node_by_id = {
        "a": {"file_type": "code"},
        "b": {"file_type": "code"},
        "docstring": {"file_type": "rationale"},
    }
    rank = build_seed_rank(scores, node_by_id)
    assert [e.id for e in rank.entries] == ["a", "b"]


@pytest.mark.unit
def test_seed_rank_sorts_by_score_and_truncates() -> None:
    scores = {"low": 0.1, "high": 0.9, "mid": 0.5}
    node_by_id = {n: {"file_type": "code"} for n in scores}
    rank = build_seed_rank(scores, node_by_id, top_n=2)
    assert [e.id for e in rank.entries] == ["high", "mid"]


# ----- the artifacts on disk -------------------------------------------------


def _built(tmp_path: Path) -> Path:
    features_dir = tmp_path / ".context" / "features"
    build_graph(copy.deepcopy(_EXTRACTION), features_dir)
    return features_dir


@pytest.mark.integration
def test_build_graph_writes_both_artifacts(tmp_path: Path) -> None:
    features_dir = tmp_path / ".context" / "features"
    result = build_graph(copy.deepcopy(_EXTRACTION), features_dir)
    assert (features_dir / "seed-rank.json").is_file()
    assert (features_dir / "graph-communities.json").is_file()
    assert result.artifacts == (
        "features/seed-rank.json",
        "features/graph-communities.json",
    )


@pytest.mark.integration
def test_seed_rank_artifact_ranks_symbols_without_rationale_noise(
    tmp_path: Path,
) -> None:
    payload = json.loads(
        (_built(tmp_path) / "seed-rank.json").read_text(encoding="utf-8")
    )
    ids = [row["id"] for row in payload["ranked"]]
    assert "auth_rationale_2" not in ids
    assert set(ids) == {"auth_login", "auth_verify", "billing_charge"}
    scores = [row["score"] for row in payload["ranked"]]
    assert scores == sorted(scores, reverse=True)
    assert ids[0] == "auth_login", "the entry-point hub outranks its callees"


@pytest.mark.integration
def test_graph_communities_cards_cite_members_and_summary(tmp_path: Path) -> None:
    payload = json.loads(
        (_built(tmp_path) / "graph-communities.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == 1
    cards = payload["communities"]
    assert cards, "the sample graph must roll up to at least one card"
    by_member = {m["id"]: card for card in cards for m in card["members"]}
    login_card = by_member["auth_login"]
    # Slug from the top member's name — never the raw partition integer.
    assert "login" in login_card["slug"]
    assert login_card["summary"] == "Check the password before charging."
    login = next(m for m in login_card["members"] if m["id"] == "auth_login")
    assert login["path"].endswith("app/auth.py:1")
    # Rationale nodes never count as members.
    assert "auth_rationale_2" not in {
        m["id"] for card in cards for m in card["members"]
    }


@pytest.mark.integration
def test_graph_communities_take_ownership_from_the_taxonomy(tmp_path: Path) -> None:
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "auth"}]}), encoding="utf-8"
    )
    (features_dir / "auth").mkdir()
    (features_dir / "auth" / "feature.json").write_text(
        json.dumps(
            {
                "feature_id": "auth",
                "members": ["auth_login", "auth_verify", "billing_charge"],
            }
        ),
        encoding="utf-8",
    )
    build_graph(copy.deepcopy(_EXTRACTION), features_dir)
    payload = json.loads(
        (features_dir / "graph-communities.json").read_text(encoding="utf-8")
    )
    for card in payload["communities"]:
        assert card["feature"] == "auth"
        assert card["slug"].startswith("auth-")


@pytest.mark.integration
def test_artifacts_are_byte_stable_across_runs(tmp_path: Path) -> None:
    first = _built(tmp_path / "one")
    second = _built(tmp_path / "two")
    for name in ("seed-rank.json", "graph-communities.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


@pytest.mark.integration
def test_write_graph_artifacts_handles_an_empty_graph(tmp_path: Path) -> None:
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    written = write_graph_artifacts(nx.Graph(), {}, features_dir)
    assert written == (
        "features/seed-rank.json",
        "features/graph-communities.json",
    )
    rank = json.loads((features_dir / "seed-rank.json").read_text(encoding="utf-8"))
    cards = json.loads(
        (features_dir / "graph-communities.json").read_text(encoding="utf-8")
    )
    assert rank["ranked"] == []
    assert cards["communities"] == []
