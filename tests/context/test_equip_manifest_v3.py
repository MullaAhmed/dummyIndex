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
