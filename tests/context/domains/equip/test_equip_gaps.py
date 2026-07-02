"""Wave 1 — pure capability-gap core (no I/O).

`capability_gaps = required(stack, proposal) - covered(manifest)`, ordered by the
`Capability` declaration order so discovery/build act on a real, deterministic
gap instead of the old 2-tag stub.
"""

from __future__ import annotations

from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    Capability,
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    StackProfile,
    capability_gaps,
    covered_capabilities,
    required_capabilities,
)

_PYTHON = StackProfile(
    label="python",
    test_runner="pytest",
    test_command="uv run pytest -q",
    formatter="ruff",
    format_command="ruff format",
)
_GENERIC = StackProfile(label="generic")


def _item(*caps: str) -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="x",
        path=".claude/agents/x.md",
        source=EquipmentSource.GENERATED,
        capabilities=tuple(caps),
    )


def _manifest(*items: EquipmentItem) -> EquipmentManifest:
    return EquipmentManifest(schema_version=SCHEMA_VERSION, items=items)


# ----- covered_capabilities -------------------------------------------------


def test_covered_capabilities_unions_every_item():
    manifest = _manifest(_item("implement"), _item("test", "review"))
    assert covered_capabilities(manifest) == frozenset({"implement", "test", "review"})


def test_covered_capabilities_empty_manifest_is_empty():
    assert covered_capabilities(_manifest()) == frozenset()


# ----- required_capabilities ------------------------------------------------


def test_required_includes_stack_baseline_for_real_stack():
    required = required_capabilities(_PYTHON)
    assert {"implement", "test", "review", "verify", "format"} <= required


def test_required_generic_stack_omits_code_baseline():
    required = required_capabilities(_GENERIC)
    assert "implement" not in required
    assert "test" not in required
    assert "format" not in required


def test_required_folds_in_proposal_capabilities():
    required = required_capabilities(
        _PYTHON, proposal_capabilities=("security", "database")
    )
    assert {"security", "database"} <= required


def test_required_returns_plain_strings():
    # frozenset[str] — values must compare equal to the enum values as plain str.
    required = required_capabilities(_PYTHON)
    assert all(isinstance(c, str) for c in required)
    assert Capability.TEST.value in required


# ----- capability_gaps ------------------------------------------------------


def test_gaps_subtract_what_the_manifest_already_covers():
    # python core fully equipped; proposal asks for security → only security gaps.
    manifest = _manifest(_item("implement", "test", "review", "verify", "format"))
    gaps = capability_gaps(
        profile=_PYTHON, manifest=manifest, proposal_capabilities=("security",)
    )
    assert gaps == ("security",)


def test_gaps_empty_when_fully_covered():
    manifest = _manifest(_item("implement", "test", "review", "verify", "format"))
    assert capability_gaps(profile=_PYTHON, manifest=manifest) == ()


def test_gaps_follow_capability_declaration_order_not_input_order():
    # Ask out of order; expect Capability enum order: database < security < docs.
    gaps = capability_gaps(
        profile=_GENERIC,
        manifest=_manifest(),
        proposal_capabilities=("docs", "security", "database"),
    )
    assert gaps == ("database", "security", "docs")


def test_gaps_unequipped_real_stack_reports_core_gap():
    # No manifest items → the core baseline itself is a gap (the "not equipped"
    # signal the build loop surfaces).
    gaps = capability_gaps(profile=_PYTHON, manifest=_manifest())
    assert "implement" in gaps
    assert "test" in gaps


def test_gaps_are_pure_and_repeatable():
    manifest = _manifest(_item("implement"))
    first = capability_gaps(
        profile=_PYTHON, manifest=manifest, proposal_capabilities=("security",)
    )
    second = capability_gaps(
        profile=_PYTHON, manifest=manifest, proposal_capabilities=("security",)
    )
    assert first == second
