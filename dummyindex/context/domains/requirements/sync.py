"""Repair local setup from the committed requirements manifest.

Sync only adds or restores. It never deletes extras and never overrides a
dev's explicit ``enabledPlugins: false``, in project or user settings.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dummyindex.context.claude_plugins import (
    PluginRegistryError,
    installed_plugin_record,
)
from dummyindex.context.claude_settings import MalformedSettingsError, load_settings
from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    DefaultPlugin,
    Runner,
    WiredEntry,
    WiredKind,
    _default_for_target,
    _effective_enabled,
    _install_one,
    _split_target,
    wire_default_plugins,
)
from dummyindex.context.domains.equip.enums import EquipmentScope
from dummyindex.context.domains.equip.errors import EquipError
from dummyindex.context.domains.equip.generate.adapters import (
    adapter_description,
    native_adapter_path,
    write_native_adapter,
)
from dummyindex.context.domains.equip.lifecycle.manifest import read_manifest
from dummyindex.context.domains.equip.plugins.marketplace import SEED_MARKETPLACES
from dummyindex.versioning import VersionOrder, compare_versions

from .check import _family_skill_row, _split_constraint
from .enums import RequirementStatus
from .models import PluginRequirement, Requirements

SKILL_FAMILY_ARGV = ("dummyindex", "install", "--scope", "user", "--skill-only")
Confirm = Callable[[str], bool]

# Values reach argv unchanged, so a leading "-" would read as a CLI flag.
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


@dataclass(frozen=True)
class SyncReport:
    adapters_written: tuple[str, ...] = ()
    adapters_unchanged: tuple[str, ...] = ()
    adapters_kept: tuple[str, ...] = ()
    skill_family_ran: bool = False
    installed: tuple[str, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()
    errors: tuple[tuple[str, str], ...] = ()


def sync_requirements(
    project_root: Path,
    requirements: Requirements,
    *,
    approve: bool,
    local_only: bool,
    runner: Runner,
    confirm: Confirm | None,
    claude_config_dir: Path,
    family_stamp: str | None,
) -> SyncReport:
    """Restore local files, then (unless ``local_only``) install trusted and approved plugins.

    ``confirm`` is ``None`` when there is no TTY; an untrusted plugin then needs
    ``approve`` or it is skipped and listed. ``claude_config_dir`` is the user-scope
    settings and plugin registry used for the disable and already-installed checks.
    ``family_stamp`` is the read skill-family stamp (``None`` when not installed); the
    family install runs only when it is missing or below ``min_version``.
    """
    written: list[str] = []
    unchanged: list[str] = []
    kept: list[str] = []
    installed: list[str] = []
    skipped: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []

    if requirements.require_native_adapters:
        _sync_adapters(project_root, written, unchanged, kept, errors)

    # The family is a user-scope install; it is local and runs even with local_only.
    skill_family_ran = False
    if any(skill.from_ == "dummyindex" for skill in requirements.skills):
        if _family_needs_install(requirements.min_version, family_stamp):
            skill_family_ran = True
            result = runner(list(SKILL_FAMILY_ARGV), project_root)
            if result.returncode != 0:
                tail = (result.stderr or result.stdout).strip()
                errors.append(
                    (
                        " ".join(SKILL_FAMILY_ARGV),
                        f"exit {result.returncode}: {tail[-200:]}",
                    )
                )
        else:
            skipped.append(("dummyindex skill family", "skill family current"))

    if not local_only:
        for plugin in requirements.plugins:
            _sync_plugin(
                project_root,
                plugin,
                approve=approve,
                confirm=confirm,
                runner=runner,
                claude_config_dir=claude_config_dir,
                installed=installed,
                skipped=skipped,
                errors=errors,
            )

    return SyncReport(
        adapters_written=tuple(written),
        adapters_unchanged=tuple(unchanged),
        adapters_kept=tuple(kept),
        skill_family_ran=skill_family_ran,
        installed=tuple(installed),
        skipped=tuple(skipped),
        errors=tuple(errors),
    )


def _sync_adapters(
    root: Path,
    written: list[str],
    unchanged: list[str],
    kept: list[str],
    errors: list[tuple[str, str]],
) -> None:
    context_dir = root / ".context"
    if not (context_dir / "equipment.json").is_file():
        return
    try:
        manifest = read_manifest(context_dir)
    except EquipError as exc:
        errors.append(("equipment.json", str(exc)))
        return
    for item in manifest.items:
        # Task-scoped items expire with their proposal; they never get an adapter.
        if item.scope is EquipmentScope.TASK:
            continue
        relative = native_adapter_path(item)
        if relative is None:
            continue
        try:
            body = (root / item.path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append((item.name, str(exc)))
            continue
        # Passing the body's description keeps a restored adapter identical to a
        # freshly generated one; None would rewrite it to the generic line.
        target = root / relative
        before = _read_or_none(target)
        message = write_native_adapter(
            root, item, description=adapter_description(body)
        )
        if message is not None:
            kept.append(message)
        elif _read_or_none(target) != before:
            written.append(relative.as_posix())
        else:
            unchanged.append(relative.as_posix())


def _family_needs_install(min_version: str | None, family_stamp: str | None) -> bool:
    """Same verdict as check.py's family row: anything but satisfied means install."""
    row = _family_skill_row("dummyindex", min_version, family_stamp)
    return row.status is not RequirementStatus.SATISFIED


def _read_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _sync_plugin(
    root: Path,
    plugin: PluginRequirement,
    *,
    approve: bool,
    confirm: Confirm | None,
    runner: Runner,
    claude_config_dir: Path,
    installed: list[str],
    skipped: list[tuple[str, str]],
    errors: list[tuple[str, str]],
) -> None:
    target = plugin.id
    parts = _split_target(target)
    if parts is None:
        skipped.append((target, "not a <plugin>@<marketplace> target"))
        return
    name, marketplace = parts
    repo = dict(plugin.extra).get("repo")
    if repo is not None and not isinstance(repo, str):
        skipped.append((target, "repo must be a string"))
        return
    if not _NAME_RE.match(name) or not _NAME_RE.match(marketplace):
        skipped.append((target, "unsafe plugin or marketplace name"))
        return

    # A toml entry seeded without a repo means the reviewed built-in's repo.
    default = _default_for_target(target)
    if default is not None and repo is None:
        repo = default.repo
    if repo is not None and not _REPO_RE.match(repo):
        skipped.append((target, "repo must be owner/name"))
        return
    # Even with --yes, a reviewed id must not be declared while its CLI source is swapped.
    if default is not None and repo != default.repo:
        skipped.append((target, "repo differs from reviewed default"))
        return

    try:
        project_state = _effective_enabled(root, target)
        user_value = _user_enabled(claude_config_dir, target)
    except (MalformedSettingsError, OSError) as exc:
        errors.append((target, str(exc)))
        return

    if project_state is False or user_value is False:
        skipped.append((target, "disabled by you"))
        return
    record = _installed_record(claude_config_dir, target, root)
    if (
        record is not None
        and (project_state is True or user_value is True)
        and _version_satisfied(record, plugin.version)
    ):
        skipped.append((target, "already installed and enabled"))
        return

    trusted = _is_trusted(marketplace, repo)
    if not trusted and not approve:
        if confirm is None:
            skipped.append((target, "untrusted: no TTY and no --yes"))
            return
        if not confirm(f"Install untrusted plugin {target}? [y/N] "):
            skipped.append((target, "untrusted: declined"))
            return

    declared = wire_default_plugins(
        (WiredEntry(kind=WiredKind.PLUGIN, target=target),), root, enabled=True
    )
    if declared.errors:
        errors.extend(declared.errors)
        return
    if declared.needs_user:
        skipped.extend(declared.needs_user)
        return

    install_as = (
        default
        if default is not None and repo == default.repo
        else DefaultPlugin(plugin=name, marketplace=marketplace, repo=repo)
    )
    ok, err = _install_one(install_as, root, runner)
    if ok:
        installed.append(target)
    else:
        errors.append((target, err or "install failed"))


def _user_enabled(config_dir: Path, target: str) -> bool | None:
    enabled = load_settings(config_dir / "settings.json").get("enabledPlugins")
    value = enabled.get(target) if isinstance(enabled, dict) else None
    return value if isinstance(value, bool) else None


def _installed_record(config_dir: Path, target: str, root: Path) -> dict | None:
    """An unreadable registry counts as no record, so sync installs as if absent."""
    try:
        return installed_plugin_record(target, config_dir=config_dir, project_root=root)
    except PluginRegistryError:
        return None


def _version_satisfied(record: dict, constraint: str | None) -> bool:
    """Same rule as check.py's plugin row: an unparseable version does not satisfy."""
    if constraint is None:
        return True
    op, want = _split_constraint(constraint)
    recorded = record.get("version")
    order = compare_versions(recorded if isinstance(recorded, str) else None, want)
    if order is VersionOrder.UNKNOWN:
        return False
    return (
        order is VersionOrder.EQUAL if op == "==" else order is not VersionOrder.OLDER
    )


def _is_trusted(marketplace: str, repo: str | None) -> bool:
    """Trust is the ``(marketplace name, repo)`` pair from code, never from config.toml."""
    if any(p.marketplace == marketplace and p.repo == repo for p in DEFAULT_PLUGINS):
        return True
    return any(
        s.trusted and s.name == marketplace and s.repo == repo
        for s in SEED_MARKETPLACES
    )
