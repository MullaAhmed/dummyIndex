"""Schema v3: EquipmentItem origin fields + v2 back-compat. v4: provenance + StackProfile evidence."""

import json

import pytest

from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
)
from dummyindex.context.domains.equip.enums import EquipmentScope, RequestedBy
from dummyindex.context.domains.equip.models import StackProfile


def test_v3_item_round_trips_origin_fields():
    item = EquipmentItem(
        kind=EquipmentKind.SKILL,
        name="pdf-extract",
        path=".claude/skills/pdf-extract/SKILL.md",
        source=EquipmentSource.VENDORED,
        capabilities=("docs",),
        marketplace="skills",
        origin_repo="anthropics/skills",
        origin_ref="abc123",
        mechanism="vendor",
        origin_hash="deadbeef",
    )
    again = EquipmentItem.from_dict(item.to_dict())
    assert again == item


def test_v2_item_loads_with_none_origin_fields():
    legacy = {
        "kind": "agent",
        "name": "python-implementer",
        "path": ".claude/agents/python-implementer.md",
        "source": "generated",
        "capabilities": ["implement"],
        "grounded_in": [],
        "subagent_type": "python-implementer",
        "version": "1.0.0",
        "origin_hash": "abc",
    }
    item = EquipmentItem.from_dict(legacy)
    assert item.marketplace is None
    assert item.origin_repo is None
    assert item.origin_ref is None
    assert item.mechanism is None


def test_marketplace_and_vendored_source_enum_values():
    assert EquipmentSource.MARKETPLACE.value == "marketplace"
    assert EquipmentSource.VENDORED.value == "vendored"


def test_manifest_round_trips_v3_item():
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="pg-tuner@official",
        path=".claude/settings.json",
        source=EquipmentSource.MARKETPLACE,
        capabilities=("database", "performance"),
        marketplace="official",
        origin_repo="anthropics/claude-plugins-official",
        mechanism="native",
    )
    manifest = EquipmentManifest(schema_version=3, items=(item,))
    again = EquipmentManifest.from_dict(manifest.to_dict())
    assert again.items[0] == item


# The v3 key set before `invariants` existed. A default item must emit *only*
# these keys so existing v3 manifests stay byte-identical without a
# SCHEMA_VERSION bump.
_PRE_INVARIANTS_KEYS = {
    "kind",
    "name",
    "path",
    "source",
    "capabilities",
    "grounded_in",
    "subagent_type",
    "version",
    "origin_hash",
    "marketplace",
    "origin_repo",
    "origin_ref",
    "mechanism",
}


def test_default_item_omits_invariants_key_for_byte_identity():
    """An item with empty invariants serializes exactly as it did before them."""
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="python-implementer",
        path=".claude/agents/python-implementer.md",
        source=EquipmentSource.GENERATED,
        capabilities=("implement",),
        grounded_in=(".context/HOW_TO_USE.md",),
    )
    data = item.to_dict()
    assert "invariants" not in data
    assert set(data.keys()) == _PRE_INVARIANTS_KEYS
    # round-trips back to the same item even though the key was never written
    assert EquipmentItem.from_dict(data) == item


def test_item_with_invariants_emits_key_and_round_trips():
    """A non-empty invariants tuple is serialized and survives from_dict."""
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="python-implementer",
        path=".claude/agents/python-implementer.md",
        source=EquipmentSource.GENERATED,
        capabilities=("implement",),
        invariants=("frozen dataclass",),
    )
    data = item.to_dict()
    assert data["invariants"] == ["frozen dataclass"]
    again = EquipmentItem.from_dict(data)
    assert again == item
    assert again.invariants == ("frozen dataclass",)


def test_from_dict_without_invariants_defaults_to_empty_tuple():
    """A payload lacking the key yields an empty invariants tuple."""
    payload = {
        "kind": "agent",
        "name": "python-implementer",
        "path": ".claude/agents/python-implementer.md",
        "source": "generated",
        "capabilities": ["implement"],
        "grounded_in": [],
    }
    item = EquipmentItem.from_dict(payload)
    assert item.invariants == ()


# A v4 manifest written with no provenance fields. It must load and re-serialise
# to the same bytes, so the new keys never leak into existing manifests.
_V4_GOLDEN_NO_PROVENANCE = (
    "{\n"
    '  "schema_version": 4,\n'
    '  "items": [\n'
    "    {\n"
    '      "kind": "agent",\n'
    '      "name": "python-implementer",\n'
    '      "path": ".claude/agents/python-implementer.md",\n'
    '      "source": "generated",\n'
    '      "capabilities": [\n'
    '        "implement"\n'
    "      ],\n"
    '      "grounded_in": [],\n'
    '      "subagent_type": "python-implementer",\n'
    '      "version": "1.0.0",\n'
    '      "origin_hash": "abc",\n'
    '      "marketplace": null,\n'
    '      "origin_repo": null,\n'
    '      "origin_ref": null,\n'
    '      "mechanism": null\n'
    "    }\n"
    "  ]\n"
    "}\n"
)


@pytest.mark.unit
def test_v4_manifest_without_provenance_is_byte_identical():
    manifest = EquipmentManifest.from_dict(json.loads(_V4_GOLDEN_NO_PROVENANCE))
    item = manifest.items[0]
    assert item.requested_by is None
    assert item.scope is EquipmentScope.PROJECT
    assert item.task_refs == ()
    rewritten = json.dumps(manifest.to_dict(), indent=2) + "\n"
    assert rewritten == _V4_GOLDEN_NO_PROVENANCE


@pytest.mark.unit
def test_default_provenance_is_not_serialised():
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="python-implementer",
        path=".claude/agents/python-implementer.md",
        source=EquipmentSource.GENERATED,
        requested_by=RequestedBy.LEGACY,
    )
    data = item.to_dict()
    assert data["requested_by"] == "legacy"
    assert "scope" not in data
    assert "task_refs" not in data


@pytest.mark.unit
def test_task_scoped_item_with_provenance_round_trips():
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="db-specialist",
        path=".claude/agents/db-specialist.md",
        source=EquipmentSource.GENERATED,
        requested_by=RequestedBy.PROPOSAL,
        scope=EquipmentScope.TASK,
        task_refs=("proposal:add-search", "audit:auth-review"),
    )
    data = item.to_dict()
    assert data["requested_by"] == "proposal"
    assert data["scope"] == "task"
    assert data["task_refs"] == ["proposal:add-search", "audit:auth-review"]
    again = EquipmentItem.from_dict(json.loads(json.dumps(data)))
    assert again == item
    assert again.scope is EquipmentScope.TASK
    assert again.requested_by is RequestedBy.PROPOSAL


@pytest.mark.unit
def test_unknown_provenance_values_fall_back_to_defaults():
    item = EquipmentItem.from_dict(
        {
            "kind": "agent",
            "name": "python-implementer",
            "path": ".claude/agents/python-implementer.md",
            "source": "generated",
            "requested_by": "not-a-value",
            "scope": "not-a-scope",
        }
    )
    assert item.requested_by is None
    assert item.scope is EquipmentScope.PROJECT
    assert item.task_refs == ()


@pytest.mark.unit
def test_provenance_enum_values():
    assert RequestedBy.ADD_SPECIALIST.value == "add_specialist"
    assert RequestedBy.PROPOSAL.value == "proposal"
    assert RequestedBy.LEGACY.value == "legacy"
    assert EquipmentScope.PROJECT.value == "project"
    assert EquipmentScope.TASK.value == "task"


@pytest.mark.unit
def test_stack_profile_evidence_fields_default_empty_and_stay_out_of_dict():
    bare = StackProfile(label="python")
    assert bare.data_stores == ()
    assert bare.search_backends == ()
    rich = StackProfile(
        label="python",
        data_stores=("sqlalchemy",),
        search_backends=("qdrant-client",),
    )
    assert rich.data_stores == ("sqlalchemy",)
    assert rich.search_backends == ("qdrant-client",)
    # Evidence never reaches serialised output (project_binding, manifest bytes).
    assert rich.to_dict() == bare.to_dict()
    assert "data_stores" not in rich.to_dict()
    assert "search_backends" not in rich.to_dict()
