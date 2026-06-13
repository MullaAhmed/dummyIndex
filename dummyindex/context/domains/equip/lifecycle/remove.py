"""Remove ONE manifest entry — the surgical sibling of :func:`status.uninstall`.

`uninstall` is all-or-nothing and `reset` refuses anything not lifecycle-
managed, so a single adopted/marketplace record had no sanctioned removal path
(users hand-edited the tool-owned equipment.json). Policy by source:

- **INSTALLED** (adopted, no file of ours): drop the record only.
- **MARKETPLACE**: drop the record and un-wire settings — disable the plugin
  key and drop the marketplace entry *unless another manifest item still
  references it* (or the caller passes ``keep_wiring=True``).
- **GENERATED / VENDORED file-backed**: refuse unless ``delete_file=True``
  (never-destructive by default; ``reset``/``uninstall`` are the file paths).
- A record-only hook item drops its record; the settings hook entry itself is
  left in place (``uninstall`` removes it by sentinel).

Raises :class:`RemoveError` for an unknown name, a refused file-backed item,
or a malformed settings file (we never half-remove: record kept on refusal).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from dummyindex.context.claude_plugins import disable_plugin, remove_marketplace
from dummyindex.context.claude_settings import MalformedSettingsError

from ..enums import EquipmentSource
from ..errors import RemoveError
from ..models import EquipmentItem, EquipmentManifest
from .manifest import write_manifest
from .status import is_lifecycle_managed, is_vendored_file

_SETTINGS_REL = ".claude/settings.json"


@dataclass(frozen=True)
class RemoveReport:
    """What :func:`remove_item` actually did."""

    name: str
    deleted_file: str | None = None
    disabled_plugin: bool = False
    removed_marketplace: str | None = None


def remove_item(
    root: Path,
    manifest: EquipmentManifest,
    name: str,
    *,
    delete_file: bool = False,
    keep_wiring: bool = False,
) -> RemoveReport:
    """Drop the manifest entry ``name`` and persist the new manifest."""
    item = next((i for i in manifest.items if i.name == name), None)
    if item is None:
        known = ", ".join(i.name for i in manifest.items) or "(empty manifest)"
        raise RemoveError(f"no manifest item named {name!r}; tracked: {known}")

    deleted: str | None = None
    if is_lifecycle_managed(item) or is_vendored_file(item):
        if not delete_file:
            raise RemoveError(
                f"{name!r} is a file-backed {item.source.value} item ({item.path}); "
                "pass --delete-file to remove the file too, or use "
                "`equip reset` / `equip uninstall`."
            )
        (root / item.path).unlink(missing_ok=True)
        deleted = item.path

    disabled = False
    removed_marketplace: str | None = None
    if item.source is EquipmentSource.MARKETPLACE and not keep_wiring:
        disabled, removed_marketplace = _unwire_marketplace(root, manifest, item)

    new_items = tuple(i for i in manifest.items if i.name != name)
    write_manifest(
        root / ".context", dataclasses.replace(manifest, items=new_items)
    )
    return RemoveReport(
        name=name,
        deleted_file=deleted,
        disabled_plugin=disabled,
        removed_marketplace=removed_marketplace,
    )


def _unwire_marketplace(
    root: Path, manifest: EquipmentManifest, item: EquipmentItem
) -> tuple[bool, str | None]:
    """Disable the plugin key; drop its marketplace when no other item needs it."""
    plugin, _, marketplace = item.name.partition("@")
    if not marketplace:
        return False, None
    settings_path = root / (item.path or _SETTINGS_REL)
    mkt_name = item.marketplace or marketplace
    try:
        disabled = disable_plugin(settings_path, plugin=plugin, marketplace=marketplace)
        if _marketplace_still_referenced(manifest, item, mkt_name):
            return disabled, None
        removed = remove_marketplace(settings_path, name=mkt_name)
    except MalformedSettingsError as exc:
        # Never half-remove: refuse (record kept) rather than leave wiring the
        # manifest no longer knows about. --keep-wiring is the escape hatch.
        raise RemoveError(
            f"cannot un-wire {item.name!r}: {exc} — fix the settings file or "
            "re-run with --keep-wiring to drop only the record."
        ) from exc
    return disabled, mkt_name if removed else None


def _marketplace_still_referenced(
    manifest: EquipmentManifest, removing: EquipmentItem, marketplace: str
) -> bool:
    """True when another marketplace item in the same settings file needs it."""
    return any(
        i.name != removing.name
        and i.source is EquipmentSource.MARKETPLACE
        and (i.marketplace or i.name.partition("@")[2]) == marketplace
        and (i.path or _SETTINGS_REL) == (removing.path or _SETTINGS_REL)
        for i in manifest.items
    )
