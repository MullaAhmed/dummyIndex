"""Optional Claude discovery pointers to the shared project capabilities."""

from __future__ import annotations

import re
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic

from ..enums import EquipmentKind, EquipmentSource
from ..lifecycle.hashing import content_hash
from ..models import GENERATED_SENTINEL, EquipmentItem

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_ADAPTER_SENTINEL = "<!-- dummyindex:generated-adapter -->"


def native_adapter_path(item: EquipmentItem) -> Path | None:
    """Only canonical generated capabilities have a native discovery pointer."""
    if (
        item.source is not EquipmentSource.GENERATED
        or not _NAME_RE.fullmatch(item.name)
        or item.path != f".context/equipment/{item.name}.md"
    ):
        return None
    if item.kind is EquipmentKind.AGENT:
        return Path(".claude/agents") / f"{item.name}.md"
    if item.kind is EquipmentKind.SKILL:
        return Path(".claude/skills") / item.name / "SKILL.md"
    return None


def native_adapter_content(item: EquipmentItem) -> str:
    """Keep workflow and policy text exclusively in the canonical file."""
    return (
        f"---\nname: {item.name}\n"
        f"description: Use the project's {item.name} capability.\n---\n"
        f"{GENERATED_SENTINEL}\n{_ADAPTER_SENTINEL}\n\n"
        f"Read `{item.path}` before acting and follow its instructions.\n"
        "The referenced file owns this capability; edit it through the "
        "equipment lifecycle.\n"
    )


def _has_symlink_parent(root: Path, relative: Path) -> bool:
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            return True
    return False


def write_native_adapter(
    root: Path,
    item: EquipmentItem,
    *,
    prior: EquipmentItem | None = None,
    dry_run: bool = False,
) -> str | None:
    """Write a pointer, preserving foreign files and edits to older equipment.

    The caller supplies ``prior`` only for an approved pristine migration.
    A matching prior hash is still required here before replacing that file.
    """
    relative = native_adapter_path(item)
    if relative is None:
        return None
    target = root / relative
    if _has_symlink_parent(root, relative) or target.is_symlink():
        return f"native adapter kept: {relative.as_posix()} (symlink)"
    expected = native_adapter_content(item)
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return f"native adapter kept: {relative.as_posix()} (unreadable)"
        if existing == expected:
            return None
        if (
            prior is None
            or prior.path != relative.as_posix()
            or prior.origin_hash is None
            or content_hash(existing) != prior.origin_hash
        ):
            return f"native adapter kept: {relative.as_posix()} (user-owned)"
    if not dry_run:
        write_text_atomic(target, expected)
    return None


def remove_native_adapter(root: Path, item: EquipmentItem) -> bool:
    """Remove only an unchanged pointer; an edited pointer belongs to the user."""
    relative = native_adapter_path(item)
    if relative is None or _has_symlink_parent(root, relative):
        return False
    target = root / relative
    if target.is_symlink():
        return False
    try:
        if target.read_text(encoding="utf-8") != native_adapter_content(item):
            return False
    except (OSError, UnicodeError):
        return False
    target.unlink()
    return True
