"""Optional Claude discovery pointers to the shared project capabilities."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic

from ..enums import EquipmentKind, EquipmentSource
from ..lifecycle.hashing import content_hash
from ..models import GENERATED_SENTINEL, EquipmentItem
from ..plugins.sourcing import split_frontmatter

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_ADAPTER_SENTINEL = "<!-- dummyindex:generated-adapter -->"
_DESCRIPTION_MAX = 300
_DESCRIPTION_PREFIX = "description: "


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


def _clean_description(raw: str) -> str:
    """One line, at most 300 characters, so the adapter frontmatter stays valid."""
    spaced = "".join(
        " " if ch in "\u2028\u2029" or unicodedata.category(ch) == "Cc" else ch for ch in raw
    )
    return " ".join(spaced.split())[:_DESCRIPTION_MAX].rstrip()


_BLOCK_INDICATORS = frozenset({">", ">-", ">+", "|", "|-", "|+"})


def _read_block(body_text: str) -> str:
    """Join the indented lines under a block-scalar ``description:`` key."""
    if body_text.startswith("﻿"):
        body_text = body_text[1:]
    lines = body_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    collected: list[str] = []
    in_block = False
    for line in lines[1:]:
        if line == "---":
            break
        if in_block:
            if line == "" or line[0] in " \t":
                collected.append(line.strip())
                continue
            break
        if line.startswith("description:"):
            in_block = True
    return " ".join(part for part in collected if part)


def adapter_description(body_text: str) -> str | None:
    """Cleaned frontmatter description of a canonical body, or None when absent."""
    parts = split_frontmatter(body_text)
    if parts is None:
        return None
    description = parts[0]
    if description in _BLOCK_INDICATORS:
        # split_frontmatter keeps only the indicator; the text lives on the next lines.
        description = _read_block(body_text)
    return _clean_description(description) or None


def _description_line(name: str, description: str | None) -> str:
    # The generic line stays unquoted so pre-fix adapters remain byte-identical.
    clean = _clean_description(description or "")
    if not clean:
        return f"{_DESCRIPTION_PREFIX}Use the project's {name} capability."
    return _DESCRIPTION_PREFIX + json.dumps(clean, ensure_ascii=True)


def _own_description(text: str) -> str | None:
    """Decode the description an adapter already carries; None for generic or unreadable."""
    for line in text.split("\n")[1:]:
        if line == "---":
            break
        if line.startswith(_DESCRIPTION_PREFIX):
            try:
                decoded = json.loads(line[len(_DESCRIPTION_PREFIX) :])
            except ValueError:
                return None
            return decoded if isinstance(decoded, str) else None
    return None


def native_adapter_content(
    item: EquipmentItem, *, description: str | None = None
) -> str:
    """Keep workflow and policy text exclusively in the canonical file."""
    return (
        f"---\nname: {item.name}\n"
        f"{_description_line(item.name, description)}\n---\n"
        f"{GENERATED_SENTINEL}\n{_ADAPTER_SENTINEL}\n\n"
        f"Read `{item.path}` before acting and follow its instructions.\n"
        "The referenced file owns this capability; edit it through the "
        "equipment lifecycle.\n"
    )


def _is_pristine(item: EquipmentItem, text: str) -> bool:
    """Structure decides ownership: any description passes when the skeleton matches."""
    return text == native_adapter_content(item, description=_own_description(text))


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
    description: str | None = None,
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
    expected = native_adapter_content(item, description=description)
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return f"native adapter kept: {relative.as_posix()} (unreadable)"
        if existing == expected:
            return None
        if not _is_pristine(item, existing) and (
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
        if not _is_pristine(item, target.read_text(encoding="utf-8")):
            return False
    except (OSError, UnicodeError):
        return False
    target.unlink()
    return True
