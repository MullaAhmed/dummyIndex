"""Wave 4 — lifecycle parity for vendored skills.

A vendored ``SKILL.md`` is hash-baselined exactly like a generated file, so
``classify_item`` / ``uninstall`` treat it identically (PRISTINE vs USER_MODIFIED
by hash), while ``refresh`` — which only re-renders GENERATED templates — leaves
it untouched (a vendored skill is refreshed by re-running ``install`` at a new
pinned ref, not by ``refresh``).
"""

from __future__ import annotations

from pathlib import Path

from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    EquipmentManifest,
    ItemState,
    classify_item,
    is_vendored_file,
    refresh,
    stamp_vendored,
    uninstall,
    vendored_item,
    write_manifest,
)


def _vendored_on_disk(
    root: Path, *, name: str = "code-review", content: str = "# skill body\n"
):
    item = vendored_item(
        name=f"{name}@coll",
        rel_path=f".claude/skills/{name}/SKILL.md",
        kind_skill=True,
        capabilities=("review",),
        repo="o/r",
        ref="a" * 40,
        content=content,
        marketplace="coll",
    )
    target = root / item.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(stamp_vendored(content), encoding="utf-8")
    (root / ".context").mkdir(parents=True, exist_ok=True)
    return item


def test_vendored_skill_classifies_pristine(tmp_path: Path) -> None:
    item = _vendored_on_disk(tmp_path)
    assert is_vendored_file(item)
    assert classify_item(tmp_path, item) is ItemState.PRISTINE


def test_vendored_skill_user_edit_is_user_modified(tmp_path: Path) -> None:
    item = _vendored_on_disk(tmp_path)
    (tmp_path / item.path).write_text("hand-edited\n", encoding="utf-8")
    assert classify_item(tmp_path, item) is ItemState.USER_MODIFIED


def test_uninstall_removes_pristine_vendored_skill(tmp_path: Path) -> None:
    item = _vendored_on_disk(tmp_path)
    manifest = EquipmentManifest(schema_version=SCHEMA_VERSION, items=(item,))
    report = uninstall(tmp_path, manifest)
    assert item.name in report.removed
    assert not (tmp_path / item.path).exists()


def test_uninstall_keeps_user_modified_vendored_skill(tmp_path: Path) -> None:
    item = _vendored_on_disk(tmp_path)
    (tmp_path / item.path).write_text("MY EDIT\n", encoding="utf-8")
    manifest = EquipmentManifest(schema_version=SCHEMA_VERSION, items=(item,))
    report = uninstall(tmp_path, manifest)
    assert item.name in report.skipped_user_modified
    assert (tmp_path / item.path).read_text() == "MY EDIT\n"  # never clobbered


def test_refresh_leaves_vendored_skill_untouched(tmp_path: Path) -> None:
    item = _vendored_on_disk(tmp_path)
    write_manifest(
        tmp_path / ".context",
        EquipmentManifest(schema_version=SCHEMA_VERSION, items=(item,)),
    )
    report = refresh(tmp_path, fresh_renders={})
    assert item.name not in report.refreshed
    assert (
        (tmp_path / item.path).read_text().startswith("<!-- dummyindex:installed -->")
    )
