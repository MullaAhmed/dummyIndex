"""Tests for the patch seam (spec §7) — sanctioned, exact-once evolution.

``apply_patch`` is the CLI-sanctioned way to evolve a generated artifact: an
exact old/new string replacement (must match exactly once), written atomically,
then re-baselined (origin_hash) and patch-version-bumped so the file stays
PRISTINE afterwards. Hand edits (not via this seam) stay USER_MODIFIED.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentManifest,
    content_hash,
    read_manifest,
    write_manifest,
)
from dummyindex.context.domains.equip.enums import (
    EquipmentKind,
    EquipmentSource,
    ItemState,
)
from dummyindex.context.domains.equip.errors import PatchError
from dummyindex.context.domains.equip.lifecycle.evolve import apply_patch
from dummyindex.context.domains.equip.lifecycle.status import classify_item

_REL = ".claude/agents/python-implementer.md"
_BODY = (
    "---\nname: python-implementer\nversion: 1.0.0\n---\n"
    "<!-- dummyindex:generated -->\nYou implement changes.\n"
)


def _fixture(root: Path) -> EquipmentManifest:
    write_text_atomic(root / _REL, _BODY)
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="python-implementer",
        path=_REL,
        source=EquipmentSource.GENERATED,
        capabilities=("implement",),
        version="1.0.0",
        origin_hash=content_hash(_BODY),
    )
    manifest = EquipmentManifest(schema_version=2, items=(item,))
    write_manifest(root / ".context", manifest)
    return manifest


@pytest.mark.integration
def test_patch_exact_once_applied_and_rebaselined(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _fixture(root)
    item = apply_patch(
        root=root,
        manifest=manifest,
        name="python-implementer",
        old="You implement changes.",
        new="You implement changes carefully.",
    )
    body = (root / _REL).read_text(encoding="utf-8")
    assert "You implement changes carefully." in body
    assert item.version == "1.0.1"
    # re-baselined → still PRISTINE after a sanctioned patch
    assert classify_item(root, item) is ItemState.PRISTINE
    # manifest persisted with the bump + new hash
    after = read_manifest(root / ".context")
    persisted = next(i for i in after.items if i.name == "python-implementer")
    assert persisted.version == "1.0.1"
    assert persisted.origin_hash == content_hash(body)


@pytest.mark.integration
def test_patch_zero_matches_raises(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _fixture(root)
    with pytest.raises(PatchError):
        apply_patch(
            root=root,
            manifest=manifest,
            name="python-implementer",
            old="NOT PRESENT",
            new="x",
        )
    # file untouched
    assert (root / _REL).read_text(encoding="utf-8") == _BODY


@pytest.mark.integration
def test_patch_multiple_matches_raises(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _fixture(root)
    with pytest.raises(PatchError):
        apply_patch(
            root=root,
            manifest=manifest,
            name="python-implementer",
            old="implement",  # appears in name + body
            new="x",
        )
    assert (root / _REL).read_text(encoding="utf-8") == _BODY


@pytest.mark.integration
def test_patch_unknown_item_raises(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _fixture(root)
    with pytest.raises(PatchError):
        apply_patch(root=root, manifest=manifest, name="nope", old="a", new="b")


def test_patch_syncs_frontmatter_version(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _fixture(root)
    item = apply_patch(
        root=root,
        manifest=manifest,
        name="python-implementer",
        old="You implement changes.",
        new="You implement small, focused changes.",
    )
    assert item.version == "1.0.1"
    disk = (root / _REL).read_text(encoding="utf-8")
    assert "version: 1.0.1" in disk  # frontmatter mirrors manifest
    assert "version: 1.0.0" not in disk
    assert classify_item(root, item) is ItemState.PRISTINE
