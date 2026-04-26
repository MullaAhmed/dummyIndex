"""Tests for feature naming + features.yaml override pipeline (Feature 3)."""
import json
from pathlib import Path

import networkx as nx
import pytest

from dummyindex.analysis.feature_naming import (
    CACHE_FILENAME,
    OVERRIDES_FILENAME,
    apply_feature_named_results,
    apply_feature_overrides,
    feature_cache_key,
    load_cached_names,
    load_features_yaml,
    prepare_feature_naming_todo,
    write_cached_names,
    write_features_yaml_starter,
)


def _make_graph():
    G = nx.DiGraph()
    for nid, lbl, sf in [
        ("login", "login()", "auth.py"),
        ("logout", "logout()", "auth.py"),
        ("logger", ".info()", "util.py"),
        ("billing_charge", "charge()", "billing.py"),
    ]:
        G.add_node(nid, label=lbl, source_file=sf, file_type="code")
    G.add_edge("login", "logger", relation="calls", confidence="EXTRACTED",
               source_file="auth.py", source_location="L1")
    return G


def _make_feature(fid="feature:auth_abc", label="Auth", nodes=None, **extra):
    return {
        "id": fid,
        "label": label,
        "kind": "feature",
        "nodes": list(nodes) if nodes else ["login", "logout"],
        "communities": [0],
        "flows": [],
        "members": [{"node_id": n, "role": "core", "weight": 1.0}
                    for n in (nodes or ["login", "logout"])],
        "roles": {"core": 2, "entry": 0, "terminal": 0,
                  "shared": 0, "rationale": 0, "data": 0},
        "evidence": {"community_ids": [0], "representative_nodes": [],
                     "doc_node_ids": [], "flow_ids": [],
                     "override_applied": False, "llm_reasoning": ""},
        "confidence": "INFERRED",
        "description": "",
        **extra,
    }


# --------------------------------------------------------------------------- #
# Cache.
# --------------------------------------------------------------------------- #


def test_load_cached_names_empty(tmp_path):
    assert load_cached_names(tmp_path) == {}


def test_cache_round_trip(tmp_path):
    entries = {"feature:x": {"name": "X", "description": "", "cache_key": "k"}}
    write_cached_names(tmp_path, entries)
    assert load_cached_names(tmp_path) == entries


def test_cache_key_stable():
    G = _make_graph()
    f = _make_feature()
    assert feature_cache_key(f, G) == feature_cache_key(f, G)


# --------------------------------------------------------------------------- #
# prepare + apply.
# --------------------------------------------------------------------------- #


def test_prepare_naming_todo_writes_file(tmp_path):
    G = _make_graph()
    f = _make_feature()
    todo = prepare_feature_naming_todo([f], G, tmp_path,
                                       god_nodes=[{"id": "logger", "label": ".info()"}],
                                       community_labels={0: "Auth"})
    assert todo["stats"]["to_name"] == 1
    assert (tmp_path / ".dummyindex_feature_names_todo.json").exists()
    assert todo["context"]["community_labels"] == {0: "Auth"}


def test_apply_persists_fresh_results_to_cache(tmp_path):
    G = _make_graph()
    f = _make_feature()
    fresh = [{"feature_id": f["id"], "name": "Auth Surface", "description": "Login + logout."}]
    new = apply_feature_named_results([f], G, tmp_path, fresh_results=fresh)
    assert new[0]["label"] == "Auth Surface"
    cached = load_cached_names(tmp_path)
    assert f["id"] in cached
    assert cached[f["id"]]["name"] == "Auth Surface"


def test_apply_falls_back_to_cache(tmp_path):
    G = _make_graph()
    f = _make_feature()
    apply_feature_named_results([f], G, tmp_path,
                                fresh_results=[{"feature_id": f["id"], "name": "Auth Surface"}])
    new = apply_feature_named_results([f], G, tmp_path, fresh_results=[])
    assert new[0]["label"] == "Auth Surface"


def test_apply_invalid_name_keeps_provisional(tmp_path):
    G = _make_graph()
    f = _make_feature()
    new = apply_feature_named_results([f], G, tmp_path,
                                       fresh_results=[{"feature_id": f["id"], "name": "X"}])
    assert new[0]["label"] == f["label"]  # original "Auth" kept; bad name rejected


# --------------------------------------------------------------------------- #
# features.yaml overrides.
# --------------------------------------------------------------------------- #


def test_features_yaml_starter_writes_when_missing(tmp_path):
    pytest.importorskip("yaml")
    G = _make_graph()
    f = _make_feature()
    path = write_features_yaml_starter([f], tmp_path)
    assert path is not None and path.exists()
    text = path.read_text(encoding="utf-8")
    assert "features:" in text
    assert f["id"] in text


def test_features_yaml_starter_skips_when_exists(tmp_path):
    pytest.importorskip("yaml")
    (tmp_path / OVERRIDES_FILENAME).write_text("features: []\n")
    assert write_features_yaml_starter([], tmp_path) is None


def test_pin_adds_node_to_feature(tmp_path):
    pytest.importorskip("yaml")
    G = _make_graph()
    f = _make_feature()
    (tmp_path / OVERRIDES_FILENAME).write_text(
        f"features:\n  - id: {f['id']}\n    pin: [logger]\n"
    )
    new, diff = apply_feature_overrides([f], G, tmp_path)
    assert "logger" in new[0]["nodes"]
    assert any("pinned" in line for line in diff)


def test_exclude_removes_node_from_feature(tmp_path):
    pytest.importorskip("yaml")
    G = _make_graph()
    f = _make_feature()
    (tmp_path / OVERRIDES_FILENAME).write_text(
        f"features:\n  - id: {f['id']}\n    exclude: [logout]\n"
    )
    new, _ = apply_feature_overrides([f], G, tmp_path)
    assert "logout" not in new[0]["nodes"]


def test_features_new_creates_user_feature(tmp_path):
    pytest.importorskip("yaml")
    G = _make_graph()
    (tmp_path / OVERRIDES_FILENAME).write_text(
        "features_new:\n"
        "  - id: feature:infra\n"
        "    name: Infrastructure\n"
        "    nodes: [logger]\n"
    )
    new, diff = apply_feature_overrides([], G, tmp_path)
    assert any(f["id"] == "feature:infra" for f in new)
    assert next(f for f in new if f["id"] == "feature:infra")["confidence"] == "EXTRACTED"


def test_merge_with_combines_two_features(tmp_path):
    pytest.importorskip("yaml")
    G = _make_graph()
    f_a = _make_feature("feature:a", "A", nodes=["login"])
    f_b = _make_feature("feature:b", "B", nodes=["logout"])
    (tmp_path / OVERRIDES_FILENAME).write_text(
        "features:\n"
        "  - id: feature:a\n"
        "    merge_with: [feature:b]\n"
    )
    new, diff = apply_feature_overrides([f_a, f_b], G, tmp_path)
    assert len(new) == 1
    assert set(new[0]["nodes"]) == {"login", "logout"}


def test_load_features_yaml_raises_on_invalid(tmp_path):
    pytest.importorskip("yaml")
    (tmp_path / OVERRIDES_FILENAME).write_text("features: [: bad")
    with pytest.raises(ValueError):
        load_features_yaml(tmp_path)


def test_unknown_pin_node_warns_not_errors(tmp_path):
    pytest.importorskip("yaml")
    G = _make_graph()
    f = _make_feature()
    (tmp_path / OVERRIDES_FILENAME).write_text(
        f"features:\n  - id: {f['id']}\n    pin: [does_not_exist]\n"
    )
    new, diff = apply_feature_overrides([f], G, tmp_path)
    assert "does_not_exist" not in new[0]["nodes"]
    assert any("WARNING" in line and "pin" in line for line in diff)
