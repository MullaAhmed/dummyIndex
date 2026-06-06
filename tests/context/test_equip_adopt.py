"""Tests for equip adoption — project agents + known-specialist registry.

Adoption is pure over its inputs (a :class:`PreflightReport` + the needed
capabilities) and never writes files: adopted items are manifest records only.
Project agents are preferred; the registry fills the remaining gaps; each
capability is satisfied at most once.
"""
from __future__ import annotations

import pytest

from dummyindex.context.domains.dev_pick import SubagentType
from dummyindex.context.domains.equip import EquipmentSource
from dummyindex.context.domains.equip import (
    adopt_existing,
    registry_capabilities,
)
from dummyindex.context.domains.preflight.models import PreflightReport, SettingsState


def _report(*, project_agents: tuple[str, ...] = ()) -> PreflightReport:
    return PreflightReport(
        project_root="/tmp/x",
        is_git_repo=True,
        git_clean=True,
        settings=SettingsState(
            exists=False,
            parseable=True,
            user_hook_events=(),
            dummyindex_hook_present=False,
        ),
        rule_files=(),
        project_agents=project_agents,
        claude_md_exists=False,
        claude_md_has_managed_block=False,
    )


@pytest.mark.unit
def test_registry_covers_every_subagent_with_capabilities() -> None:
    registry = registry_capabilities()
    for member in SubagentType:
        assert member in registry, f"{member} missing from registry map"
        assert registry[member], f"{member} has empty capabilities"


@pytest.mark.unit
def test_security_gap_not_filled_when_registry_lacks_it() -> None:
    """No SubagentType names a security specialist → the gap is NOT adopted.

    Adopt-before-generate means an uncovered capability falls back to the
    generic implementer (decided in the catalog), not a speculative adoption.
    """
    adopted = adopt_existing(preflight=_report(), needed=("security",))
    assert all("security" not in a.capabilities for a in adopted)
    assert adopted == ()


@pytest.mark.unit
def test_registry_fills_database_gap() -> None:
    adopted = adopt_existing(preflight=_report(), needed=("database",))
    assert len(adopted) == 1
    item = adopted[0]
    assert item.subagent_type == SubagentType.DATA.value  # "Data Engineer"
    assert item.source == EquipmentSource.INSTALLED
    assert item.path == ""
    assert "database" in item.capabilities


@pytest.mark.unit
def test_project_agent_preferred_and_capabilities_inferred() -> None:
    adopted = adopt_existing(
        preflight=_report(project_agents=("db-helper",)), needed=("database",)
    )
    assert len(adopted) == 1
    item = adopted[0]
    assert item.subagent_type == "db-helper"   # the file stem
    assert item.source == EquipmentSource.INSTALLED
    assert "database" in item.capabilities


@pytest.mark.unit
def test_each_capability_adopted_at_most_once() -> None:
    # A project agent covering database + a registry that also could → only one.
    adopted = adopt_existing(
        preflight=_report(project_agents=("db-helper",)), needed=("database",)
    )
    assert len(adopted) == 1


@pytest.mark.unit
def test_infer_capabilities_from_stem() -> None:
    # Observable through adopt_existing: a project agent's stem yields the
    # capability that lets it fill the matching gap.
    for stem, cap in (
        ("security-auditor", "security"),
        ("db-migrator", "database"),
        ("react-ui-helper", "frontend"),
    ):
        adopted = adopt_existing(preflight=_report(project_agents=(stem,)), needed=(cap,))
        assert [a.subagent_type for a in adopted] == [stem]
        assert cap in adopted[0].capabilities


@pytest.mark.unit
def test_no_need_adopts_nothing() -> None:
    assert adopt_existing(preflight=_report(project_agents=("db-helper",)), needed=()) == ()
