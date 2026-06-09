"""Vendoring helpers: stamp + manifest item (pure)."""
from dummyindex.context.domains.equip import (
    EquipmentKind,
    EquipmentSource,
    stamp_vendored,
    vendored_item,
)
from dummyindex.context.domains.equip._constants import VENDORED_SENTINEL


def test_stamp_adds_sentinel_once():
    body = "# Agent\nbody\n"
    stamped = stamp_vendored(body)
    assert VENDORED_SENTINEL in stamped
    assert stamp_vendored(stamped).count(VENDORED_SENTINEL) == 1


def test_vendored_item_records_origin_and_hash():
    item = vendored_item(
        name="pdf-extract",
        rel_path=".claude/skills/pdf-extract/SKILL.md",
        kind_skill=True,
        capabilities=("docs",),
        repo="anthropics/skills",
        ref="abc123",
        content="x",
        marketplace="agent-skills",
    )
    assert item.kind == EquipmentKind.SKILL
    assert item.source == EquipmentSource.VENDORED
    assert item.origin_repo == "anthropics/skills"
    assert item.origin_ref == "abc123"
    assert item.marketplace == "agent-skills"
    assert item.mechanism == "vendor"
    assert item.origin_hash is not None


def test_vendored_item_agent_kind():
    item = vendored_item(
        name="sec-reviewer",
        rel_path=".claude/agents/sec-reviewer.md",
        kind_skill=False,
        capabilities=("security",),
        repo="affaan-m/ECC",
        ref=None,
        content="y",
    )
    assert item.kind == EquipmentKind.AGENT
    assert item.origin_ref is None
