"""Presence and version checks for the required-setup manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.equip.enums import (
    EquipmentKind,
    EquipmentScope,
    EquipmentSource,
)
from dummyindex.context.domains.equip.lifecycle.manifest import write_manifest
from dummyindex.context.domains.equip.models import EquipmentItem, EquipmentManifest
from dummyindex.context.domains.memory.miner.resolve import resolve_claude_config_dir
from dummyindex.context.domains.requirements import (
    PluginRequirement,
    RequirementKind,
    Requirements,
    RequirementStatus,
    SkillRequirement,
    check_requirements,
    exit_code,
)

PLUGIN = "superpowers@claude-plugins-official"
_S = RequirementStatus


def _write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _enable_user(config_dir: Path, target: str = PLUGIN, value: bool = True) -> None:
    _write_settings(config_dir / "settings.json", {"enabledPlugins": {target: value}})


def _registry(config_dir: Path, records: dict) -> None:
    path = config_dir / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 2, "plugins": records}), encoding="utf-8")


def _user_record(version: str = "7.1.0") -> list[dict]:
    return [{"scope": "user", "installPath": "/x", "version": version}]


def _check(
    project: Path,
    config_dir: Path,
    req: Requirements,
    *,
    family: str | None = "0.39.0",
    cli: str = "0.39.0",
):
    return check_requirements(
        project,
        req,
        claude_config_dir=config_dir,
        family_stamp=family,
        cli_version=cli,
    )


def _row(rows, kind: RequirementKind, name: str):
    matches = [r for r in rows if r.kind is kind and r.name == name]
    assert len(matches) == 1, rows
    return matches[0]


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "repo"
    config_dir = tmp_path / "claude-config"
    project.mkdir()
    config_dir.mkdir()
    return project, config_dir


@pytest.mark.unit
def test_all_satisfied_exits_zero(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    _registry(config_dir, {PLUGIN: _user_record("7.1.0")})
    req = Requirements(
        min_version="0.39.0",
        plugins=(PluginRequirement(id=PLUGIN, version=">=7.0.0"),),
        skills=(SkillRequirement(name="dummyindex-plan"),),
    )
    rows = _check(project, config_dir, req)
    assert {r.status for r in rows} == {_S.SATISFIED}
    assert exit_code(rows) == 0


@pytest.mark.unit
def test_missing_plugin_not_enabled_exits_three(dirs):
    project, config_dir = dirs
    _registry(config_dir, {PLUGIN: _user_record()})
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    rows = _check(project, config_dir, req)
    row = _row(rows, RequirementKind.PLUGIN, PLUGIN)
    assert row.status is _S.MISSING
    assert row.fix == f"/plugin install {PLUGIN}"
    assert exit_code(rows) == 3


@pytest.mark.unit
def test_plugin_not_in_registry_is_missing(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    row = _row(_check(project, config_dir, req), RequirementKind.PLUGIN, PLUGIN)
    assert row.status is _S.MISSING


@pytest.mark.unit
def test_plugin_below_version_is_mismatch(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    _registry(config_dir, {PLUGIN: _user_record("6.9.0")})
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN, version=">=7.0.0"),))
    rows = _check(project, config_dir, req)
    assert _row(rows, RequirementKind.PLUGIN, PLUGIN).status is _S.VERSION_MISMATCH
    assert exit_code(rows) == 3


@pytest.mark.unit
def test_exact_version_constraint_requires_equal(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    _registry(config_dir, {PLUGIN: _user_record("7.1.0")})
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN, version="==7.0.0"),))
    rows = _check(project, config_dir, req)
    assert _row(rows, RequirementKind.PLUGIN, PLUGIN).status is _S.VERSION_MISMATCH


@pytest.mark.unit
def test_dev_explicit_false_is_missing_disabled_by_you(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    _write_settings(
        project / ".claude" / "settings.local.json", {"enabledPlugins": {PLUGIN: False}}
    )
    _registry(config_dir, {PLUGIN: _user_record()})
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    rows = _check(project, config_dir, req)
    row = _row(rows, RequirementKind.PLUGIN, PLUGIN)
    assert row.status is _S.MISSING
    assert row.reason == "disabled by you"
    assert exit_code(rows) == 3


@pytest.mark.unit
def test_user_scope_explicit_false_is_missing_disabled_by_you(dirs):
    project, config_dir = dirs
    _enable_user(config_dir, value=False)
    _registry(config_dir, {PLUGIN: _user_record()})
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    rows = _check(project, config_dir, req)
    row = _row(rows, RequirementKind.PLUGIN, PLUGIN)
    assert row.status is _S.MISSING
    assert row.reason == "disabled by you"
    assert exit_code(rows) == 3


@pytest.mark.unit
def test_project_enable_counts_when_user_settings_absent(dirs):
    project, config_dir = dirs
    _write_settings(
        project / ".claude" / "settings.json", {"enabledPlugins": {PLUGIN: True}}
    )
    _registry(config_dir, {PLUGIN: _user_record()})
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    row = _row(_check(project, config_dir, req), RequirementKind.PLUGIN, PLUGIN)
    assert row.status is _S.SATISFIED


@pytest.mark.unit
def test_project_scope_record_for_other_repo_is_missing(dirs, tmp_path):
    project, config_dir = dirs
    _enable_user(config_dir)
    other = tmp_path / "other-repo"
    _registry(
        config_dir,
        {
            PLUGIN: [
                {
                    "scope": "project",
                    "projectPath": str(other),
                    "installPath": "/x",
                    "version": "7.1.0",
                }
            ]
        },
    )
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    row = _row(_check(project, config_dir, req), RequirementKind.PLUGIN, PLUGIN)
    assert row.status is _S.MISSING


@pytest.mark.unit
def test_project_scope_record_for_this_repo_counts(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    _registry(
        config_dir,
        {
            PLUGIN: [
                {
                    "scope": "project",
                    "projectPath": str(project),
                    "installPath": "/x",
                    "version": "7.1.0",
                }
            ]
        },
    )
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    row = _row(_check(project, config_dir, req), RequirementKind.PLUGIN, PLUGIN)
    assert row.status is _S.SATISFIED


@pytest.mark.unit
def test_unreadable_registry_is_unknown_and_exit_zero(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    registry = config_dir / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True)
    registry.write_text("{not json", encoding="utf-8")
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    rows = _check(project, config_dir, req)
    assert _row(rows, RequirementKind.PLUGIN, PLUGIN).status is _S.UNKNOWN
    assert exit_code(rows) == 0


@pytest.mark.unit
def test_unparseable_recorded_version_is_unknown(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    _registry(config_dir, {PLUGIN: _user_record("dev-build")})
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN, version=">=7.0.0"),))
    rows = _check(project, config_dir, req)
    assert _row(rows, RequirementKind.PLUGIN, PLUGIN).status is _S.UNKNOWN
    assert exit_code(rows) == 0


@pytest.mark.unit
def test_dev_cli_version_is_unknown_and_exit_zero(dirs):
    project, config_dir = dirs
    req = Requirements(min_version="0.39.0")
    rows = _check(project, config_dir, req, cli="unknown")
    row = _row(rows, RequirementKind.DUMMYINDEX, "dummyindex")
    assert row.status is _S.UNKNOWN
    assert exit_code(rows) == 0


@pytest.mark.unit
def test_cli_below_min_version_is_mismatch(dirs):
    project, config_dir = dirs
    req = Requirements(min_version="0.39.0")
    rows = _check(project, config_dir, req, cli="0.38.0")
    row = _row(rows, RequirementKind.DUMMYINDEX, "dummyindex")
    assert row.status is _S.VERSION_MISMATCH
    assert row.fix
    assert exit_code(rows) == 3


@pytest.mark.unit
def test_no_min_version_gives_no_dummyindex_row(dirs):
    project, config_dir = dirs
    rows = _check(project, config_dir, Requirements(), cli="0.1.0")
    assert not [r for r in rows if r.kind is RequirementKind.DUMMYINDEX]


@pytest.mark.unit
def test_family_skill_not_installed_is_missing(dirs):
    project, config_dir = dirs
    req = Requirements(skills=(SkillRequirement(name="dummyindex-plan"),))
    rows = _check(project, config_dir, req, family=None)
    row = _row(rows, RequirementKind.SKILL, "dummyindex-plan")
    assert row.status is _S.MISSING
    assert row.fix == "dummyindex context requirements sync"
    assert exit_code(rows) == 3


@pytest.mark.unit
def test_family_stamp_below_min_is_mismatch(dirs):
    project, config_dir = dirs
    req = Requirements(
        min_version="0.39.0", skills=(SkillRequirement(name="dummyindex-plan"),)
    )
    rows = _check(project, config_dir, req, family="0.30.0")
    assert (
        _row(rows, RequirementKind.SKILL, "dummyindex-plan").status
        is _S.VERSION_MISMATCH
    )


@pytest.mark.unit
def test_family_stamp_unparseable_is_unknown(dirs):
    project, config_dir = dirs
    req = Requirements(
        min_version="0.39.0", skills=(SkillRequirement(name="dummyindex-plan"),)
    )
    rows = _check(project, config_dir, req, family="unknown")
    assert _row(rows, RequirementKind.SKILL, "dummyindex-plan").status is _S.UNKNOWN
    assert exit_code(rows) == 0


@pytest.mark.unit
def test_plugin_skill_reuses_plugin_judgement(dirs):
    project, config_dir = dirs
    req = Requirements(
        skills=(SkillRequirement(name="brainstorm", from_=f"plugin:{PLUGIN}"),)
    )
    rows = _check(project, config_dir, req)
    row = _row(rows, RequirementKind.SKILL, "brainstorm")
    assert row.status is _S.MISSING
    assert row.fix == f"/plugin install {PLUGIN}"


@pytest.mark.unit
def test_project_skill_missing_is_missing(dirs):
    project, config_dir = dirs
    req = Requirements(skills=(SkillRequirement(name="repo-helper", from_="project"),))
    rows = _check(project, config_dir, req)
    row = _row(rows, RequirementKind.SKILL, "repo-helper")
    assert row.status is _S.MISSING
    assert exit_code(rows) == 3


@pytest.mark.unit
@pytest.mark.parametrize("base", [".claude/skills", ".agents/skills"])
def test_project_skill_present_in_either_dir_is_satisfied(dirs, base):
    project, config_dir = dirs
    skill_dir = project / base / "repo-helper"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# helper\n", encoding="utf-8")
    req = Requirements(skills=(SkillRequirement(name="repo-helper", from_="project"),))
    row = _row(_check(project, config_dir, req), RequirementKind.SKILL, "repo-helper")
    assert row.status is _S.SATISFIED


def _equip_item(name: str, scope: EquipmentScope) -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=name,
        path=f".context/equipment/{name}.md",
        source=EquipmentSource.GENERATED,
        scope=scope,
    )


def _write_equipment(project: Path, items: tuple[EquipmentItem, ...]) -> None:
    write_manifest(
        project / ".context", EquipmentManifest(schema_version=4, items=items)
    )


@pytest.mark.unit
def test_missing_project_adapter_is_missing_when_native_required(dirs):
    project, config_dir = dirs
    _write_equipment(project, (_equip_item("docs-specialist", EquipmentScope.PROJECT),))
    req = Requirements(require_native_adapters=True)
    rows = _check(project, config_dir, req)
    row = _row(rows, RequirementKind.EQUIPMENT, "docs-specialist")
    assert row.status is _S.MISSING
    assert row.fix == "dummyindex context requirements sync"
    assert exit_code(rows) == 3


@pytest.mark.unit
def test_present_project_adapter_is_satisfied(dirs):
    project, config_dir = dirs
    _write_equipment(project, (_equip_item("docs-specialist", EquipmentScope.PROJECT),))
    adapter = project / ".claude" / "agents" / "docs-specialist.md"
    adapter.parent.mkdir(parents=True)
    adapter.write_text("---\nname: docs-specialist\n---\n", encoding="utf-8")
    req = Requirements(require_native_adapters=True)
    rows = _check(project, config_dir, req)
    assert (
        _row(rows, RequirementKind.EQUIPMENT, "docs-specialist").status is _S.SATISFIED
    )
    assert exit_code(rows) == 0


@pytest.mark.unit
def test_task_scoped_item_is_never_checked(dirs):
    project, config_dir = dirs
    _write_equipment(
        project, (_equip_item("frontend-specialist", EquipmentScope.TASK),)
    )
    req = Requirements(require_native_adapters=True)
    rows = _check(project, config_dir, req)
    assert not [r for r in rows if r.kind is RequirementKind.EQUIPMENT]
    assert exit_code(rows) == 0


@pytest.mark.unit
def test_adapters_not_checked_when_flag_off(dirs):
    project, config_dir = dirs
    _write_equipment(project, (_equip_item("docs-specialist", EquipmentScope.PROJECT),))
    rows = _check(project, config_dir, Requirements(require_native_adapters=False))
    assert not [r for r in rows if r.kind is RequirementKind.EQUIPMENT]


@pytest.mark.unit
def test_missing_manifest_gives_no_equipment_rows(dirs):
    project, config_dir = dirs
    rows = _check(project, config_dir, Requirements(require_native_adapters=True))
    assert not [r for r in rows if r.kind is RequirementKind.EQUIPMENT]


@pytest.mark.unit
def test_extra_plugin_changes_nothing(dirs):
    project, config_dir = dirs
    _enable_user(config_dir)
    _registry(
        config_dir,
        {PLUGIN: _user_record(), "extra@elsewhere": _user_record("0.0.1")},
    )
    _write_settings(
        config_dir / "settings.json",
        {"enabledPlugins": {PLUGIN: True, "extra@elsewhere": True}},
    )
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    rows = _check(project, config_dir, req)
    assert all(r.name != "extra@elsewhere" for r in rows)
    assert exit_code(rows) == 0


@pytest.mark.unit
def test_claude_config_dir_env_is_honoured(dirs, monkeypatch):
    project, config_dir = dirs
    _enable_user(config_dir)
    _registry(config_dir, {PLUGIN: _user_record()})
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    resolved = resolve_claude_config_dir()
    assert resolved == config_dir
    req = Requirements(plugins=(PluginRequirement(id=PLUGIN),))
    rows = check_requirements(
        project,
        req,
        claude_config_dir=resolved,
        family_stamp=None,
        cli_version="0.39.0",
    )
    assert _row(rows, RequirementKind.PLUGIN, PLUGIN).status is _S.SATISFIED
