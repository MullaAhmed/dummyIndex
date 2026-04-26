"""Unit tests for the feature hypergraph synthesizer (Feature 3)."""
import networkx as nx
import pytest

from dummyindex.analysis.features import (
    FeatureConfig,
    canonical_hash,
    derive_feature_dependencies,
    detect_orphans,
    overlap_matrix,
    signal_pack,
    synthesize_features,
)


def _add_node(G, nid, label, source_file="x.py", file_type="code", **extra):
    G.add_node(nid, label=label, source_file=source_file, file_type=file_type, **extra)


def _add_edge(G, src, tgt, rel="calls", confidence="EXTRACTED"):
    G.add_edge(src, tgt, relation=rel, confidence=confidence,
               source_file="x.py", source_location="L1")


@pytest.fixture
def three_feature_graph():
    """Auth + Payments + Infra (shared utilities). Auth and Payments both
    use logger / db / cache → those should attach to all three features."""
    G = nx.DiGraph()
    for nid in ["login", "logout", "register"]:
        _add_node(G, nid, f"{nid}()", source_file="auth.py")
    for nid in ["charge", "refund", "subscribe"]:
        _add_node(G, nid, f"{nid}()", source_file="billing.py")
    for nid in ["logger", "db", "cache"]:
        _add_node(G, nid, f"{nid}()", source_file="util.py")
    for src in ["login", "logout", "register"]:
        for tgt in ["logger", "db", "cache"]:
            _add_edge(G, src, tgt)
    for src in ["charge", "refund", "subscribe"]:
        for tgt in ["logger", "db", "cache"]:
            _add_edge(G, src, tgt)
    _add_edge(G, "charge", "login", rel="imports")
    return G


@pytest.fixture
def three_feature_inputs(three_feature_graph):
    G = three_feature_graph
    communities = {
        0: ["login", "logout", "register"],
        1: ["charge", "refund", "subscribe"],
        2: ["logger", "db", "cache"],
    }
    flows = [
        {"id": "flow:auth", "kind": "flow",
         "nodes": ["login", "logger"], "entry_nodes": ["login"],
         "exit_nodes": ["logger"], "sequence": [{"source": "login", "target": "logger"}]},
        {"id": "flow:pay", "kind": "flow",
         "nodes": ["charge", "login", "logger", "db"], "entry_nodes": ["charge"],
         "exit_nodes": ["db"], "sequence": [
             {"source": "charge", "target": "login"},
             {"source": "login", "target": "logger"},
             {"source": "charge", "target": "db"},
         ]},
    ]
    gods = [{"id": "logger", "label": ".info()"}, {"id": "db", "label": ".query()"}]
    labels = {0: "Auth", 1: "Payments", 2: "Infra Utilities"}
    return G, communities, flows, gods, labels


# --------------------------------------------------------------------------- #
# Stage A.
# --------------------------------------------------------------------------- #


def test_one_feature_per_sized_community(three_feature_inputs):
    G, communities, flows, gods, labels = three_feature_inputs
    features = synthesize_features(G, communities, flows=flows,
                                    god_nodes_data=gods, community_labels=labels)
    assert len(features) == 3
    names = sorted(f["label"] for f in features)
    assert names == ["Auth", "Infra Utilities", "Payments"]


def test_min_feature_size_filters_small_communities():
    G = nx.DiGraph()
    _add_node(G, "a", "a()")
    _add_node(G, "b", "b()")
    _add_edge(G, "a", "b")
    features = synthesize_features(
        G, {0: ["a", "b"]},
        config=FeatureConfig(min_feature_size=3),
    )
    assert features == []


def test_god_node_attaches_via_in_edges(three_feature_inputs):
    """Logger has 6 incoming `calls` edges from auth + payments members.
    It should attach to Auth (3 callers), Payments (3 callers), and stay in
    Infra (its own community). Hypergraph property in action."""
    G, communities, flows, gods, labels = three_feature_inputs
    features = synthesize_features(G, communities, flows=flows,
                                    god_nodes_data=gods, community_labels=labels)
    by_label = {f["label"]: f for f in features}
    assert "logger" in by_label["Auth"]["nodes"]
    assert "logger" in by_label["Payments"]["nodes"]
    assert "logger" in by_label["Infra Utilities"]["nodes"]


def test_overlap_matrix_records_shared_nodes(three_feature_inputs):
    G, communities, flows, gods, labels = three_feature_inputs
    features = synthesize_features(G, communities, flows=flows,
                                    god_nodes_data=gods, community_labels=labels)
    idx = overlap_matrix(features)
    assert len(idx["logger"]) == 3
    assert len(idx["db"]) == 3


# --------------------------------------------------------------------------- #
# Roles + weights.
# --------------------------------------------------------------------------- #


def test_role_assignment_basic(three_feature_inputs):
    G, communities, flows, gods, labels = three_feature_inputs
    features = synthesize_features(G, communities, flows=flows,
                                    god_nodes_data=gods, community_labels=labels)
    by_label = {f["label"]: f for f in features}
    auth_roles = by_label["Auth"]["roles"]
    assert auth_roles["core"] >= 2
    assert auth_roles["shared"] >= 1


def test_weight_in_valid_range(three_feature_inputs):
    G, communities, flows, gods, labels = three_feature_inputs
    features = synthesize_features(G, communities, flows=flows,
                                    god_nodes_data=gods, community_labels=labels)
    for f in features:
        for m in f["members"]:
            assert 0.0 < m["weight"] <= 1.0


# --------------------------------------------------------------------------- #
# Determinism.
# --------------------------------------------------------------------------- #


def test_feature_ids_are_deterministic(three_feature_inputs):
    G, communities, flows, gods, labels = three_feature_inputs
    a = [f["id"] for f in synthesize_features(G, communities, flows=flows,
                                               god_nodes_data=gods, community_labels=labels)]
    b = [f["id"] for f in synthesize_features(G, communities, flows=flows,
                                               god_nodes_data=gods, community_labels=labels)]
    assert a == b


def test_canonical_hash_stable():
    f = {"nodes": ["b", "a", "c"]}
    assert canonical_hash(f) == canonical_hash({"nodes": ["a", "b", "c"]})


# --------------------------------------------------------------------------- #
# Dependency derivation.
# --------------------------------------------------------------------------- #


def test_payments_depends_on_auth_via_flow_and_import(three_feature_inputs):
    G, communities, flows, gods, labels = three_feature_inputs
    features = synthesize_features(G, communities, flows=flows,
                                    god_nodes_data=gods, community_labels=labels)
    deps = derive_feature_dependencies(G, features, flows=flows)
    pay = next(f["id"] for f in features if f["label"] == "Payments")
    auth = next(f["id"] for f in features if f["label"] == "Auth")
    edge = next((d for d in deps if d["source_feature_id"] == pay
                 and d["target_feature_id"] == auth), None)
    assert edge is not None, "expected Payments -> Auth dependency"
    assert "flow:pay" in edge["evidence"]["via_flows"]
    assert any("charge" in pair and "login" in pair for pair in edge["evidence"]["via_imports"])


def test_dep_threshold_prunes_low_weight():
    """Dependency below threshold gets dropped."""
    G = nx.DiGraph()
    for nid in ["a1", "a2", "a3", "b1", "b2", "b3"]:
        _add_node(G, nid, f"{nid}()")
    _add_edge(G, "a1", "b1", rel="imports")
    features = [
        {"id": "feature:a", "label": "A", "kind": "feature",
         "nodes": ["a1", "a2", "a3"], "communities": [0], "flows": [],
         "members": [{"node_id": n, "role": "core", "weight": 1.0} for n in ["a1","a2","a3"]],
         "roles": {}, "evidence": {}, "confidence": "INFERRED"},
        {"id": "feature:b", "label": "B", "kind": "feature",
         "nodes": ["b1", "b2", "b3"], "communities": [1], "flows": [],
         "members": [{"node_id": n, "role": "core", "weight": 1.0} for n in ["b1","b2","b3"]],
         "roles": {}, "evidence": {}, "confidence": "INFERRED"},
    ]
    deps = derive_feature_dependencies(G, features, flows=[],
                                       config=FeatureConfig(dep_threshold=10.0))
    assert deps == []


# --------------------------------------------------------------------------- #
# Orphans.
# --------------------------------------------------------------------------- #


def test_orphan_detection():
    G = nx.DiGraph()
    for nid in ["a", "b", "c", "orphan"]:
        _add_node(G, nid, f"{nid}()")
    features = [{"id": "feature:x", "nodes": ["a", "b", "c"]}]
    assert detect_orphans(G, features) == ["orphan"]


# --------------------------------------------------------------------------- #
# Signal pack.
# --------------------------------------------------------------------------- #


def test_signal_pack_groups_docs_by_file():
    G = nx.DiGraph()
    _add_node(G, "code", "code()", file_type="code")
    _add_node(G, "doc1", "intro", source_file="docs/intro.md", file_type="document")
    _add_node(G, "doc2", "guide", source_file="docs/guide.md", file_type="document")
    pack = signal_pack(G, {0: ["code"]})
    assert "docs/intro.md" in pack.docs_by_file
    assert "docs/guide.md" in pack.docs_by_file
