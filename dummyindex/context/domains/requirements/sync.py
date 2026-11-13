"""Repair local setup from the committed requirements manifest.

Sync only adds or restores. It never deletes extras and never overrides a
dev's explicit ``enabledPlugins: false``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dummyindex.context.claude_settings import MalformedSettingsError
from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    DefaultPlugin,
    Runner,
    WiredEntry,
    WiredKind,
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

from .models import PluginRequirement, Requirements

SKILL_FAMILY_ARGV = ("dummyindex", "install", "--scope", "user", "--skill-only")
Confirm = Callable[[str], bool]


@dataclass(frozen=True)
class SyncReport:
    adapters: tuple[str, ...] = ()
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
) -> SyncReport:
    """Restore local files, then (unless ``local_only``) install trusted and approved plugins.

    ``confirm`` is ``None`` when there is no TTY; an untrusted plugin then needs
    ``approve`` or it is skipped and listed.
    """
    adapters: list[str] = []
    kept: list[str] = []
    installed: list[str] = []
    skipped: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []

    if requirements.require_native_adapters:
        _sync_adapters(project_root, adapters, kept, errors)

    # The family is a user-scope install; it is local and runs even with local_only.
    skill_family_ran = any(skill.from_ == "dummyindex" for skill in requirements.skills)
    if skill_family_ran:
        result = runner(list(SKILL_FAMILY_ARGV), project_root)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip()
            errors.append(
                (
                    " ".join(SKILL_FAMILY_ARGV),
                    f"exit {result.returncode}: {tail[-200:]}",
                )
            )

    if not local_only:
        for plugin in requirements.plugins:
            _sync_plugin(
                project_root,
                plugin,
                approve=approve,
                confirm=confirm,
                runner=runner,
                installed=installed,
                skipped=skipped,
                errors=errors,
            )

    return SyncReport(
        adapters=tuple(adapters),
        adapters_kept=tuple(kept),
        skill_family_ran=skill_family_ran,
        installed=tuple(installed),
        skipped=tuple(skipped),
        errors=tuple(errors),
    )


def _sync_adapters(
    root: Path,
    adapters: list[str],
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
        message = write_native_adapter(
            root, item, description=adapter_description(body)
        )
        if message is None:
            adapters.append(relative.as_posix())
        else:
            kept.append(message)


def _sync_plugin(
    root: Path,
    plugin: PluginRequirement,
    *,
    approve: bool,
    confirm: Confirm | None,
    runner: Runner,
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

    try:
        if _effective_enabled(root, target) is False:
            skipped.append((target, "disabled by you"))
            return
    except (MalformedSettingsError, OSError) as exc:
        errors.append((target, str(exc)))
        return

    if not _is_trusted(marketplace, repo) and not approve:
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

    ok, err = _install_one(
        DefaultPlugin(plugin=name, marketplace=marketplace, repo=repo), root, runner
    )
    if ok:
        installed.append(target)
    else:
        errors.append((target, err or "install failed"))


def _is_trusted(marketplace: str, repo: str | None) -> bool:
    """Trust is the ``(marketplace name, repo)`` pair from code, never from config.toml."""
    if any(p.marketplace == marketplace and p.repo == repo for p in DEFAULT_PLUGINS):
        return True
    return any(
        s.trusted and s.name == marketplace and s.repo == repo
        for s in SEED_MARKETPLACES
    )
