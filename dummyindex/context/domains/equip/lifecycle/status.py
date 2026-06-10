"""Hash-baselined lifecycle: status / refresh / reset / uninstall (spec §7).

Every generated, file-backed item carries an ``origin_hash`` baseline. The
lifecycle compares the file's current hash to that baseline to decide what is
safe to touch:

- :func:`classify_item` — PRISTINE (hash matches) / USER_MODIFIED (differs) /
  MISSING (absent). The hash is the authority; the in-body sentinel is only a
  human marker.
- :func:`status` — classify every generated item; report ``(name, state,
  version)``.
- :func:`refresh` — re-render only PRISTINE items whose fresh render differs,
  re-baseline + minor-bump them; USER_MODIFIED is skipped forever.
- :func:`reset` — restore one item to its fresh (pristine) render, re-baseline +
  minor-bump (the explicit escape hatch).
- :func:`uninstall` — delete PRISTINE generated files + our settings hook
  entries + the manifest; USER_MODIFIED files are kept and reported.

Adopted items (``path==""``) and the record-only hook item
(``path==".claude/settings.json"``) carry no origin-hash baseline and are
excluded from every disk operation here — the hook is removed via
:func:`remove_hook_entries`, never file deletion.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from dummyindex.context.claude_plugins import disable_plugin, remove_marketplace
from dummyindex.context.claude_settings import (
    MalformedSettingsError,
    load_settings,
    remove_hook_entries,
)
from dummyindex.context.domains.atomic_io import write_text_atomic

from ..constants import EQUIP_SENTINEL
from .hashing import content_hash
from ..enums import EquipmentSource, ItemState
from ..errors import ResetError
from .manifest import EQUIPMENT_REL, write_manifest
from ..models import EquipmentItem, EquipmentManifest
from ..generate.render import set_frontmatter_version

_SETTINGS_REL = ".claude/settings.json"
_DEFAULT_VERSION = "1.0.0"


@dataclass(frozen=True)
class StatusReport:
    items: tuple[tuple[str, ItemState, str | None], ...] = ()
    missing_playbook: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshReport:
    refreshed: tuple[str, ...] = ()
    skipped_user_modified: tuple[str, ...] = ()
    skipped_missing: tuple[str, ...] = ()
    skipped_evolved: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()


@dataclass(frozen=True)
class UninstallReport:
    removed: tuple[str, ...] = ()
    skipped_user_modified: tuple[str, ...] = ()
    removed_hook_events: tuple[str, ...] = ()


def is_lifecycle_managed(item: EquipmentItem) -> bool:
    """True when ``item`` is a generated, file-backed, hash-baselined artifact.

    Excludes adopted items (``path==""``), the record-only settings hook item,
    and anything without an ``origin_hash`` — none of which the disk-touching
    lifecycle operations may act on.
    """
    return (
        item.source == EquipmentSource.GENERATED
        and bool(item.path)
        and item.path != _SETTINGS_REL
        and item.origin_hash is not None
    )


def is_vendored_file(item: EquipmentItem) -> bool:
    """True when ``item`` is a vendored, file-backed, hash-baselined copy.

    Vendored agents/skills classify exactly like generated items (origin-hash vs
    disk), so the file-touching lifecycle treats them identically — only the
    source differs.
    """
    return (
        item.source == EquipmentSource.VENDORED
        and bool(item.path)
        and item.path != _SETTINGS_REL
        and item.origin_hash is not None
    )


def _classify_marketplace(root: Path, item: EquipmentItem) -> ItemState:
    """A MARKETPLACE item is PRISTINE when its ``enabledPlugins`` key is still
    true in the settings file it was wired into (``item.path``), else MISSING. A
    malformed settings.json reads as MISSING (we never parse it as enabled)."""
    try:
        settings = load_settings(root / (item.path or _SETTINGS_REL))
    except MalformedSettingsError:
        return ItemState.MISSING
    enabled = settings.get("enabledPlugins")
    if isinstance(enabled, dict) and enabled.get(item.name) is True:
        return ItemState.PRISTINE
    return ItemState.MISSING


def is_evolved(item: EquipmentItem) -> bool:
    """True when ``item`` carries sanctioned patch-evolution (patch-level > 0).

    A patched item is PRISTINE by hash (the patch re-baselined it) yet its
    content deliberately differs from a fresh template render — regenerating it
    would wipe the evolution. ``apply``/``refresh`` keep evolved items; only the
    explicit ``reset`` escape hatch discards evolution.
    """
    if not item.version:
        return False
    parts = item.version.split(".")
    try:
        return int(parts[2]) > 0
    except (IndexError, ValueError):
        return False


def classify_item(root: Path, item: EquipmentItem) -> ItemState:
    """Classify a generated item against its recorded ``origin_hash``."""
    target = root / item.path
    if not target.is_file():
        return ItemState.MISSING
    try:
        disk = content_hash(target.read_text(encoding="utf-8"))
    except OSError:
        return ItemState.MISSING
    return ItemState.PRISTINE if disk == item.origin_hash else ItemState.USER_MODIFIED


def status(root: Path, manifest: EquipmentManifest) -> StatusReport:
    """Classify every tracked item: generated + vendored by origin-hash, and
    marketplace items by whether their ``enabledPlugins`` key is still set.
    Also flag plugin items (marketplace/vendored) that carry no usage playbook
    in ``grounded_in`` — they are wired but undocumented."""
    rows: list[tuple[str, ItemState, str | None]] = []
    missing_playbook: list[str] = []
    for item in manifest.items:
        if is_lifecycle_managed(item) or is_vendored_file(item):
            rows.append((item.name, classify_item(root, item), item.version))
        elif item.source == EquipmentSource.MARKETPLACE:
            rows.append((item.name, _classify_marketplace(root, item), item.version))
        if (
            item.source in (EquipmentSource.MARKETPLACE, EquipmentSource.VENDORED)
            and not item.grounded_in
        ):
            missing_playbook.append(item.name)
    return StatusReport(items=tuple(rows), missing_playbook=tuple(missing_playbook))


def refresh(
    root: Path,
    *,
    fresh_renders: dict[str, str],
    dry_run: bool = False,
) -> RefreshReport:
    """Re-render PRISTINE-and-stale items; re-baseline + minor-bump them.

    Reads the manifest from ``root/.context``. USER_MODIFIED items are skipped
    forever; MISSING items are reported but not re-created. ``dry_run`` reports
    the same decisions without writing files or the manifest.
    """
    from .manifest import read_manifest

    manifest = read_manifest(root / ".context")
    refreshed: list[str] = []
    skipped_user: list[str] = []
    skipped_missing: list[str] = []
    skipped_evolved: list[str] = []
    unchanged: list[str] = []

    new_items: list[EquipmentItem] = []
    for item in manifest.items:
        if not is_lifecycle_managed(item):
            new_items.append(item)
            continue
        state = classify_item(root, item)
        fresh = fresh_renders.get(item.name)
        if state is ItemState.USER_MODIFIED:
            skipped_user.append(item.name)
            new_items.append(item)
            continue
        if state is ItemState.MISSING:
            skipped_missing.append(item.name)
            new_items.append(item)
            continue
        # PRISTINE-but-evolved: content intentionally differs from the template
        # (sanctioned patches) — regenerating would wipe the evolution. Keep.
        if is_evolved(item):
            skipped_evolved.append(item.name)
            new_items.append(item)
            continue
        # PRISTINE: re-render only if the fresh render actually differs.
        # Compare version-normalized — the disk content carries the item's
        # current version in its frontmatter, the raw template render carries
        # 1.0.0; without normalizing, every previously-refreshed item would
        # look permanently stale.
        if fresh is None:
            unchanged.append(item.name)
            new_items.append(item)
            continue
        fresh_at_version = set_frontmatter_version(fresh, item.version or _DEFAULT_VERSION)
        if content_hash(fresh_at_version) == item.origin_hash:
            unchanged.append(item.name)
            new_items.append(item)
            continue
        refreshed.append(item.name)
        if dry_run:
            new_items.append(item)
            continue
        bumped = _bump(item.version, "minor")
        out = set_frontmatter_version(fresh, bumped)
        write_text_atomic(root / item.path, out)
        new_items.append(
            dataclasses.replace(
                item,
                origin_hash=content_hash(out),
                version=bumped,
            )
        )

    if not dry_run and refreshed:
        write_manifest(root / ".context", dataclasses.replace(manifest, items=tuple(new_items)))
    return RefreshReport(
        refreshed=tuple(refreshed),
        skipped_user_modified=tuple(skipped_user),
        skipped_missing=tuple(skipped_missing),
        skipped_evolved=tuple(skipped_evolved),
        unchanged=tuple(unchanged),
    )


def reset(
    root: Path,
    manifest: EquipmentManifest,
    name: str,
    *,
    fresh_render: str,
) -> EquipmentItem:
    """Restore one item to its pristine render, re-baseline + minor-bump.

    The explicit escape hatch: overwrites even a USER_MODIFIED file. Returns the
    re-baselined item and persists the updated manifest.
    """
    target_item = next((i for i in manifest.items if i.name == name), None)
    if target_item is None or not is_lifecycle_managed(target_item):
        raise ResetError(f"no resettable generated item named {name!r}")

    bumped = _bump(target_item.version, "minor")
    out = set_frontmatter_version(fresh_render, bumped)
    write_text_atomic(root / target_item.path, out)
    rebaselined = dataclasses.replace(
        target_item,
        origin_hash=content_hash(out),
        version=bumped,
    )
    new_items = tuple(rebaselined if i.name == name else i for i in manifest.items)
    write_manifest(root / ".context", dataclasses.replace(manifest, items=new_items))
    return rebaselined


def uninstall(
    root: Path,
    manifest: EquipmentManifest,
    *,
    dry_run: bool = False,
) -> UninstallReport:
    """Remove PRISTINE generated files + our settings hook + the manifest.

    USER_MODIFIED files are kept and reported; MISSING ones are silently
    skipped. The settings hook is removed by sentinel (never file deletion).
    """
    removed: list[str] = []
    skipped_user: list[str] = []

    # File-backed items (generated + vendored): remove PRISTINE, keep USER_MODIFIED.
    for item in manifest.items:
        if not (is_lifecycle_managed(item) or is_vendored_file(item)):
            continue
        state = classify_item(root, item)
        if state is ItemState.USER_MODIFIED:
            skipped_user.append(item.name)
            continue
        if state is ItemState.MISSING:
            continue
        removed.append(item.name)
        if not dry_run:
            (root / item.path).unlink(missing_ok=True)

    # Marketplace items: disable each plugin + drop every referenced marketplace
    # from the settings file it was wired into (``item.path``; scope-aware — a
    # full uninstall removes the whole ledger, so no other item can still need a
    # shared marketplace entry). A malformed settings.json is left untouched
    # rather than clobbered.
    to_remove: dict[Path, set[str]] = {}
    for item in manifest.items:
        if item.source != EquipmentSource.MARKETPLACE:
            continue
        removed.append(item.name)
        plugin, _, mkt = item.name.partition("@")
        if dry_run or not mkt:
            continue
        item_settings = root / (item.path or _SETTINGS_REL)
        try:
            disable_plugin(item_settings, plugin=plugin, marketplace=mkt)
        except MalformedSettingsError:
            continue
        to_remove.setdefault(item_settings, set()).add(mkt)

    removed_events: tuple[str, ...] = ()
    if not dry_run:
        for path, mkts in to_remove.items():
            for mkt in mkts:
                try:
                    remove_marketplace(path, name=mkt)
                except MalformedSettingsError:
                    pass
        removed_events = tuple(
            remove_hook_entries(root / _SETTINGS_REL, sentinel=EQUIP_SENTINEL)
        )
        (root / ".context" / EQUIPMENT_REL).unlink(missing_ok=True)

    return UninstallReport(
        removed=tuple(removed),
        skipped_user_modified=tuple(skipped_user),
        removed_hook_events=removed_events,
    )


def _bump(version: str | None, level: str) -> str:
    """Bump a ``MAJOR.MINOR.PATCH`` string at ``level`` ("minor" | "patch").

    A missing/malformed version starts from ``1.0.0``. Minor resets patch to 0;
    patch leaves major/minor. Shared by :func:`refresh`/:func:`reset` (minor)
    and the patch seam (:mod:`.evolve`, patch).
    """
    base = version or _DEFAULT_VERSION
    parts = base.split(".")
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except (IndexError, ValueError):
        major, minor, patch = 1, 0, 0
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    # Programmer assertion, not a domain condition — `level` is never user input.
    raise AssertionError(f"unknown bump level: {level!r}")
