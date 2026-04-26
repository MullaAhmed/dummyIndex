"""Unit tests for the flow hypergraph synthesizer (Feature 2)."""
import networkx as nx
import pytest

from dummyindex.analysis.flows import (
    FlowConfig,
    derive_flow,
    detect_entry_points,
    merge_flows,
    overlap_index,
    synthesize_flows,
)


# --------------------------------------------------------------------------- #
# Fixtures.
# --------------------------------------------------------------------------- #


def _add_node(G, nid, label, source_file="app.py", **extra):
    G.add_node(nid, label=label, source_file=source_file, **extra)


def _add_call(G, src, tgt, loc="L1", confidence="EXTRACTED"):
    G.add_edge(src, tgt, relation="calls", confidence=confidence,
               source_file="app.py", source_location=loc)


@pytest.fixture
def two_route_graph():
    """Two HTTP routes sharing a validator and a logger I/O terminal."""
    G = nx.DiGraph()
    _add_node(G, "login", "login()", annotations=["@app.route('/login')"])
    _add_node(G, "register", "register()", annotations=["@app.route('/register')"])
    _add_node(G, "validate", "validate()")
    _add_node(G, "hash", "hash()")
    _add_node(G, "save_db", "save()")
    _add_node(G, "logger", ".info()")
    _add_call(G, "login", "validate", "L10")
    _add_call(G, "login", "hash", "L11")
    _add_call(G, "register", "validate", "L20")
    _add_call(G, "register", "save_db", "L21")
    _add_call(G, "validate", "logger", "L30")
    _add_call(G, "save_db", "logger", "L40")
    return G


@pytest.fixture
def cli_graph():
    G = nx.DiGraph()
    _add_node(G, "main", "main()", source_file="pkg/__main__.py")
    _add_node(G, "run_a", "run_a()")
    _add_node(G, "run_b", "run_b()")
    _add_call(G, "main", "run_a", "L5")
    _add_call(G, "main", "run_b", "L6")
    return G


@pytest.fixture
def recursive_graph():
    G = nx.DiGraph()
    _add_node(G, "main", "main()", source_file="pkg/__main__.py")
    _add_node(G, "rec", "rec()")
    _add_call(G, "main", "rec", "L1")
    _add_call(G, "rec", "rec", "L2")
    return G


# --------------------------------------------------------------------------- #
# Entry-point detection.
# --------------------------------------------------------------------------- #


def test_detects_http_routes(two_route_graph):
    entries = detect_entry_points(two_route_graph)
    by_id = {e.node_id: e for e in entries}
    assert by_id["login"].entry_kind == "http_route"
    assert by_id["register"].entry_kind == "http_route"
    assert "validate" not in by_id  # not an entry point


def test_detects_cli_command_via_main_module(cli_graph):
    entries = detect_entry_points(cli_graph)
    kinds = {e.node_id: e.entry_kind for e in entries}
    assert kinds["main"] == "cli_command"


def test_internal_entry_fallback():
    G = nx.DiGraph()
    _add_node(G, "orphan", "orphan()")
    _add_node(G, "child", "child()")
    _add_call(G, "orphan", "child", "L1")
    entries = detect_entry_points(G)
    assert any(e.node_id == "orphan" and e.entry_kind == "internal" for e in entries)


def test_test_function_detection():
    G = nx.DiGraph()
    _add_node(G, "test_foo", "test_foo()", source_file="tests/test_app.py")
    _add_node(G, "helper", "helper()")
    _add_call(G, "test_foo", "helper", "L1")
    entries = detect_entry_points(G)
    assert any(e.node_id == "test_foo" and e.entry_kind == "test" for e in entries)


# --------------------------------------------------------------------------- #
# Derivation.
# --------------------------------------------------------------------------- #


def test_flow_includes_io_terminator_node(two_route_graph):
    flows = synthesize_flows(two_route_graph)
    login_flow = next(f for f in flows if "login" in f["entry_nodes"])
    assert "logger" in login_flow["nodes"]
    assert "logger" in login_flow["exit_nodes"]


def test_shared_node_appears_in_multiple_flows(two_route_graph):
    flows = synthesize_flows(two_route_graph)
    index = overlap_index(flows)
    assert len(index["validate"]) == 2
    assert len(index["logger"]) == 2


def test_recursion_terminates_at_cycle_break(recursive_graph):
    flows = synthesize_flows(recursive_graph)
    assert len(flows) >= 1
    flow = flows[0]
    # cycle break is recorded as an alt-path entry pointing at rec
    assert any(ap.get("reason") == "cycle" for ap in flow["alt_paths"])


def test_max_depth_clamps_traversal():
    G = nx.DiGraph()
    _add_node(G, "main", "main()", source_file="pkg/__main__.py")
    for i in range(20):
        _add_node(G, f"f{i}", f"f{i}()")
    _add_call(G, "main", "f0", "L1")
    for i in range(19):
        _add_call(G, f"f{i}", f"f{i+1}", f"L{i+1}")
    flows = synthesize_flows(G, FlowConfig(max_depth=3))
    flow = flows[0]
    # depth 3: main(0) -> f0(1) -> f1(2) -> f2(3 = depth bound, terminate)
    assert flow["depth"] <= 3
    assert "f2" in flow["nodes"]
    assert "f10" not in flow["nodes"]


# --------------------------------------------------------------------------- #
# Determinism (PRD SC-4).
# --------------------------------------------------------------------------- #


def test_flow_ids_are_deterministic(two_route_graph):
    a = [f["id"] for f in synthesize_flows(two_route_graph)]
    b = [f["id"] for f in synthesize_flows(two_route_graph)]
    assert a == b


def test_flow_sequence_is_source_order(two_route_graph):
    flows = synthesize_flows(two_route_graph)
    login_flow = next(f for f in flows if "login" in f["entry_nodes"])
    targets = [s["target"] for s in login_flow["sequence"]]
    # validate (L10) before hash (L11) — source order DFS
    assert targets.index("validate") < targets.index("hash")


# --------------------------------------------------------------------------- #
# Merge rules.
# --------------------------------------------------------------------------- #


def test_full_equivalence_merge():
    a = {
        "id": "flow:a", "label": "flow:a", "kind": "flow",
        "entry_kind": "http_route", "entry_nodes": ["e1"],
        "exit_nodes": ["x"], "nodes": ["e1", "x"],
        "sequence": [{"source": "e1", "target": "x"}],
        "alt_paths": [], "depth": 1, "salience": 1.0, "confidence": "EXTRACTED",
    }
    b = dict(a, id="flow:b", entry_nodes=["e2"])
    merged = merge_flows([a, b])
    assert len(merged) == 1
    assert set(merged[0]["entry_nodes"]) == {"e1", "e2"}


def test_high_overlap_merge_keeps_higher_salience():
    a = {"id": "a", "label": "a", "kind": "flow", "entry_kind": "http_route",
         "entry_nodes": ["e1"], "exit_nodes": [], "nodes": ["e1", "n1", "n2", "n3", "n4"],
         "sequence": [], "alt_paths": [], "depth": 1, "salience": 5.0, "confidence": "EXTRACTED"}
    b = {"id": "b", "label": "b", "kind": "flow", "entry_kind": "http_route",
         "entry_nodes": ["e2"], "exit_nodes": [], "nodes": ["e2", "n1", "n2", "n3", "n4"],
         "sequence": [], "alt_paths": [], "depth": 1, "salience": 1.0, "confidence": "EXTRACTED"}
    merged = merge_flows([a, b], threshold=0.5)
    assert len(merged) == 1
    assert merged[0]["id"] == "a"
    assert "e2" in merged[0]["entry_nodes"]


# --------------------------------------------------------------------------- #
# Salience + ranking.
# --------------------------------------------------------------------------- #


def test_salience_ordering(two_route_graph):
    flows = synthesize_flows(two_route_graph)
    sals = [f["salience"] for f in flows]
    assert sals == sorted(sals, reverse=True)


def test_flow_limit_is_respected():
    G = nx.DiGraph()
    for i in range(20):
        nid = f"r{i}"
        _add_node(G, nid, f"r{i}()", annotations=[f"@app.route('/r{i}')"])
        _add_node(G, f"c{i}", f"c{i}()")
        _add_call(G, nid, f"c{i}", f"L{i}")
    flows = synthesize_flows(G, FlowConfig(flow_limit=5))
    assert len(flows) == 5


# --------------------------------------------------------------------------- #
# Confidence aggregation.
# --------------------------------------------------------------------------- #


def test_inferred_edge_downgrades_confidence():
    G = nx.DiGraph()
    _add_node(G, "main", "main()", source_file="pkg/__main__.py")
    _add_node(G, "child", "child()")
    _add_call(G, "main", "child", confidence="INFERRED")
    flows = synthesize_flows(G)
    assert flows[0]["confidence"] == "INFERRED"


def test_ambiguous_edge_dominates_confidence():
    G = nx.DiGraph()
    _add_node(G, "main", "main()", source_file="pkg/__main__.py")
    _add_node(G, "a", "a()")
    _add_node(G, "b", "b()")
    _add_call(G, "main", "a", confidence="EXTRACTED")
    _add_call(G, "a", "b", confidence="AMBIGUOUS")
    flows = synthesize_flows(G)
    assert flows[0]["confidence"] == "AMBIGUOUS"
