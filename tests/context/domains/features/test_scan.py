"""`features/graph.json` schema v2 — the curated codebase scan.

Covers the three halves of the artifact:

- **models** — frozen dataclasses serialize to the wire shape, omitting
  every optional field that was never set (the viewer and the authoring
  prompt both read a tight object).
- **seed** — the deterministic backbone `scaffold_features` writes before
  any model has curated it: one `service` node per feature, `entry` nodes
  from flows, cross-feature `calls` edges, all inside the caps.
- **validate** — the boundary check the authoring prompt loops against.
  A curated scan is model-authored, so it is untrusted input.
"""

from __future__ import annotations

import pytest

from dummyindex.context.domains.features.constants import (
    MAX_SCAN_EDGES,
    MAX_SCAN_NODES,
    SCAN_SCHEMA_VERSION,
)
from dummyindex.context.domains.features.models import Feature, Flow, FlowStep
from dummyindex.context.domains.features.scan import (
    Scan,
    ScanChip,
    ScanEdge,
    ScanNode,
    ScanProject,
    ScanStats,
    seed_scan,
    validate_scan,
)
from dummyindex.context.enums import ScanEdgeKind, ScanNodeKind
from dummyindex.pipeline.enums import ConfidenceLevel

# ----- fixtures --------------------------------------------------------------


def _feature(
    fid: str,
    *,
    name: str | None = None,
    files: tuple[str, ...] = (),
    flow_ids: tuple[str, ...] = (),
    summary: str | None = None,
) -> Feature:
    return Feature(
        feature_id=fid,
        kind="community",
        name=name or fid,
        summary=summary,
        members=(),
        files=files,
        entry_points=(),
        flow_ids=flow_ids,
    )


def _flow(
    flow_id: str,
    feature_id: str,
    *,
    label: str = "main",
    path: str | None = "app/main.py",
    files: tuple[str, ...] = (),
) -> Flow:
    return Flow(
        flow_id=flow_id,
        feature_id=feature_id,
        entry_point="sym::1",
        entry_point_label=label,
        entry_point_path=path,
        steps=(
            FlowStep(depth=0, node_id="sym::1", label=label, path=path, range=None),
        ),
        files=files,
    )


def _minimal_payload() -> dict:
    """A valid curated scan — the baseline every validate test mutates."""
    return Scan(
        project=ScanProject(name="Acme", slug="acme"),
        stats=ScanStats(),
        nodes=(
            ScanNode(id="api", label="HTTP API", kind=ScanNodeKind.ENTRY),
            ScanNode(id="billing", label="Billing", kind=ScanNodeKind.SERVICE),
        ),
        edges=(ScanEdge(from_id="api", to_id="billing", kind=ScanEdgeKind.TRIGGERS),),
    ).to_dict()


# ----- models ----------------------------------------------------------------


@pytest.mark.unit
def test_scan_to_dict_emits_the_foglamp_wire_shape() -> None:
    payload = Scan(
        project=ScanProject(name="Acme", slug="acme", tagline="Ships things"),
        stats=ScanStats(agents=1, models=2, tools=3, integrations=4),
        nodes=(ScanNode(id="a", label="A", kind=ScanNodeKind.SERVICE),),
        edges=(),
        top_models=(ScanChip(id="gpt-4o", label="GPT-4o", domain="openai.com"),),
    ).to_dict()

    assert payload["schema_version"] == SCAN_SCHEMA_VERSION
    assert payload["project"] == {
        "name": "Acme",
        "slug": "acme",
        "tagline": "Ships things",
    }
    assert payload["stats"] == {
        "agents": 1,
        "models": 2,
        "tools": 3,
        "integrations": 4,
    }
    assert payload["topModels"] == [
        {"id": "gpt-4o", "label": "GPT-4o", "domain": "openai.com"}
    ]
    assert payload["topTools"] == []
    assert payload["graph"]["nodes"] == [{"id": "a", "label": "A", "kind": "service"}]
    assert payload["graph"]["edges"] == []


@pytest.mark.unit
def test_scan_node_omits_unset_optional_fields() -> None:
    """A node that only has the required trio serializes to exactly three keys."""
    bare = ScanNode(id="a", label="A", kind=ScanNodeKind.STORE).to_dict()
    assert set(bare) == {"id", "label", "kind"}


@pytest.mark.unit
def test_scan_node_renames_source_ref_to_camel_case() -> None:
    node = ScanNode(
        id="a",
        label="A",
        kind=ScanNodeKind.AGENT,
        source_ref="src/agents/support.ts:42",
        detail="Answers tickets.",
        group="Support",
        sub="streamText",
    ).to_dict()
    assert node["sourceRef"] == "src/agents/support.ts:42"
    assert "source_ref" not in node


@pytest.mark.unit
def test_scan_edge_uses_from_and_to_keys() -> None:
    edge = ScanEdge(from_id="a", to_id="b", kind=ScanEdgeKind.WRITES).to_dict()
    assert edge == {"from": "a", "to": "b", "kind": "writes"}


@pytest.mark.unit
def test_scan_edge_without_kind_or_label_is_two_keys() -> None:
    assert ScanEdge(from_id="a", to_id="b").to_dict() == {"from": "a", "to": "b"}


@pytest.mark.unit
def test_seeded_scan_is_marked_extracted_not_inferred() -> None:
    """The preservation contract keys off this field — it must ship in the JSON."""
    payload = seed_scan((), (), project_name="Acme", slug="acme").to_dict()
    assert payload["confidence"] == ConfidenceLevel.EXTRACTED


# ----- seed ------------------------------------------------------------------


@pytest.mark.unit
def test_seed_emits_one_service_node_per_feature() -> None:
    scan = seed_scan(
        (
            _feature("auth", name="Auth", files=("app/auth.py",)),
            _feature("billing", name="Billing", files=("app/billing.py",)),
        ),
        (),
        project_name="Acme",
        slug="acme",
    )
    services = [n for n in scan.nodes if n.kind == ScanNodeKind.SERVICE]
    assert [n.id for n in services] == ["auth", "billing"]
    assert [n.label for n in services] == ["Auth", "Billing"]


@pytest.mark.unit
def test_seed_points_service_nodes_at_source() -> None:
    scan = seed_scan(
        (_feature("auth", files=("app/z.py", "app/a.py")),),
        (),
        project_name="Acme",
        slug="acme",
    )
    node = scan.nodes[0]
    assert node.source_ref == "app/a.py", "lowest-sorted file, so the ref is stable"
    assert node.sub == "2 files"


@pytest.mark.unit
def test_seed_turns_flows_into_entry_nodes_that_trigger_their_feature() -> None:
    scan = seed_scan(
        (_feature("auth", files=("app/auth.py",), flow_ids=("flow-001",)),),
        (_flow("flow-001", "auth", label="login", path="app/auth.py"),),
        project_name="Acme",
        slug="acme",
    )
    entries = [n for n in scan.nodes if n.kind == ScanNodeKind.ENTRY]
    assert [n.id for n in entries] == ["flow-001"]
    assert entries[0].label == "login"
    assert entries[0].source_ref == "app/auth.py"
    assert ScanEdge(
        from_id="flow-001", to_id="auth", kind=ScanEdgeKind.TRIGGERS
    ) in list(scan.edges)


@pytest.mark.unit
def test_seed_links_features_that_reach_into_each_others_files() -> None:
    """A flow owned by `auth` that touches a `billing` file is a real call edge."""
    scan = seed_scan(
        (
            _feature("auth", files=("app/auth.py",), flow_ids=("flow-001",)),
            _feature("billing", files=("app/billing.py",)),
        ),
        (
            _flow(
                "flow-001",
                "auth",
                files=("app/auth.py", "app/billing.py"),
            ),
        ),
        project_name="Acme",
        slug="acme",
    )
    calls = [e for e in scan.edges if e.kind == ScanEdgeKind.CALLS]
    assert [(e.from_id, e.to_id) for e in calls] == [("auth", "billing")]


@pytest.mark.unit
def test_seed_does_not_emit_a_feature_calling_itself() -> None:
    scan = seed_scan(
        (_feature("auth", files=("app/auth.py",), flow_ids=("flow-001",)),),
        (_flow("flow-001", "auth", files=("app/auth.py",)),),
        project_name="Acme",
        slug="acme",
    )
    assert not [e for e in scan.edges if e.kind == ScanEdgeKind.CALLS]


@pytest.mark.unit
def test_seed_respects_the_node_and_edge_caps() -> None:
    features = tuple(
        _feature(f"f{i:03d}", files=(f"app/f{i}.py",), flow_ids=(f"flow-{i:03d}",))
        for i in range(80)
    )
    flows = tuple(
        _flow(f"flow-{i:03d}", f"f{i:03d}", files=(f"app/f{i}.py",)) for i in range(80)
    )
    scan = seed_scan(features, flows, project_name="Acme", slug="acme")
    assert len(scan.nodes) <= MAX_SCAN_NODES
    assert len(scan.edges) <= MAX_SCAN_EDGES
    assert not validate_scan(scan.to_dict()), "a capped seed is still a valid scan"


@pytest.mark.unit
def test_seed_keeps_the_biggest_features_when_it_has_to_cut() -> None:
    features = (
        _feature("small", files=("a.py",)),
        _feature("huge", files=tuple(f"h{i}.py" for i in range(50))),
    )
    scan = seed_scan(features, (), project_name="Acme", slug="acme", max_nodes=1)
    assert [n.id for n in scan.nodes] == ["huge"]


@pytest.mark.unit
def test_seed_drops_edges_whose_endpoints_were_cut() -> None:
    """Cap enforcement must never leave a dangling edge behind."""
    features = (
        _feature("huge", files=tuple(f"h{i}.py" for i in range(50))),
        _feature("small", files=("a.py",), flow_ids=("flow-001",)),
    )
    flows = (_flow("flow-001", "small", files=("a.py", "h0.py")),)
    scan = seed_scan(features, flows, project_name="Acme", slug="acme", max_nodes=1)
    ids = {n.id for n in scan.nodes}
    assert all(e.from_id in ids and e.to_id in ids for e in scan.edges)


@pytest.mark.unit
def test_seed_truncates_overlong_labels_and_summaries() -> None:
    scan = seed_scan(
        (
            _feature(
                "f",
                name="A" * 100,
                files=("a.py",),
                summary="S" * 400,
            ),
        ),
        (),
        project_name="Acme",
        slug="acme",
    )
    assert not validate_scan(scan.to_dict())


@pytest.mark.unit
def test_seed_of_an_empty_repo_is_still_a_valid_scan() -> None:
    scan = seed_scan((), (), project_name="Acme", slug="acme")
    assert scan.nodes == ()
    assert not validate_scan(scan.to_dict())


@pytest.mark.unit
def test_seed_is_byte_reproducible() -> None:
    args = (
        (
            _feature("b", files=("b.py",), flow_ids=("flow-002",)),
            _feature("a", files=("a.py",), flow_ids=("flow-001",)),
        ),
        (_flow("flow-002", "b", files=("b.py", "a.py")), _flow("flow-001", "a")),
    )
    first = seed_scan(*args, project_name="Acme", slug="acme").to_dict()
    second = seed_scan(*args, project_name="Acme", slug="acme").to_dict()
    assert first == second


@pytest.mark.unit
def test_seed_leaves_the_ai_surface_for_the_model_to_fill() -> None:
    """Provider/model/tool detection is judgment, not extraction."""
    scan = seed_scan(
        (_feature("auth", files=("app/auth.py",)),), (), project_name="A", slug="a"
    )
    assert scan.stats == ScanStats()
    assert scan.top_models == ()
    assert scan.top_tools == ()
    assert scan.top_integrations == ()


# ----- validate --------------------------------------------------------------


@pytest.mark.unit
def test_validate_accepts_a_well_formed_scan() -> None:
    assert validate_scan(_minimal_payload()) == ()


@pytest.mark.unit
def test_validate_rejects_a_non_dict_payload() -> None:
    violations = validate_scan([])  # type: ignore[arg-type]
    assert [v.code for v in violations] == ["not_an_object"]


@pytest.mark.unit
def test_validate_flags_a_wrong_schema_version() -> None:
    payload = _minimal_payload()
    payload["schema_version"] = 1
    assert any(v.code == "schema_version" for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_flags_a_dangling_edge_endpoint() -> None:
    payload = _minimal_payload()
    payload["graph"]["edges"].append({"from": "api", "to": "ghost"})
    violations = validate_scan(payload)
    assert any(v.code == "edge_endpoint" for v in violations)
    assert any("ghost" in v.message for v in violations)


@pytest.mark.unit
def test_validate_flags_duplicate_node_ids() -> None:
    payload = _minimal_payload()
    payload["graph"]["nodes"].append({"id": "api", "label": "Dup", "kind": "entry"})
    assert any(v.code == "duplicate_node_id" for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_flags_an_unknown_node_kind() -> None:
    payload = _minimal_payload()
    payload["graph"]["nodes"][0]["kind"] = "microservice"
    violations = validate_scan(payload)
    assert any(v.code == "node_kind" for v in violations)
    assert any("service" in v.message for v in violations), "message lists the alphabet"


@pytest.mark.unit
def test_validate_flags_an_unknown_edge_kind() -> None:
    payload = _minimal_payload()
    payload["graph"]["edges"][0]["kind"] = "invokes"
    assert any(v.code == "edge_kind" for v in validate_scan(payload))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("label", "L" * 29, "node_label_length"),
        ("sub", "S" * 41, "node_sub_length"),
        ("detail", "D" * 201, "node_detail_length"),
        ("sourceRef", "R" * 121, "node_source_ref_length"),
        ("group", "G" * 25, "node_group_length"),
    ],
)
def test_validate_enforces_node_text_caps(field: str, value: str, code: str) -> None:
    payload = _minimal_payload()
    payload["graph"]["nodes"][0][field] = value
    assert any(v.code == code for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_enforces_the_edge_label_cap() -> None:
    payload = _minimal_payload()
    payload["graph"]["edges"][0]["label"] = "x" * 25
    assert any(v.code == "edge_label_length" for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_enforces_the_node_count_cap() -> None:
    payload = _minimal_payload()
    payload["graph"]["nodes"] = [
        {"id": f"n{i}", "label": f"n{i}", "kind": "service"}
        for i in range(MAX_SCAN_NODES + 1)
    ]
    payload["graph"]["edges"] = []
    assert any(v.code == "node_count" for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_enforces_the_top_models_cap() -> None:
    payload = _minimal_payload()
    payload["topModels"] = [{"id": f"m{i}", "label": f"M{i}"} for i in range(4)]
    assert any(v.code == "top_models_count" for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_rejects_a_domain_with_a_scheme() -> None:
    payload = _minimal_payload()
    payload["graph"]["nodes"][0]["domain"] = "https://openai.com"
    assert any(v.code == "domain_format" for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_rejects_a_non_slug_project_slug() -> None:
    payload = _minimal_payload()
    payload["project"]["slug"] = "Acme Corp"
    assert any(v.code == "project_slug" for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_rejects_a_malformed_date() -> None:
    payload = _minimal_payload()
    payload["project"]["date"] = "24-07-2026"
    assert any(v.code == "project_date" for v in validate_scan(payload))


@pytest.mark.unit
def test_validate_accepts_an_iso_date() -> None:
    payload = _minimal_payload()
    payload["project"]["date"] = "2026-07-24"
    assert validate_scan(payload) == ()


@pytest.mark.unit
def test_validate_reports_every_violation_not_just_the_first() -> None:
    payload = _minimal_payload()
    payload["graph"]["nodes"][0]["kind"] = "nope"
    payload["graph"]["nodes"][1]["label"] = "L" * 40
    payload["graph"]["edges"].append({"from": "ghost", "to": "api"})
    codes = {v.code for v in validate_scan(payload)}
    assert codes == {"node_kind", "node_label_length", "edge_endpoint"}


@pytest.mark.unit
def test_violations_carry_a_json_path_the_author_can_act_on() -> None:
    payload = _minimal_payload()
    payload["graph"]["nodes"][1]["kind"] = "nope"
    violation = next(v for v in validate_scan(payload) if v.code == "node_kind")
    assert violation.path == "graph.nodes[1].kind"


# ----- cross-feature edges from the call graph -------------------------------
#
# Flows are the obvious edge signal and the unreliable one: council stage 4
# discards most of them by design ("expect 15-25 of ~75 to survive"), and a
# fully enriched repo can end with none — leaving a seed of disconnected
# boxes. The call graph is always there, so it carries the edges.


def _link(src: str, dst: str, relation: str = "calls") -> dict:
    return {"source": src, "target": dst, "relation": relation}


def _feature_with_members(fid: str, members: tuple[str, ...], files: tuple[str, ...]):
    return Feature(
        feature_id=fid,
        kind="community",
        name=fid,
        summary=None,
        members=members,
        files=files,
        entry_points=(),
        flow_ids=(),
    )


@pytest.mark.unit
def test_seed_derives_edges_from_cross_feature_calls_without_any_flows() -> None:
    scan = seed_scan(
        (
            _feature_with_members("auth", ("a1", "a2"), ("auth.py",)),
            _feature_with_members("billing", ("b1",), ("billing.py",)),
        ),
        (),
        project_name="Acme",
        slug="acme",
        links=(_link("a1", "b1"),),
    )
    assert [(e.from_id, e.to_id, e.kind) for e in scan.edges] == [
        ("auth", "billing", ScanEdgeKind.CALLS)
    ]


@pytest.mark.unit
def test_seed_counts_uses_as_a_call_but_ignores_containment() -> None:
    features = (
        _feature_with_members("auth", ("a1",), ("auth.py",)),
        _feature_with_members("billing", ("b1",), ("billing.py",)),
    )
    uses = seed_scan(
        features, (), project_name="A", slug="a", links=(_link("a1", "b1", "uses"),)
    )
    assert len(uses.edges) == 1

    for noise in ("contains", "imports_from", "rationale_for", "inherits"):
        quiet = seed_scan(
            features, (), project_name="A", slug="a", links=(_link("a1", "b1", noise),)
        )
        assert quiet.edges == (), f"{noise} is not a call"


@pytest.mark.unit
def test_seed_ignores_calls_between_symbols_it_cannot_place() -> None:
    scan = seed_scan(
        (_feature_with_members("auth", ("a1",), ("auth.py",)),),
        (),
        project_name="A",
        slug="a",
        links=(_link("a1", "unknown"), _link("ghost", "a1")),
    )
    assert scan.edges == ()


@pytest.mark.unit
def test_seed_does_not_draw_a_feature_calling_itself() -> None:
    scan = seed_scan(
        (_feature_with_members("auth", ("a1", "a2"), ("auth.py",)),),
        (),
        project_name="A",
        slug="a",
        links=(_link("a1", "a2"),),
    )
    assert scan.edges == ()


@pytest.mark.unit
def test_seed_collapses_many_calls_between_two_features_into_one_edge() -> None:
    scan = seed_scan(
        (
            _feature_with_members("auth", ("a1", "a2"), ("auth.py",)),
            _feature_with_members("billing", ("b1", "b2"), ("billing.py",)),
        ),
        (),
        project_name="A",
        slug="a",
        links=(_link("a1", "b1"), _link("a2", "b2"), _link("a1", "b2")),
    )
    assert len(scan.edges) == 1


@pytest.mark.unit
def test_seed_keeps_the_busiest_links_when_the_edge_cap_bites() -> None:
    """Call *volume* is the only ranking signal available, so use it."""
    features = tuple(
        _feature_with_members(f"f{i}", (f"s{i}",), (f"f{i}.py",)) for i in range(4)
    )
    links = (
        # f0 → f1 called three times; f0 → f2 once.
        _link("s0", "s1"),
        _link("s0", "s1"),
        _link("s0", "s1"),
        _link("s0", "s2"),
    )
    scan = seed_scan(features, (), project_name="A", slug="a", links=links, max_edges=1)
    assert [(e.from_id, e.to_id) for e in scan.edges] == [("f0", "f1")]


@pytest.mark.unit
def test_seed_does_not_duplicate_an_edge_both_signals_found() -> None:
    feature_a = Feature(
        feature_id="auth",
        kind="community",
        name="auth",
        summary=None,
        members=("a1",),
        files=("auth.py",),
        entry_points=(),
        flow_ids=("flow-001",),
    )
    scan = seed_scan(
        (feature_a, _feature_with_members("billing", ("b1",), ("billing.py",))),
        (_flow("flow-001", "auth", files=("auth.py", "billing.py")),),
        project_name="A",
        slug="a",
        links=(_link("a1", "b1"),),
    )
    calls = [e for e in scan.edges if e.kind == ScanEdgeKind.CALLS]
    assert calls == [ScanEdge(from_id="auth", to_id="billing", kind=ScanEdgeKind.CALLS)]
