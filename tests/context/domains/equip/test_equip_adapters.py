"""Native discovery contains references, never another capability body."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentKind,
    EquipmentSource,
)
from dummyindex.context.domains.equip.generate.adapters import (
    adapter_description,
    native_adapter_content,
    native_adapter_path,
    remove_native_adapter,
    write_native_adapter,
)
from dummyindex.context.domains.equip.lifecycle.hashing import content_hash


def _item(kind: EquipmentKind = EquipmentKind.AGENT) -> EquipmentItem:
    return EquipmentItem(
        kind=kind,
        name="project-reviewer",
        path=".context/equipment/project-reviewer.md",
        source=EquipmentSource.GENERATED,
        origin_hash=content_hash("canonical body"),
    )


@pytest.mark.unit
@pytest.mark.parametrize("kind", [EquipmentKind.AGENT, EquipmentKind.SKILL])
def test_adapter_points_at_shared_body_and_is_idempotent(tmp_path: Path, kind) -> None:
    item = _item(kind)
    assert write_native_adapter(tmp_path, item) is None
    target = tmp_path / native_adapter_path(item)
    expected = target.read_bytes()
    assert item.path in expected.decode()
    assert b"canonical body" not in expected
    assert write_native_adapter(tmp_path, item) is None
    assert target.read_bytes() == expected
    assert remove_native_adapter(tmp_path, item)
    assert not target.exists()


@pytest.mark.unit
def test_foreign_and_edited_adapters_survive_write_and_removal(tmp_path: Path) -> None:
    item = _item()
    target = tmp_path / native_adapter_path(item)
    target.parent.mkdir(parents=True)
    for content in ("user-authored", native_adapter_content(item) + "user edit\n"):
        target.write_text(content, encoding="utf-8")
        assert "user-owned" in write_native_adapter(tmp_path, item)
        assert not remove_native_adapter(tmp_path, item)
        assert target.read_text(encoding="utf-8") == content


@pytest.mark.unit
def test_invalid_utf8_native_file_is_preserved(tmp_path: Path) -> None:
    item = _item()
    target = tmp_path / native_adapter_path(item)
    target.parent.mkdir(parents=True)
    original = b"user content: \xff\xfe\n"
    target.write_bytes(original)
    assert "unreadable" in write_native_adapter(tmp_path, item)
    assert not remove_native_adapter(tmp_path, item)
    assert target.read_bytes() == original


@pytest.mark.unit
def test_native_adapter_does_not_write_through_junction_parent(
    tmp_path: Path, monkeypatch
) -> None:
    parent = tmp_path / ".claude"
    parent.mkdir()
    monkeypatch.setattr(Path, "is_junction", lambda path: path == parent, raising=False)
    assert "symlink" in write_native_adapter(tmp_path, _item())
    assert not list(parent.iterdir())


@pytest.mark.unit
def test_adapter_preview_checks_ownership_without_mutation(tmp_path: Path) -> None:
    item = _item()
    assert write_native_adapter(tmp_path, item, dry_run=True) is None
    assert not (tmp_path / ".claude").exists()
    target = tmp_path / native_adapter_path(item)
    target.parent.mkdir(parents=True)
    target.write_text("user body", encoding="utf-8")
    preview = write_native_adapter(tmp_path, item, dry_run=True)
    assert preview == write_native_adapter(tmp_path, item)
    assert "user-owned" in preview
    assert target.read_text(encoding="utf-8") == "user body"


@pytest.mark.unit
def test_pristine_legacy_migration_requires_exact_recorded_hash(tmp_path: Path) -> None:
    item = _item()
    relative = native_adapter_path(item)
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_text("legacy role body", encoding="utf-8")
    prior = dataclasses.replace(item, path=relative.as_posix())
    assert "user-owned" in write_native_adapter(tmp_path, item, prior=prior)
    prior = dataclasses.replace(prior, origin_hash=content_hash("legacy role body"))
    assert write_native_adapter(tmp_path, item, prior=prior) is None
    assert target.read_text(encoding="utf-8") == native_adapter_content(item)


@pytest.mark.unit
def test_adapter_refuses_parent_symlink_and_unsafe_names(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (tmp_path / ".claude").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    assert "symlink" in write_native_adapter(tmp_path, _item())
    assert not list(outside.iterdir())
    malicious = dataclasses.replace(_item(), name="../../escape")
    assert native_adapter_path(malicious) is None
    assert write_native_adapter(tmp_path, malicious) is None


def _frontmatter_description(text: str) -> object:
    head = text.split("---\n", 2)[1]
    line = next(ln for ln in head.splitlines() if ln.startswith("description: "))
    value = json.loads(line[len("description: ") :])
    try:
        import yaml
    except ImportError:  # PyYAML is not a dev dependency; the JSON check still runs.
        return value
    assert yaml.safe_load(head)["description"] == value
    return value


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "---\nname: x\ndescription: a: b # c 'q' -x --- y\n---\nbody",
            "a: b # c 'q' -x --- y",
        ),
        ('---\ndescription: "quoted"\n---\nbody', "quoted"),
        ("---\ndescription: - leading dash\n---\nbody", "- leading dash"),
        ("---\ndescription: " + "a" * 400 + "\n---\nbody", "a" * 300),
        ("---\ndescription: café 日本\n---\nbody", "café 日本"),
        ("---\ndescription: \n---\nbody", None),
        ("no frontmatter at all", None),
        ("---\r\ndescription: crlf body\r\n---\r\nbody", "crlf body"),
    ],
)
def test_adapter_description_sanitised_and_valid_yaml(body: str, expected) -> None:
    description = adapter_description(body)
    assert description == expected
    rendered = native_adapter_content(_item(), description=description)
    if expected is None:
        assert rendered == native_adapter_content(_item())
        return
    assert len(expected) <= 300
    assert _frontmatter_description(rendered) == expected


@pytest.mark.unit
def test_multiline_and_control_characters_collapse_to_one_line() -> None:
    from dummyindex.context.domains.equip.generate.adapters import _clean_description

    raw = "first line\n  second:\tline \u2028 with \x00 control\u2029end"
    cleaned = _clean_description(raw)
    assert cleaned == "first line second: line with control end"
    assert (
        _frontmatter_description(native_adapter_content(_item(), description=raw))
        == cleaned
    )


@pytest.mark.unit
def test_pre_fix_generic_adapter_is_replaced_when_description_arrives(
    tmp_path: Path,
) -> None:
    item = _item()
    target = tmp_path / native_adapter_path(item)
    target.parent.mkdir(parents=True)
    target.write_text(native_adapter_content(item), encoding="utf-8")
    assert write_native_adapter(tmp_path, item, description="Reviews code.") is None
    assert target.read_text(encoding="utf-8") == native_adapter_content(
        item, description="Reviews code."
    )


@pytest.mark.unit
def test_description_change_updates_pristine_adapter(tmp_path: Path) -> None:
    item = _item()
    target = tmp_path / native_adapter_path(item)
    assert write_native_adapter(tmp_path, item, description="X") is None
    assert write_native_adapter(tmp_path, item, description="Y") is None
    assert target.read_text(encoding="utf-8") == native_adapter_content(
        item, description="Y"
    )


@pytest.mark.unit
def test_crlf_adapter_counts_as_pristine(tmp_path: Path) -> None:
    item = _item()
    target = tmp_path / native_adapter_path(item)
    target.parent.mkdir(parents=True)
    crlf = native_adapter_content(item, description="X").replace("\n", "\r\n")
    target.write_bytes(crlf.encode("utf-8"))
    assert write_native_adapter(tmp_path, item, description="Y") is None
    assert target.read_text(encoding="utf-8") == native_adapter_content(
        item, description="Y"
    )


@pytest.mark.unit
def test_hand_edited_adapter_with_description_is_user_owned(tmp_path: Path) -> None:
    item = _item()
    target = tmp_path / native_adapter_path(item)
    target.parent.mkdir(parents=True)
    edited = native_adapter_content(item, description="Mine") + "extra line\n"
    target.write_text(edited, encoding="utf-8")
    assert "(user-owned)" in write_native_adapter(tmp_path, item, description="Y")
    assert not remove_native_adapter(tmp_path, item)
    assert target.read_text(encoding="utf-8") == edited


@pytest.mark.unit
def test_new_format_adapter_with_description_is_removed(tmp_path: Path) -> None:
    item = _item()
    target = tmp_path / native_adapter_path(item)
    write_native_adapter(tmp_path, item, description="Reviews: code # carefully")
    assert remove_native_adapter(tmp_path, item)
    assert not target.exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "---\nname: x\ndescription: >-\n  first line\n  second: line\n---\nbody",
            "first line second: line",
        ),
        (
            "---\ndescription: |\n  line one\n\n  line two\n---\nbody",
            "line one line two",
        ),
        (
            "---\ndescription: >-\n  folded text\nversion: 2\n---\nbody",
            "folded text",
        ),
        ("---\ndescription: >-\nversion: 2\n---\nbody", None),
        ("---\r\ndescription: >-\r\n  crlf block\r\n---\r\nbody", "crlf block"),
    ],
)
def test_block_scalar_description_is_read_in_full(body: str, expected) -> None:
    assert adapter_description(body) == expected
    if expected is not None:
        rendered = native_adapter_content(
            _item(), description=adapter_description(body)
        )
        assert _frontmatter_description(rendered) == expected
