"""Tests for the catalog policy core — the deterministic decision of what to
generate, adopt, and wire.

``build_catalog`` is pure over its inputs (a :class:`StackProfile`, the
conventions list, a :class:`PreflightReport`, and the proposal capabilities).
The standard generated set is fixed (implementer + tester + reviewer agents and
a verify skill); the format hook appears iff a formatter was detected;
adoption covers proposal-capability gaps before any generic fallback.
"""

from __future__ import annotations

import pytest

from dummyindex.context.domains.equip import EquipmentKind
from dummyindex.context.domains.equip.generate.catalog import build_catalog
from dummyindex.context.domains.equip.generate.specialists import SPECIALIST_TEMPLATES
from dummyindex.context.domains.equip.models import StackProfile
from dummyindex.context.domains.preflight.models import PreflightReport, SettingsState

# Specialists are no longer opt-in: every equip pass generates one per template.
# Counts are expressed as "core + the templated alphabet" so adding a template
# never silently breaks an unrelated assertion.
# Always-on specialists = the undimensioned templates. The dimensioned ones
# (frontend / api / migration / ci) are signal-gated; the FastAPI test profile
# evidences api (procedure + domain) only.
_SPECIALISTS = sum(1 for t in SPECIALIST_TEMPLATES.values() if t.dimension is None)
_API_PAIR = 2
_CORE_GENERATE = 4  # implementer + tester + reviewer agents, verify skill
_CORE_AGENTS = 3


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


def _python_profile(*, formatter: bool = True) -> StackProfile:
    return StackProfile(
        label="python",
        frameworks=("FastAPI",),
        formatter="ruff" if formatter else None,
        format_command='ruff format "$CLAUDE_FILE_PATHS"' if formatter else None,
        test_runner="pytest",
        test_command="uv run pytest -q",
        linter="ruff",
        lint_command="uv run ruff check .",
        type_checker="mypy",
        typecheck_command="uv run mypy .",
    )


@pytest.mark.unit
def test_standard_generated_set() -> None:
    decision = build_catalog(
        profile=_python_profile(),
        conventions=(".context/conventions/naming.md",),
        preflight=_report(),
        proj="myproj",
    )
    agents = [g for g in decision.generate if g.kind == EquipmentKind.AGENT]
    skills = [g for g in decision.generate if g.kind == EquipmentKind.SKILL]
    names = {g.name for g in decision.generate}
    assert "python-implementer" in names
    assert "python-tester" in names
    assert "myproj-reviewer" in names
    assert "myproj-verify" in names
    assert len(agents) == _CORE_AGENTS + _SPECIALISTS + _API_PAIR
    assert len(skills) == 1


@pytest.mark.unit
def test_every_templated_specialist_is_generated_without_being_asked() -> None:
    """A specialist is an ability, not an opt-in: a bare pass — no proposal
    capabilities, no forced caps — generates one specialist per template."""
    decision = build_catalog(
        profile=_python_profile(),
        conventions=(),
        preflight=_report(),
        proj="p",
    )
    names = {g.name for g in decision.generate}
    for template in SPECIALIST_TEMPLATES.values():
        if template.dimension is None or template.capability == "api":
            assert f"p-{template.name_suffix}" in names
        else:  # frontend / migration / ci: no signal on a FastAPI stack
            assert f"p-{template.name_suffix}" not in names


@pytest.mark.unit
def test_format_hook_present_when_formatter() -> None:
    decision = build_catalog(
        profile=_python_profile(formatter=True),
        conventions=(),
        preflight=_report(),
        proj="p",
    )
    assert len(decision.hooks) == 1
    hook = decision.hooks[0]
    assert hook.event == "PostToolUse"
    assert "ruff format" in hook.command
    assert "command -v ruff" in hook.command  # binary guard
    assert "DUMMYINDEX_EQUIP" in hook.command  # equip sentinel in body


@pytest.mark.unit
def test_no_hook_without_formatter() -> None:
    decision = build_catalog(
        profile=_python_profile(formatter=False),
        conventions=(),
        preflight=_report(),
        proj="p",
    )
    assert decision.hooks == ()


@pytest.mark.unit
def test_proposal_capability_generates_specialist_when_template_exists() -> None:
    decision = build_catalog(
        profile=_python_profile(),
        conventions=(),
        preflight=_report(),
        proj="p",
        proposal_capabilities=("database",),
    )
    # database has a template now → a grounded specialist is GENERATED (a file),
    # not recorded as a manifest-only adoption (the old Data Engineer pointer).
    assert "p-db-specialist" in {g.name for g in decision.generate}
    # The specialist is generated once, not twice, when the proposal also names
    # a capability the always-on pass already covers.
    assert len(decision.generate) == _CORE_GENERATE + _SPECIALISTS + _API_PAIR
    assert decision.adopt == ()


@pytest.mark.unit
def test_frontend_proposal_on_frontend_stack_generates_pair() -> None:
    # The real template registry backs frontend: a frontend-evidenced stack
    # GENERATES the procedure + domain pair; the registry Frontend Developer is
    # never adopted for it.
    decision = build_catalog(
        profile=StackProfile(label="typescript", frameworks=("React",)),
        conventions=(),
        preflight=_report(),
        proj="p",
        proposal_capabilities=("frontend",),
    )
    names = {g.name for g in decision.generate}
    assert {"p-frontend-procedure", "p-frontend-domain"} <= names
    assert decision.adopt == ()


@pytest.mark.unit
def test_frontend_specialists_not_generated_on_backend_stack() -> None:
    # REGRESSION: a FastAPI repo must not get frontend specialists, with or
    # without a plan that names the capability.
    for caps in ((), ("frontend",)):
        decision = build_catalog(
            profile=_python_profile(),
            conventions=(),
            preflight=_report(),
            proj="p",
            proposal_capabilities=caps,
        )
        assert not any("frontend" in g.name for g in decision.generate)


@pytest.mark.unit
def test_frontend_stack_signal_generates_without_proposal() -> None:
    decision = build_catalog(
        profile=StackProfile(label="typescript", frameworks=("React",)),
        conventions=(),
        preflight=_report(),
        proj="p",
    )
    names = {g.name for g in decision.generate}
    assert {"p-frontend-procedure", "p-frontend-domain"} <= names


@pytest.mark.unit
def test_migration_and_ci_generated_only_on_proposal_signal() -> None:
    bare = build_catalog(
        profile=_python_profile(), conventions=(), preflight=_report(), proj="p"
    )
    bare_names = {g.name for g in bare.generate}
    signalled = build_catalog(
        profile=_python_profile(),
        conventions=(),
        preflight=_report(),
        proj="p",
        proposal_capabilities=("migration", "ci"),
    )
    names = {g.name for g in signalled.generate}
    for suffix in (
        "migration-procedure",
        "migration-domain",
        "ci-procedure",
        "ci-domain",
    ):
        assert f"p-{suffix}" not in bare_names
        assert f"p-{suffix}" in names


@pytest.mark.unit
def test_user_project_agent_wins_over_stack_signalled_specialist() -> None:
    # A frontend stack with the user's own UI agent: adopt theirs, generate no
    # frontend specialist over it.
    decision = build_catalog(
        profile=StackProfile(label="typescript", frameworks=("React",)),
        conventions=(),
        preflight=_report(project_agents=("ui-wizard",)),
        proj="p",
    )
    assert [a.subagent_type for a in decision.adopt] == ["ui-wizard"]
    assert not any("frontend" in g.name for g in decision.generate)


@pytest.mark.unit
def test_unknown_capability_no_crash_no_extra_generation() -> None:
    decision = build_catalog(
        profile=_python_profile(),
        conventions=(),
        preflight=_report(),
        proj="p",
        proposal_capabilities=("blockchain",),
    )
    assert decision.adopt == ()  # nothing covers it
    # An unknown capability adds nothing beyond the always-on templated set.
    assert len(decision.generate) == _CORE_GENERATE + _SPECIALISTS + _API_PAIR


@pytest.mark.unit
def test_generic_profile_still_generates_standard_set() -> None:
    decision = build_catalog(
        profile=StackProfile(label="generic"),
        conventions=(),
        preflight=_report(),
        proj="p",
    )
    names = {g.name for g in decision.generate}
    assert "generic-implementer" in names
    assert decision.hooks == ()  # no formatter on a fresh repo


# ----- stack-consistency gate: no Frontend Developer on backend repos --------
# (audit 2026-06-13, C7: equip --for-proposal adopted 'Frontend Developer' for
# a pure-backend FastAPI repo because one frontend-ish word appeared in the
# proposal text; the registry fallthrough never saw the stack.)


@pytest.mark.unit
def test_backend_stack_skips_frontend_registry_adoption() -> None:
    decision = build_catalog(
        profile=_python_profile(),  # label=python, frameworks=(FastAPI,)
        conventions=(),
        preflight=_report(),
        proj="p",
        proposal_capabilities=("frontend",),
    )
    assert decision.adopt == ()  # no Frontend Developer on a backend stack
    # frontend is left to the generic implementer; the templated set is unchanged.
    assert len(decision.generate) == _CORE_GENERATE + _SPECIALISTS + _API_PAIR


@pytest.mark.unit
def test_database_registry_adoption_unaffected_by_frontend_gate() -> None:
    # The gate is frontend-specific: with no db template... db HAS a template,
    # so prove via resolve_coverage directly that a DATABASE registry adoption
    # still happens on a backend stack when no template covers it.
    from dummyindex.context.domains.equip import resolve_coverage

    coverage = resolve_coverage(
        preflight=_report(),
        proposal_capabilities=("database",),
        stack_frontend=False,
    )
    assert any("database" in a.capabilities for a in coverage.adopt)


@pytest.mark.unit
def test_project_frontend_agent_still_adopted_on_backend_stack() -> None:
    # The gate blocks only the REGISTRY fallthrough — a user-authored project
    # agent covering frontend is theirs and stays adopted regardless of stack.
    decision = build_catalog(
        profile=_python_profile(),
        conventions=(),
        preflight=_report(project_agents=("ui-wizard",)),
        proj="p",
        proposal_capabilities=("frontend",),
    )
    assert [a.subagent_type for a in decision.adopt] == ["ui-wizard"]
    assert not any("frontend" in g.name for g in decision.generate)


@pytest.mark.unit
def test_profile_has_frontend_predicate() -> None:
    from dummyindex.context.domains.equip import profile_has_frontend

    assert profile_has_frontend(StackProfile(label="typescript")) is True
    assert profile_has_frontend(StackProfile(label="javascript")) is True
    assert (
        profile_has_frontend(StackProfile(label="python", frameworks=("React",)))
        is True
    )
    assert (
        profile_has_frontend(StackProfile(label="python", frameworks=("FastAPI",)))
        is False
    )
    assert profile_has_frontend(StackProfile(label="generic")) is False
