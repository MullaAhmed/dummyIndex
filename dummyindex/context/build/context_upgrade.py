"""Bring an existing ``.context/`` forward to the installed CLI, once and safely.

Runs as one contained pipeline: each step records its failure and the next step still
runs. The version stamp moves last and only when no step failed, so a failed run is
retried by the next one. Deterministic refresh never re-clusters, and no step deletes
a file or installs a plugin.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from dummyindex.context.build.meta import read_meta
from dummyindex.context.build.upgrade import _attempt
from dummyindex.versioning import VersionOrder, compare_versions, parse_version

if TYPE_CHECKING:
    import subprocess

    from dummyindex.context.build.enriched_refresh import RefreshResult

LOCK_REL = Path("cache") / "upgrade.lock"
LOCK_STALE_SECONDS = 600
GITIGNORE_WARNING = (
    ".claude/ is gitignored — teammates get this setup from .context/config.toml "
    "via the global dummyindex hooks"
)
# Manifest paths a write may touch; anything else is skipped and reported.
_ALLOWED_ROOTS = (
    Path(".context/equipment"),
    Path(".claude/agents"),
    Path(".claude/skills"),
)

GitRunner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class UpgradeReport:
    steps: tuple[str, ...] = ()
    changed: bool = False
    adapters_written: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    skipped_paths: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    stamp_advanced: bool = False


def is_stale(context_dir: Path, cli_version: str) -> bool:
    """True when the stored stamp is older than ``cli_version`` (or unparseable).

    Reads only ``meta.json``. A missing or unreadable meta is not stale: there is no
    index to upgrade.
    """
    stored = _stored_version(context_dir)
    if stored is None:
        return False
    order = compare_versions(stored, cli_version)
    if order is VersionOrder.OLDER:
        return True
    return order is VersionOrder.UNKNOWN and parse_version(cli_version) is not None


def upgrade_project(
    project_root: Path,
    *,
    package_version: str,
    refresh: RefreshResult | None = None,
    runner: GitRunner,
) -> UpgradeReport:
    root = Path(project_root).resolve()
    context_dir = root / ".context"
    if not (context_dir / "meta.json").is_file():
        return UpgradeReport(warnings=("no .context/meta.json: nothing to upgrade",))
    stored = _stored_version(context_dir)
    if stored is None:
        return UpgradeReport(warnings=("meta.json unreadable: nothing upgraded",))
    if compare_versions(stored, package_version) is VersionOrder.NEWER:
        return UpgradeReport(warnings=("stamp newer than CLI",))

    stale = is_stale(context_dir, package_version)
    lock = context_dir / LOCK_REL
    if not _acquire_lock(lock):
        return UpgradeReport(warnings=("upgrade in progress",))
    try:
        return _run(
            root,
            context_dir,
            package_version=package_version,
            refresh=refresh,
            runner=runner,
            stale=stale,
        )
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


def _run(
    root: Path,
    context_dir: Path,
    *,
    package_version: str,
    refresh: RefreshResult | None,
    runner: GitRunner,
    stale: bool,
) -> UpgradeReport:
    errors: list[str] = []
    warnings: list[str] = []
    skipped: list[str] = []
    adapters: list[str] = []
    steps: list[str] = []
    changed = False

    # 1. deterministic refresh (never re-clusters; the stamp is held back here).
    result = refresh
    if result is None:
        result = _attempt(
            "refresh", lambda: _deterministic_refresh(root, package_version), errors
        )
    if result is not None:
        errors.extend(f"refresh {artifact}: {err}" for artifact, err in result.failed)
        steps.append("refresh")

    # 2. config.toml (contract 8) and the legacy backfill (contract 3).
    claude_wired = bool(
        _attempt("claude-wiring", lambda: _claude_wired(root, context_dir), errors)
    )
    created = _attempt(
        "config",
        lambda: _seed_config_toml(
            context_dir, cli_version=package_version, claude_wired=claude_wired
        ),
        errors,
    )
    if created:
        steps.append("config")
        changed = True
    legacy = _attempt("legacy", lambda: _backfill_legacy(context_dir), errors)
    if legacy is not None:
        steps.append("legacy")
        backfilled, without_evidence = legacy
        changed = changed or backfilled
        warnings.extend(
            f"specialist without evidence: {name} (see dummyindex-gc)"
            for name in without_evidence
        )

    # 3. equipment: pristine bodies, grounding sidecars, native adapters.
    equipment = _attempt(
        "equipment",
        lambda: _upgrade_equipment(
            root,
            context_dir,
            claude_wired=claude_wired,
            skipped=skipped,
            adapters=adapters,
            warnings=warnings,
        ),
        errors,
    )
    if equipment is not None:
        steps.append("equipment")
        changed = changed or equipment

    # 4. managed project hooks, only where the repo already has them.
    hooks = _attempt("hooks", lambda: _refresh_hooks(root, package_version), errors)
    if hooks:
        steps.append("hooks")
        changed = True

    # 5. the gitignore warning, once: only on the run that moves the stamp.
    if stale:
        ignored = _attempt("gitignore", lambda: _is_gitignored(root, runner), errors)
        if ignored:
            warnings.append(GITIGNORE_WARNING)

    # 6. the stamp, the true last step, and only when nothing failed.
    advanced = False
    if errors:
        warnings.append("version stamp held back: a step failed; the next run retries")
    else:
        advanced = (
            _attempt(
                "stamp",
                lambda: _advance_stamp(context_dir, package_version),
                errors,
            )
            or False
        )
        if advanced:
            steps.append("stamp")
            changed = True

    return UpgradeReport(
        steps=tuple(steps),
        changed=changed,
        adapters_written=tuple(adapters),
        warnings=tuple(warnings),
        skipped_paths=tuple(skipped),
        errors=tuple(errors),
        stamp_advanced=advanced,
    )


def _deterministic_refresh(root: Path, package_version: str) -> RefreshResult:
    from dummyindex.context.build.enriched_refresh import (
        refresh_deterministic_artifacts,
    )

    return refresh_deterministic_artifacts(
        root, dummyindex_version=package_version, advance_stamp=False
    )


def _stored_version(context_dir: Path) -> str | None:
    try:
        return read_meta(context_dir / "meta.json").dummyindex_version
    except (OSError, ValueError):
        return None


def _advance_stamp(context_dir: Path, package_version: str) -> bool:
    from dummyindex.context.build.enriched_refresh import advance_version_stamp

    return advance_version_stamp(context_dir, package_version, allow_downgrade=False)


def _acquire_lock(path: Path) -> bool:
    """Take ``path`` with ``O_EXCL``; a lock older than the stale window is reclaimed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age < LOCK_STALE_SECONDS:
                return False
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
            continue
        os.close(fd)
        return True
    return False


def _contained(root: Path, rel: str) -> Path | None:
    """The resolved path when ``rel`` lies strictly inside an allowed root, else None."""
    if not rel or Path(rel).is_absolute():
        return None
    target = (root / rel).resolve()
    for base in _ALLOWED_ROOTS:
        base_abs = (root / base).resolve()
        if base_abs in target.parents:
            return target
    return None


def _read_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _is_specialist(item) -> bool:
    from dummyindex.context.domains.equip.enums import EquipmentKind, EquipmentSource

    return item.kind is EquipmentKind.AGENT and item.source is EquipmentSource.GENERATED


def _capability_values(capabilities) -> frozenset[str]:
    return frozenset(c.value if hasattr(c, "value") else str(c) for c in capabilities)


def _is_templated_specialist(item) -> bool:
    """A generated specialist whose capability has a shipped template (core agents excluded)."""
    from dummyindex.context.domains.equip.enums import EquipmentSource
    from dummyindex.context.domains.equip.generate.specialists import (
        templated_capabilities,
    )

    if item.source is not EquipmentSource.GENERATED:
        return False
    templated = _capability_values(templated_capabilities())
    return bool(_capability_values(item.capabilities) & templated)


def _lacks_evidence(item, context_dir: Path) -> bool:
    """True for an evidence-gated specialist that today's stack does not back.

    Always-on capabilities never lack evidence. ``add_specialist`` and ``proposal``
    items were asked for explicitly, so they are not reported either.
    """
    from dummyindex.context.domains.equip.enums import RequestedBy
    from dummyindex.context.domains.equip.generate import detect as equip_detect
    from dummyindex.context.domains.equip.generate.catalog import (
        _evidenced_capabilities,
    )
    from dummyindex.context.domains.equip.generate.specialists import (
        EVIDENCE_GATED_CAPABILITIES,
    )

    if item.requested_by in (RequestedBy.ADD_SPECIALIST, RequestedBy.PROPOSAL):
        return False
    gated = _capability_values(EVIDENCE_GATED_CAPABILITIES)
    wanted = _capability_values(item.capabilities) & gated
    if not wanted:
        return False
    profile = equip_detect.detect_stack(context_dir)
    evidenced = _capability_values(_evidenced_capabilities(profile))
    return not (wanted & evidenced)


def _claude_wired(root: Path, context_dir: Path) -> bool:
    from dummyindex.context.domains.config import ConfigError, read_config
    from dummyindex.context.domains.equip.generate.adapters import native_adapter_path
    from dummyindex.context.domains.equip.lifecycle.manifest import read_manifest

    try:
        config = read_config(context_dir)
    except ConfigError:
        config = None
    if config is not None and config.auto_refresh_hook:
        return True
    for item in read_manifest(context_dir).items:
        rel = native_adapter_path(item)
        if rel is not None and (root / rel).is_file():
            return True
    return False


def _seed_config_toml(
    context_dir: Path, *, cli_version: str, claude_wired: bool
) -> bool:
    """Create ``config.toml`` once from a parseable ``config.json``; never touch json."""
    from dummyindex.context.domains.config import ConfigError, read_config
    from dummyindex.context.domains.requirements import (
        seed_requirements,
        write_requirements,
    )

    if (context_dir / "config.toml").exists() or not (
        context_dir / "config.json"
    ).is_file():
        return False
    try:
        config = read_config(context_dir)
    except ConfigError:
        # Malformed config.json: create nothing and leave its bytes alone.
        return False
    if config is None:
        return False
    req = seed_requirements(
        config.wired,
        default_plugins_enabled=config.default_plugins_enabled is not False,
        cli_version=cli_version,
        claude_wired=claude_wired,
    )
    write_requirements(context_dir / "config.toml", req)
    return True


def _backfill_legacy(context_dir: Path) -> tuple[bool, tuple[str, ...]]:
    """Stamp ``requested_by=legacy`` on templated specialists; return (changed, unevidenced names)."""
    from dummyindex.context.domains.equip.enums import RequestedBy
    from dummyindex.context.domains.equip.lifecycle.manifest import (
        read_manifest,
        write_manifest,
    )

    manifest = read_manifest(context_dir)
    changed = False
    items = []
    without: list[str] = []
    for item in manifest.items:
        if not _is_templated_specialist(item):
            items.append(item)
            continue
        if item.requested_by is None:
            item = dataclasses.replace(item, requested_by=RequestedBy.LEGACY)
            changed = True
        if _lacks_evidence(item, context_dir):
            without.append(item.name)
        items.append(item)
    if changed:
        write_manifest(context_dir, dataclasses.replace(manifest, items=tuple(items)))
    return changed, tuple(without)


def _upgrade_equipment(
    root: Path,
    context_dir: Path,
    *,
    claude_wired: bool,
    skipped: list[str],
    adapters: list[str],
    warnings: list[str],
) -> bool:
    from dummyindex.context.domains.equip.generate import fresh as equip_fresh
    from dummyindex.context.domains.equip.lifecycle import status as equip_status
    from dummyindex.context.domains.equip.lifecycle.manifest import read_manifest
    from dummyindex.context.domains.equip.lifecycle.status import is_lifecycle_managed

    fresh = equip_fresh.fresh_renders(root, context_dir)
    for item in read_manifest(context_dir).items:
        if is_lifecycle_managed(item) and _contained(root, item.path) is None:
            skipped.append(item.path)
            fresh.pop(item.name, None)  # no fresh render, so refresh never writes it

    # Pristine bodies only: refresh keeps user-modified and evolved items as they are.
    changed = bool(equip_status.refresh(root, fresh_renders=fresh).refreshed)
    for item in read_manifest(context_dir).items:
        if not _is_specialist(item):
            continue
        changed = _write_sidecar(root, context_dir, item, skipped) or changed
        if claude_wired:
            changed = _write_adapter(root, item, skipped, adapters, warnings) or changed
    return changed


def _write_sidecar(root: Path, context_dir: Path, item, skipped: list[str]) -> bool:
    from dummyindex.context.domains.atomic_io import write_text_atomic
    from dummyindex.context.domains.equip.generate.grounding import (
        grounding_path,
        render_grounding,
    )

    rel = grounding_path(item.name)
    if _contained(root, rel) is None:
        skipped.append(rel)
        return False
    capability = item.capabilities[0] if item.capabilities else item.name
    text = render_grounding(context_dir, capability=capability)
    target = root / rel
    if _read_or_none(target) == text:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(target, text)
    return True


def _write_adapter(
    root: Path, item, skipped: list[str], adapters: list[str], warnings: list[str]
) -> bool:
    from dummyindex.context.domains.equip.generate.adapters import (
        adapter_description,
        native_adapter_path,
        write_native_adapter,
    )

    rel = native_adapter_path(item)
    if rel is None:
        return False
    rel_text = rel.as_posix()
    if _contained(root, rel_text) is None or _contained(root, item.path) is None:
        skipped.append(rel_text)
        return False
    body = _read_or_none(root / item.path)
    if body is None:
        return False
    before = _read_or_none(root / rel)
    # No prior: write_native_adapter replaces only pristine adapters and keeps user edits.
    message = write_native_adapter(root, item, description=adapter_description(body))
    if message:
        warnings.append(message)
    if _read_or_none(root / rel) == before:
        return False
    adapters.append(rel_text)
    return True


def _refresh_hooks(root: Path, package_version: str) -> bool:
    from dummyindex.context import hooks
    from dummyindex.context.hooks_requirements import install_requirements_hooks

    if not hooks.local_install_present(root):
        return False
    result = hooks.install(root)
    if result.errors:
        raise RuntimeError("; ".join(f"{name}: {msg}" for name, msg in result.errors))
    wrote = install_requirements_hooks(
        root / ".claude" / "settings.json", cli_version=package_version
    )
    return bool(result.installed or result.refreshed or wrote)


def _is_gitignored(root: Path, runner: GitRunner) -> bool:
    try:
        proc = runner(root, "check-ignore", "-q", ".claude/settings.json")
    except OSError:
        return False
    return proc.returncode == 0
