"""Pure helpers for the VENDOR mechanism: stamp a copied file with the installed
sentinel and build its manifest item with origin + hash.

The file write itself happens at the CLI boundary (never-clobber guarded via
:func:`safety.is_safe_to_write`), exactly like generated items — this module
stays pure so it is trivially unit-tested.
"""
from __future__ import annotations

from ..constants import VENDORED_SENTINEL
from ..lifecycle.hashing import content_hash
from ..enums import EquipmentKind, EquipmentSource, InstallMechanism
from ..models import EquipmentItem


def stamp_vendored(content: str) -> str:
    """Prepend the installed sentinel as an HTML comment, idempotently."""
    if VENDORED_SENTINEL in content:
        return content
    return f"{VENDORED_SENTINEL}\n{content}"


def vendored_item(
    *,
    name: str,
    rel_path: str,
    kind_skill: bool,
    capabilities: tuple[str, ...],
    repo: str,
    ref: str | None,
    content: str,
    marketplace: str | None = None,
) -> EquipmentItem:
    """Build the manifest item for a vendored agent/skill.

    ``origin_hash`` is taken over the *stamped* content so the hash-baselined
    lifecycle (refresh/reset/uninstall) classifies it identically to a generated
    item.
    """
    stamped = stamp_vendored(content)
    return EquipmentItem(
        kind=EquipmentKind.SKILL if kind_skill else EquipmentKind.AGENT,
        name=name,
        path=rel_path,
        source=EquipmentSource.VENDORED,
        capabilities=capabilities,
        marketplace=marketplace,
        origin_repo=repo,
        origin_ref=ref,
        mechanism=InstallMechanism.VENDOR.value,
        origin_hash=content_hash(stamped),
    )
