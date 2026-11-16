"""Presence and version checks for the required-setup manifest.

Pure reads: nothing here writes to ``~/.claude`` or the repo. The caller
supplies the Claude config dir and the family stamp, so tests can point at
a temp dir.
"""

from __future__ import annotations

from pathlib import Path

from dummyindex.context.claude_plugins import (
    PluginRegistryError,
    installed_plugin_record,
)
from dummyindex.context.claude_settings import MalformedSettingsError, load_settings
from dummyindex.context.default_plugins import _effective_enabled
from dummyindex.context.domains.equip.enums import EquipmentScope
from dummyindex.context.domains.equip.errors import EquipError
from dummyindex.context.domains.equip.generate.adapters import native_adapter_path
from dummyindex.context.domains.equip.lifecycle.manifest import read_manifest
from dummyindex.context.versioning import VersionOrder, compare_versions

from .enums import RequirementKind, RequirementStatus, SkillOrigin
from .models import PluginRequirement, RequirementRow, Requirements, SkillRequirement
from .toml_io import parse_skill_from

SYNC_FIX = "dummyindex context requirements sync"
CLI_FIX = "pip install --user dummyindex  (or: uv tool install dummyindex)"
_DISABLED_BY_DEV = "disabled by you"

_S = RequirementStatus


def check_requirements(
    project_root: Path,
    requirements: Requirements,
    *,
    claude_config_dir: Path,
    family_stamp: str | None,
    cli_version: str,
) -> tuple[RequirementRow, ...]:
    """One row per requirement. Extras in the repo never produce rows."""
    rows: list[RequirementRow] = []
    if requirements.min_version is not None:
        rows.append(_cli_row(requirements.min_version, cli_version))
    for plugin in requirements.plugins:
        rows.append(_plugin_row(project_root, claude_config_dir, plugin))
    for skill in requirements.skills:
        rows.append(
            _skill_row(
                project_root, claude_config_dir, requirements, skill, family_stamp
            )
        )
    if requirements.require_native_adapters:
        rows.extend(_equipment_rows(project_root))
    return tuple(rows)


def exit_code(rows: tuple[RequirementRow, ...]) -> int:
    """3 when any row is missing or below its version; otherwise 0."""
    bad = {_S.MISSING, _S.VERSION_MISMATCH}
    return 3 if any(row.status in bad for row in rows) else 0


def _cli_row(min_version: str, cli_version: str) -> RequirementRow:
    name = "dummyindex"
    order = compare_versions(cli_version, min_version)
    if order is VersionOrder.UNKNOWN:
        # Dev builds report "unknown"; that is not proof of a gap.
        return _row(
            RequirementKind.DUMMYINDEX,
            name,
            _S.UNKNOWN,
            f"CLI version {cli_version!r} is not a release",
        )
    if order is VersionOrder.OLDER:
        return _row(
            RequirementKind.DUMMYINDEX,
            name,
            _S.VERSION_MISMATCH,
            f"CLI {cli_version} is below min_version {min_version}",
            CLI_FIX,
        )
    return _row(RequirementKind.DUMMYINDEX, name, _S.SATISFIED)


def _plugin_row(
    project_root: Path, config_dir: Path, plugin: PluginRequirement
) -> RequirementRow:
    status, reason = _plugin_state(project_root, config_dir, plugin)
    fix = f"/plugin install {plugin.id}" if status in _BAD else ""
    return _row(RequirementKind.PLUGIN, plugin.id, status, reason, fix)


def _plugin_state(
    project_root: Path, config_dir: Path, plugin: PluginRequirement
) -> tuple[RequirementStatus, str]:
    target = plugin.id
    try:
        project = _effective_enabled(project_root, target)
        user_enabled = load_settings(config_dir / "settings.json").get("enabledPlugins")
        record = installed_plugin_record(
            target, config_dir=config_dir, project_root=project_root
        )
    except (MalformedSettingsError, PluginRegistryError) as exc:
        return _S.UNKNOWN, str(exc)

    # A dev's explicit false wins over any enable elsewhere.
    user_value = user_enabled.get(target) if isinstance(user_enabled, dict) else None
    if project is False or user_value is False:
        return _S.MISSING, _DISABLED_BY_DEV
    if project is not True and user_value is not True:
        return _S.MISSING, "not enabled"
    if record is None:
        return _S.MISSING, "not installed for this project"
    if plugin.version is None:
        return _S.SATISFIED, ""

    op, want = _split_constraint(plugin.version)
    recorded = record.get("version")
    order = compare_versions(recorded if isinstance(recorded, str) else None, want)
    if order is VersionOrder.UNKNOWN:
        return _S.UNKNOWN, f"recorded version {recorded!r} is not readable"
    ok = order is VersionOrder.EQUAL if op == "==" else order is not VersionOrder.OLDER
    if not ok:
        return (
            _S.VERSION_MISMATCH,
            f"installed {recorded} does not satisfy {plugin.version}",
        )
    return _S.SATISFIED, ""


def _skill_row(
    project_root: Path,
    config_dir: Path,
    requirements: Requirements,
    skill: SkillRequirement,
    family_stamp: str | None,
) -> RequirementRow:
    origin, plugin_id = parse_skill_from(skill.from_)
    if origin is SkillOrigin.PLUGIN:
        status, reason = _plugin_state(
            project_root, config_dir, PluginRequirement(id=plugin_id or "")
        )
        fix = f"/plugin install {plugin_id}" if status in _BAD else ""
        return _row(RequirementKind.SKILL, skill.name, status, reason, fix)
    if origin is SkillOrigin.PROJECT:
        present = any(
            (project_root / base / skill.name / "SKILL.md").is_file()
            for base in (".claude/skills", ".agents/skills")
        )
        if present:
            return _row(RequirementKind.SKILL, skill.name, _S.SATISFIED)
        return _row(
            RequirementKind.SKILL,
            skill.name,
            _S.MISSING,
            "no project skill at .claude/skills or .agents/skills",
            SYNC_FIX,
        )
    return _family_skill_row(skill.name, requirements.min_version, family_stamp)


def _family_skill_row(
    name: str, min_version: str | None, family_stamp: str | None
) -> RequirementRow:
    kind = RequirementKind.SKILL
    if family_stamp is None:
        return _row(
            kind, name, _S.MISSING, "dummyindex skill family not installed", SYNC_FIX
        )
    if min_version is None:
        return _row(kind, name, _S.SATISFIED)
    order = compare_versions(family_stamp, min_version)
    if order is VersionOrder.UNKNOWN:
        return _row(
            kind, name, _S.UNKNOWN, f"family stamp {family_stamp!r} is not a release"
        )
    if order is VersionOrder.OLDER:
        return _row(
            kind,
            name,
            _S.VERSION_MISMATCH,
            f"skill family {family_stamp} is below min_version {min_version}",
            SYNC_FIX,
        )
    return _row(kind, name, _S.SATISFIED)


def _equipment_rows(project_root: Path) -> list[RequirementRow]:
    context_dir = project_root / ".context"
    if not (context_dir / "equipment.json").is_file():
        return []
    try:
        manifest = read_manifest(context_dir)
    except EquipError as exc:
        return [_row(RequirementKind.EQUIPMENT, "equipment.json", _S.UNKNOWN, str(exc))]
    rows: list[RequirementRow] = []
    for item in manifest.items:
        # Task-scoped items expire with their proposal; they are never required.
        if item.scope is EquipmentScope.TASK:
            continue
        rel = native_adapter_path(item)
        if rel is None:
            continue
        if (project_root / rel).is_file():
            rows.append(_row(RequirementKind.EQUIPMENT, item.name, _S.SATISFIED))
        else:
            rows.append(
                _row(
                    RequirementKind.EQUIPMENT,
                    item.name,
                    _S.MISSING,
                    f"native adapter {rel.as_posix()} is absent",
                    SYNC_FIX,
                )
            )
    return rows


_BAD = frozenset({_S.MISSING, _S.VERSION_MISMATCH})


def _split_constraint(value: str) -> tuple[str, str]:
    if value.startswith(">="):
        return ">=", value[2:]
    return "==", value[2:]


def _row(
    kind: RequirementKind,
    name: str,
    status: RequirementStatus,
    reason: str = "",
    fix: str = "",
) -> RequirementRow:
    return RequirementRow(kind=kind, name=name, status=status, reason=reason, fix=fix)
