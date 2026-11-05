import json
from dataclasses import replace
from pathlib import Path

import pytest

from dummyindex.cli.equip import run as run_equip
from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentManifest,
    capability_identity,
    read_manifest,
    write_manifest,
)
from dummyindex.context.domains.equip.identity import capability_metadata
from dummyindex.context.domains.equip.lifecycle.status import refresh, reset


def equip(root: Path):
    context = root / ".context"
    (context / "map").mkdir(parents=True)
    write_text_atomic(
        context / "map/files.json",
        json.dumps({"files": [{"path": "app.py", "language": "python"}]}),
    )
    write_text_atomic(
        root / "pyproject.toml", "[tool.ruff]\ndependencies = ['pytest']\n"
    )
    assert run_equip(["apply", "--root", str(root)]) == 0
    return next(
        item for item in read_manifest(context).items if "reviewer" in item.name
    )


def test_package_identity_is_shared_across_projects_and_task_bindings(tmp_path):
    first_root, second_root = tmp_path / "one", tmp_path / "two"
    first, second = equip(first_root), equip(second_root)
    assert first.name != second.name
    assert first.path != second.path
    assert first.project_binding["project"] == "one"
    assert second.project_binding["project"] == "two"
    for key in ("capability_id", "package_version", "package_source", "package_sha256"):
        assert getattr(first, key) == getattr(second, key)
    assert first.required_tools == ("pytest", "ruff")
    assert "review" in first.triggers
    assert EquipmentItem.from_dict(first.to_dict()) == first
    for root, item in ((first_root, first), (second_root, second)):
        bound = capability_identity(item, root, qualify_body=True)
        assert bound["id"] == first.capability_id
        assert bound["body_verified"] is True
        assert (root / item.path).read_bytes()
        body = (root / item.path).read_text(encoding="utf-8")
        assert ".context/proposals/" not in body
        assert not (root / ".claude").exists()
        # Two task selections use the same body without minting task-specific copies.
        assert capability_identity(item, root) == bound


def test_actual_body_change_is_reported_and_cannot_qualify(tmp_path):
    item = equip(tmp_path / "project")
    root = tmp_path / "project"
    before = capability_identity(item, root, qualify_body=True)
    write_text_atomic(root / item.path, "changed guidance")
    changed = capability_identity(item, root)
    assert changed["sha256"] != before["sha256"]
    assert changed["body_verified"] is False
    with pytest.raises(ValueError, match="baseline"):
        capability_identity(item, root, qualify_body=True)
    with pytest.raises(ValueError, match="escapes"):
        capability_identity(replace(item, path="../outside.md"), root)


def test_refresh_and_reset_bind_the_package_that_rendered_the_body(tmp_path):
    root = tmp_path / "project"
    item = equip(root)
    body = (root / item.path).read_text(encoding="utf-8")
    qualified = replace(item, qualification_refs=(".context/memory/evidence.jsonl#e1",))
    write_manifest(
        root / ".context", EquipmentManifest(schema_version=4, items=(qualified,))
    )
    updated = replace(item, package_version="new-source", package_sha256="a" * 64)
    report = refresh(
        root, fresh_renders={item.name: body}, fresh_items={item.name: updated}
    )
    assert report.refreshed == ()  # metadata can update without rewriting the body
    current = read_manifest(root / ".context").items[0]
    assert current.package_sha256 == "a" * 64
    assert current.qualification_refs == ()
    assert current.origin_hash == item.origin_hash
    assert capability_identity(current, root, qualify_body=True)["body_verified"]
    newer = replace(updated, package_version="next", package_sha256="b" * 64)
    reset_item = reset(
        root,
        read_manifest(root / ".context"),
        item.name,
        fresh_render=body,
        fresh_item=newer,
    )
    assert capability_metadata(reset_item) == capability_metadata(newer)
    assert (
        capability_identity(reset_item, root, qualify_body=True)["package_version"]
        == "next"
    )


def test_old_manifest_has_no_invented_package_claim():
    item = EquipmentItem.from_dict(
        dict(kind="agent", name="local", path="agent.md", source="generated")
    )
    assert item.capability_id is None
    assert item.project_binding == {}
    assert "capability_id" not in item.to_dict()


def test_crlf_legacy_body_verifies_baseline_but_reports_actual_loaded_bytes(tmp_path):
    import hashlib

    root = tmp_path / "project"
    item = equip(root)
    target = root / item.path
    original = target.read_bytes()
    assert (
        b"\r\n" not in original
    )  # new generation uses the shared byte-faithful writer
    crlf = original.replace(b"\n", b"\r\n")
    target.write_bytes(crlf)
    loaded = capability_identity(item, root, qualify_body=True)
    assert loaded["sha256"] == hashlib.sha256(crlf).hexdigest()
    assert loaded["sha256"] != item.origin_hash.removeprefix("sha256:")
    assert loaded["body_verified"]
