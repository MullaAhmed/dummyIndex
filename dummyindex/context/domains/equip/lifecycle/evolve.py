"""The patch seam (spec §7) — sanctioned, exact-once evolution of a generated tool.

Applying a patch *through the CLI* is the one way to evolve a generated artifact
without it becoming USER_MODIFIED: the old/new replacement (Hermes-style, more
token-efficient than a full re-edit) must match exactly once, is written
atomically, and the item is then re-baselined (``origin_hash``) and
patch-version-bumped so it stays PRISTINE. The build skill's post-build learning
step drafts these patches; the mechanics stay here in Python.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic

from ..errors import PatchError
from ..generate.render import set_frontmatter_version
from ..models import EquipmentItem, EquipmentManifest
from .hashing import content_hash
from .manifest import write_manifest
from .status import _bump, is_lifecycle_managed


def apply_patch(
    *,
    root: Path,
    manifest: EquipmentManifest,
    name: str,
    old: str,
    new: str,
) -> EquipmentItem:
    """Apply an exact-once ``old`` → ``new`` patch to a generated item.

    Raises :class:`PatchError` when ``name`` is not a patchable generated item,
    or when ``old`` does not occur exactly once in the file. On success: writes
    the patched content atomically, re-baselines ``origin_hash``, bumps the
    patch-level version, persists the manifest, and returns the updated item.
    """
    target_item = next((i for i in manifest.items if i.name == name), None)
    if target_item is None or not is_lifecycle_managed(target_item):
        raise PatchError(f"no patchable generated item named {name!r}")

    target = root / target_item.path
    try:
        content = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise PatchError(f"could not read {target_item.path}: {exc}") from exc

    occurrences = content.count(old)
    if occurrences != 1:
        raise PatchError(
            f"patch `old` must match exactly once in {name!r}; "
            f"found {occurrences} occurrence(s)"
        )

    bumped = _bump(target_item.version, "patch")
    # Sync the artifact's frontmatter to the bumped version in the same write —
    # the manifest is the version source of truth, the file mirrors it.
    patched = set_frontmatter_version(content.replace(old, new, 1), bumped)
    write_text_atomic(target, patched)

    updated = dataclasses.replace(
        target_item,
        origin_hash=content_hash(patched),
        version=bumped,
    )
    new_items = tuple(updated if i.name == name else i for i in manifest.items)
    write_manifest(root / ".context", dataclasses.replace(manifest, items=new_items))
    return updated
