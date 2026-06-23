"""Schema v3: EquipmentItem origin fields + v2 back-compat."""

from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
)


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


# The pre-invariants v3 key set — the exact serialized shape of an
# EquipmentItem.to_dict() before the `invariants` field existed. A default
# item must still emit *only* these keys so existing v3 manifests stay
# byte-identical (Decision D3 — no SCHEMA_VERSION bump).
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
    """An item with empty invariants serializes exactly as it did pre-D3."""
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
