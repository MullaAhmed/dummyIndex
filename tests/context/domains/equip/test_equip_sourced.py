"""Pure compose/item tests for sourced specialists (generate/sourced.py)."""

from __future__ import annotations

import hashlib

import pytest

from dummyindex.context.domains.equip.enums import EquipmentKind, EquipmentSource
from dummyindex.context.domains.equip.errors import TemplateError
from dummyindex.context.domains.equip.generate.sourced import (
    OVERLAY_INVARIANTS,
    compose_body,
    render_overlay,
    sourced_description,
    sourced_item,
)
from dummyindex.context.domains.equip.lifecycle.hashing import content_hash
from dummyindex.context.domains.equip.models import EquipmentItem, StackProfile

pytestmark = pytest.mark.unit

UPSTREAM = (
    "---\nname: up\ndescription: upstream desc\nallowed-tools: Bash\n---\n"
    "# Up\n\nUse {{name}} literally.\n"
)
BODY = "# Up\n\nUse {{name}} literally.\n"


def _overlay() -> str:
    profile = StackProfile(label="python", frameworks=("fastapi",))
    return render_overlay(
        profile=profile,
        proj="demo",
        conventions=(".context/conventions/naming.md",),
    )


def _compose(overlay: str | None = None) -> str:
    return compose_body(
        overlay=_overlay() if overlay is None else overlay,
        name="demo-db-specialist",
        description=sourced_description("database", "python", "o/r", "db-helper"),
        repo="o/r",
        skill="db-helper",
        ref="a" * 40,
        body=BODY,
    )


def _frontmatter(text: str) -> str:
    first = text.index("---")
    second = text.index("---", first + 3)
    return text[first : second + 3]


def test_result_ends_with_body_exactly() -> None:
    assert _compose().endswith(BODY)


def test_frontmatter_has_our_identity_and_no_upstream_keys() -> None:
    fm = _frontmatter(_compose())
    assert "name: demo-db-specialist" in fm
    assert "version: 1.0.0" in fm
    assert "allowed-tools" not in fm
    assert "upstream desc" not in fm
    assert "name: up" not in fm


def test_upstream_placeholders_stay_literal() -> None:
    assert "Use {{name}} literally." in _compose()


def test_result_contains_invariants_and_headings() -> None:
    result = _compose()
    for invariant in OVERLAY_INVARIANTS:
        assert result.count(invariant) == 1
    assert "## Repo overlay" in result
    assert "## Upstream skill: o/r/db-helper@aaaaaaaaaaaa" in result


def test_no_residual_template_slots() -> None:
    result = _compose()
    for slot in ("{{upstream}}", "{{description}}", "{{stack}}"):
        assert slot not in result


def test_overlay_without_upstream_slot_raises() -> None:
    with pytest.raises(TemplateError):
        _compose(overlay=_overlay().replace("{{upstream}}", ""))


def test_sourced_description_has_no_colon() -> None:
    assert ":" not in sourced_description("database", "python", "o/r", "db-helper")


def test_sourced_item_sets_origin_and_keeps_identity() -> None:
    template = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="demo-db-specialist",
        path=".context/equipment/demo-db-specialist.md",
        source=EquipmentSource.GENERATED,
        capabilities=("database",),
        invariants=("t1", "t2", "t3"),
        subagent_type="demo-db-specialist",
        version="1.0.0",
        origin_hash="sha256:old",
        package_sha256="0" * 64,
    )
    content = _compose()
    item = sourced_item(
        template,
        repo="o/r",
        skill="db-helper",
        ref="a" * 40,
        path="skills/db-helper/SKILL.md",
        upstream_text=UPSTREAM,
        marketplace="ecc",
        content=content,
    )

    assert item.origin_repo == "o/r"
    assert item.origin_ref == "a" * 40
    assert item.marketplace == "ecc"
    assert item.capability_id == "o/r/db-helper"
    assert item.package_source == "skills/db-helper/SKILL.md"
    assert item.package_version == "a" * 12
    assert item.package_sha256 == hashlib.sha256(UPSTREAM.encode()).hexdigest()
    assert item.invariants == OVERLAY_INVARIANTS
    assert item.origin_hash == content_hash(content)

    assert item.source is EquipmentSource.GENERATED
    assert item.name == template.name
    assert item.path == template.path
    assert item.kind is template.kind
    assert item.subagent_type == template.subagent_type
    assert item.capabilities == template.capabilities
    assert item.mechanism is None
