"""Tests for the flow-naming cache + override + apply pipeline (Feature 2)."""
import json
from pathlib import Path

import networkx as nx
import pytest

from dummyindex.analysis.flow_naming import (
    CACHE_FILENAME,
    OVERRIDES_FILENAME,
    RESULTS_FILENAME,
    TODO_FILENAME,
    apply_named_results,
    cache_key_for_flow,
    load_cached_names,
    load_overrides,
    prepare_naming_todo,
    write_cached_names,
    write_naming_results,
)


def _make_graph():
    G = nx.DiGraph()
    G.add_node("login", label="login()", source_file="app.py", docstring="Authenticate the user.")
    G.add_node("validate", label="validate()", source_file="auth.py")
    G.add_node("logger", label=".info()", source_file="util.py")
    G.add_edge("login", "validate", relation="calls", confidence="EXTRACTED",
               source_file="app.py", source_location="L1")
    G.add_edge("validate", "logger", relation="calls", confidence="EXTRACTED",
               source_file="auth.py", source_location="L1")
    return G


def _make_flow(flow_id="flow:abc123"):
    return {
        "id": flow_id,
        "label": flow_id,
        "kind": "flow",
        "entry_kind": "http_route",
        "entry_nodes": ["login"],
        "exit_nodes": ["logger"],
        "nodes": ["login", "validate", "logger"],
        "sequence": [
            {"source": "login", "target": "validate", "relation": "calls",
             "confidence": "EXTRACTED", "source_location": "L1"},
            {"source": "validate", "target": "logger", "relation": "calls",
             "confidence": "EXTRACTED", "source_location": "L1"},
        ],
        "alt_paths": [],
        "depth": 2,
        "salience": 1.5,
        "confidence": "EXTRACTED",
    }


# --------------------------------------------------------------------------- #
# Cache I/O.
# --------------------------------------------------------------------------- #


def test_load_cached_names_returns_empty_when_missing(tmp_path):
    assert load_cached_names(tmp_path) == {}


def test_cache_round_trips(tmp_path):
    entries = {"flow:1": {"name": "Login Flow", "description": "auth", "cache_key": "k1"}}
    write_cached_names(tmp_path, entries)
    assert load_cached_names(tmp_path) == entries


def test_cache_with_wrong_schema_is_ignored(tmp_path):
    (tmp_path / CACHE_FILENAME).write_text(
        json.dumps({"schema_version": "0.0", "entries": {"flow:1": {"name": "x"}}})
    )
    assert load_cached_names(tmp_path) == {}


# --------------------------------------------------------------------------- #
# Cache key stability (PRD SC-5).
# --------------------------------------------------------------------------- #


def test_cache_key_is_stable():
    G = _make_graph()
    flow = _make_flow()
    assert cache_key_for_flow(flow, G) == cache_key_for_flow(flow, G)


def test_cache_key_changes_when_entry_changes():
    G = _make_graph()
    flow_a = _make_flow()
    flow_b = dict(flow_a, entry_nodes=["validate"])
    assert cache_key_for_flow(flow_a, G) != cache_key_for_flow(flow_b, G)


# --------------------------------------------------------------------------- #
# Overrides.
# --------------------------------------------------------------------------- #


def test_load_overrides_yaml(tmp_path):
    pytest.importorskip("yaml")
    (tmp_path / OVERRIDES_FILENAME).write_text(
        "flow:abc123:\n  name: Custom Login\n  description: Hand-written name\n"
    )
    overrides = load_overrides(tmp_path)
    assert overrides["flow:abc123"]["name"] == "Custom Login"
    assert overrides["flow:abc123"]["description"] == "Hand-written name"


def test_load_overrides_accepts_string_shorthand(tmp_path):
    pytest.importorskip("yaml")
    (tmp_path / OVERRIDES_FILENAME).write_text("flow:1: Quick Name\n")
    overrides = load_overrides(tmp_path)
    assert overrides["flow:1"]["name"] == "Quick Name"


# --------------------------------------------------------------------------- #
# prepare_naming_todo + apply_named_results.
# --------------------------------------------------------------------------- #


def test_prepare_writes_todo_with_context(tmp_path):
    G = _make_graph()
    flows = [_make_flow()]
    todo = prepare_naming_todo(
        flows, G, tmp_path,
        god_nodes=[{"id": "validate", "label": "validate()"}],
        community_labels={0: "auth", 1: "io"},
    )
    assert todo["stats"]["to_name"] == 1
    assert "validate()" in todo["context"]["god_nodes"]
    assert (tmp_path / TODO_FILENAME).exists()


def test_apply_uses_fresh_results_and_caches(tmp_path):
    G = _make_graph()
    flow = _make_flow()
    flows = [flow]
    fresh = [{"flow_id": flow["id"], "name": "Login Flow",
              "description": "Auth + log."}]
    new_flows = apply_named_results(flows, G, tmp_path, fresh_results=fresh)
    assert new_flows[0]["label"] == "Login Flow"
    assert new_flows[0]["description"] == "Auth + log."
    cached = load_cached_names(tmp_path)
    assert flow["id"] in cached
    assert cached[flow["id"]]["name"] == "Login Flow"


def test_apply_falls_back_to_cache_on_repeat_run(tmp_path):
    G = _make_graph()
    flow = _make_flow()
    fresh = [{"flow_id": flow["id"], "name": "Login Flow"}]
    apply_named_results([flow], G, tmp_path, fresh_results=fresh)
    # second call with no fresh results — cache should still produce the name
    new_flows = apply_named_results([flow], G, tmp_path, fresh_results=[])
    assert new_flows[0]["label"] == "Login Flow"


def test_apply_invalid_name_keeps_provisional_id(tmp_path):
    G = _make_graph()
    flow = _make_flow()
    fresh = [{"flow_id": flow["id"], "name": "BadOneWord"}]
    new_flows = apply_named_results([flow], G, tmp_path, fresh_results=fresh)
    assert new_flows[0]["label"] == flow["id"]
    assert flow["id"] not in load_cached_names(tmp_path)


def test_overrides_win_over_cache_and_fresh(tmp_path):
    pytest.importorskip("yaml")
    G = _make_graph()
    flow = _make_flow()
    (tmp_path / OVERRIDES_FILENAME).write_text(
        f"{flow['id']}:\n  name: Manual Name\n"
    )
    fresh = [{"flow_id": flow["id"], "name": "Generated Name"}]
    new_flows = apply_named_results([flow], G, tmp_path, fresh_results=fresh)
    assert new_flows[0]["label"] == "Manual Name"


def test_results_file_round_trip(tmp_path):
    write_naming_results(tmp_path, [{"flow_id": "flow:1", "name": "Two Words"}])
    assert (tmp_path / RESULTS_FILENAME).exists()
