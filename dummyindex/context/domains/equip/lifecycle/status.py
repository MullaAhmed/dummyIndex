"""Hash-baselined lifecycle: status / refresh / reset / uninstall (spec §7).

A file's hash vs its ``origin_hash`` decides what is safe to touch (the in-body
sentinel is only a human marker). :func:`refresh` and :func:`uninstall` rewrite or
delete only PRISTINE item files; :func:`reset` restores one even if modified (the
escape hatch). Adopted items (``path==""``) and the record-only settings hook have no
baseline; the hook is removed by sentinel, never by file deletion.
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
from ..enums import EquipmentSource, ItemState
from ..errors import ResetError
from ..generate.render import set_frontmatter_version
from ..models import EquipmentItem, EquipmentManifest
from .hashing import content_hash
from .manifest import EQUIPMENT_REL, write_manifest

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
    # Names of skipped items classified INVARIANT_BROKEN — a surfaced alarm: a
    # generated tool was edited in a way that dropped a load-bearing invariant.
    # Always empty when no item carries invariants (back-compat).
    alarm_invariant_broken: tuple[str, ...] = ()


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
    """Classify a generated item against its recorded ``origin_hash``.

    Equal hash ⇒ PRISTINE, absent ⇒ MISSING, unreadable ⇒ USER_MODIFIED. A
    differing hash is user-owned; the canary refines it via ``item.invariants``:
    none ⇒ ``USER_MODIFIED``, all present ⇒ ``CUSTOMIZED``, any gone ⇒
    ``INVARIANT_BROKEN``. Callers never overwrite, re-baseline or delete any of
    the three (:func:`is_user_owned`).
    """
    target = root / item.path
    if not target.is_file():
        return ItemState.MISSING
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        # An existing unreadable file is not evidence of absence or ownership.
        return ItemState.USER_MODIFIED
    if content_hash(text) == item.origin_hash:
        return ItemState.PRISTINE
    if not item.invariants:
        return ItemState.USER_MODIFIED
    if all(inv in text for inv in item.invariants):
        return ItemState.CUSTOMIZED
    return ItemState.INVARIANT_BROKEN


def is_user_owned(state: ItemState) -> bool:
    """True when ``state`` means "the user owns this file; leave it alone".

    Covers the plain ``USER_MODIFIED`` verdict and both canary refinements
    (``CUSTOMIZED`` / ``INVARIANT_BROKEN``). The never-clobber contract (spec
    §7, D2) keys on this predicate, so ``apply`` / ``refresh`` / ``uninstall``
    skip all three identically — never overwriting, re-baselining, or deleting a
    user-owned file. PRISTINE / MISSING / ADOPTED are *not* user-owned.
    """
    return state in {
        ItemState.USER_MODIFIED,
        ItemState.CUSTOMIZED,
        ItemState.INVARIANT_BROKEN,
    }


def status(root: Path, manifest: EquipmentManifest) -> StatusReport:
    """Classify every tracked item.

    Generated + vendored items by origin-hash, marketplace items by whether
    their ``enabledPlugins`` key is still set, adopted (INSTALLED) items by
    presence: a registry pointer (``path==""``) is ADOPTED, a path-backed one
    turns MISSING when its file is gone. Also lists marketplace items with no
    usage playbook in ``grounded_in`` (wired but undocumented).
    """
    rows: list[tuple[str, ItemState, str | None]] = []
    missing_playbook: list[str] = []
    for item in manifest.items:
        if is_lifecycle_managed(item) or is_vendored_file(item):
            rows.append((item.name, classify_item(root, item), item.version))
        elif item.source == EquipmentSource.MARKETPLACE:
            rows.append((item.name, _classify_marketplace(root, item), item.version))
        elif item.source == EquipmentSource.INSTALLED:
            rows.append((item.name, _classify_adopted(root, item), item.version))
        if item.source == EquipmentSource.MARKETPLACE and not item.grounded_in:
            missing_playbook.append(item.name)
    return StatusReport(items=tuple(rows), missing_playbook=tuple(missing_playbook))


def _classify_adopted(root: Path, item: EquipmentItem) -> ItemState:
    """ADOPTED for a registry pointer or a present file; MISSING when gone."""
    if not item.path:
        return ItemState.ADOPTED
    return ItemState.ADOPTED if (root / item.path).is_file() else ItemState.MISSING


def refresh(
    root: Path,
    *,
    fresh_renders: dict[str, str],
    fresh_items: dict[str, EquipmentItem] | None = None,
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
    alarm_broken: list[str] = []

    new_items: list[EquipmentItem] = []
    metadata_changed = False
    for item in manifest.items:
        if not is_lifecycle_managed(item):
            new_items.append(item)
            continue
        state = classify_item(root, item)
        fresh = fresh_renders.get(item.name)
        # User-owned (USER_MODIFIED / CUSTOMIZED / INVARIANT_BROKEN): skip
        # forever — never re-render or re-baseline. Surface INVARIANT_BROKEN as
        # an alarm so a dropped convention does not pass silently.
        if is_user_owned(state):
            skipped_user.append(item.name)
            if state is ItemState.INVARIANT_BROKEN:
                alarm_broken.append(item.name)
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
        # PRISTINE: re-render only if the fresh render differs, compared at the
        # item's version: disk carries it in frontmatter, the raw render 1.0.0,
        # so an unnormalized compare makes every refreshed item look stale.
        if fresh is None:
            unchanged.append(item.name)
            new_items.append(item)
            continue
        from ..identity import capability_metadata

        fresh_item = (fresh_items or {}).get(item.name)
        updated_metadata = (
            capability_metadata(fresh_item) if fresh_item is not None else {}
        )
        if (
            fresh_item is not None
            and fresh_item.package_sha256 == item.package_sha256
            and fresh_item.project_binding == item.project_binding
        ):
            updated_metadata["qualification_refs"] = item.qualification_refs
        fresh_at_version = set_frontmatter_version(
            fresh, item.version or _DEFAULT_VERSION
        )
        if content_hash(fresh_at_version) == item.origin_hash:
            unchanged.append(item.name)
            updated = dataclasses.replace(item, **updated_metadata)
            metadata_changed = metadata_changed or updated != item
            new_items.append(updated)
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
                **updated_metadata,
            )
        )

    if not dry_run and (refreshed or metadata_changed):
        write_manifest(
            root / ".context", dataclasses.replace(manifest, items=tuple(new_items))
        )
    return RefreshReport(
        refreshed=tuple(refreshed),
        skipped_user_modified=tuple(skipped_user),
        skipped_missing=tuple(skipped_missing),
        skipped_evolved=tuple(skipped_evolved),
        unchanged=tuple(unchanged),
        alarm_invariant_broken=tuple(alarm_broken),
    )


def reset(
    root: Path,
    manifest: EquipmentManifest,
    name: str,
    *,
    fresh_render: str,
    fresh_item: EquipmentItem | None = None,
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
    from ..identity import capability_metadata

    rebaselined = dataclasses.replace(
        target_item,
        origin_hash=content_hash(out),
        version=bumped,
        **(capability_metadata(fresh_item) if fresh_item is not None else {}),
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
        # User-owned (incl. CUSTOMIZED / INVARIANT_BROKEN): keep the file, report it.
        if is_user_owned(state):
            skipped_user.append(item.name)
            continue
        if state is ItemState.MISSING:
            if not dry_run:
                from ..generate.adapters import remove_native_adapter

                remove_native_adapter(root, item)
            continue
        removed.append(item.name)
        if not dry_run:
            (root / item.path).unlink(missing_ok=True)
            from ..generate.adapters import remove_native_adapter

            remove_native_adapter(root, item)

    # Marketplace items: disable each plugin and drop its marketplace from the
    # settings file it was wired into (``item.path``). A full uninstall removes
    # the whole ledger, so no item can still need a shared entry. A malformed
    # settings.json is left untouched rather than clobbered.
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
