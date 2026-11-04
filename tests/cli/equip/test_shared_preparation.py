"""Shared capability preparation and retirement preserve user-owned files."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import run
from dummyindex.context.domains.equip import (
    GENERATED_SENTINEL,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    read_manifest,
    write_manifest,
)

pytestmark = pytest.mark.integration


def _prepare(root: Path, capsys, *flags: str) -> EquipmentManifest:
    (root / ".context").mkdir(exist_ok=True)
    capsys.readouterr()
    assert run(["apply", "--root", str(root), "--json", *flags]) == 0
    json.loads(capsys.readouterr().out)
    return read_manifest(root / ".context")


def _agent(manifest: EquipmentManifest):
    return next(
        item
        for item in manifest.items
        if item.kind is EquipmentKind.AGENT and item.source is EquipmentSource.GENERATED
    )


def test_default_preparation_has_one_canonical_body_and_no_eval(tmp_path, capsys):
    manifest = _prepare(tmp_path, capsys)
    assert manifest.items
    for item in manifest.items:
        if item.source is EquipmentSource.GENERATED:
            assert item.path == f".context/equipment/{item.name}.md"
            assert (tmp_path / item.path).is_file()
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".agents").exists()
    assert not (tmp_path / ".context/equipment-evals").exists()
    assert run(["status", "--root", str(tmp_path), "--json"]) == 0
    assert "unevaluated" not in json.loads(capsys.readouterr().out)


def test_retired_suites_are_preserved_without_being_used(tmp_path, capsys):
    suite = tmp_path / ".context/equipment-evals/custom.suite.json"
    suite.parent.mkdir(parents=True)
    suite.write_bytes(b"user-owned legacy suite\r\n")
    _prepare(tmp_path, capsys)
    assert suite.read_bytes() == b"user-owned legacy suite\r\n"
    assert list(suite.parent.iterdir()) == [suite]


@pytest.mark.parametrize("verb", ["eval", "benchmark"])
def test_removed_eval_verbs_do_not_write(tmp_path, capsys, verb):
    assert run([verb, "old-tool", "--root", str(tmp_path)]) == 2
    assert not list(tmp_path.iterdir())


def test_claude_discovery_is_a_pointer_and_preserves_settings(tmp_path, capsys):
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    owned = {"custom": {"keep": True}, "enabledPlugins": {"mine@local": False}}
    settings.write_text(json.dumps(owned), encoding="utf-8")
    manifest = _prepare(tmp_path, capsys, "--platform", "claude")
    item = _agent(manifest)
    pointer = tmp_path / ".claude/agents" / f"{item.name}.md"
    text = pointer.read_text(encoding="utf-8")
    assert item.path in text
    assert len(text) < 500
    assert text != (tmp_path / item.path).read_text(encoding="utf-8")
    updated = json.loads(settings.read_text(encoding="utf-8"))
    assert updated["custom"] == owned["custom"]
    assert updated["enabledPlugins"] == owned["enabledPlugins"]


def _legacy(root: Path, capsys):
    manifest = _prepare(root, capsys)
    item = _agent(manifest)
    old = root / ".claude/agents" / f"{item.name}.md"
    old.parent.mkdir(parents=True)
    old.write_bytes((root / item.path).read_bytes())
    (root / item.path).unlink()
    legacy = dataclasses.replace(item, path=old.relative_to(root).as_posix())
    write_manifest(
        root / ".context",
        dataclasses.replace(
            manifest,
            items=tuple(legacy if i.name == item.name else i for i in manifest.items),
        ),
    )
    return legacy, item, old


def test_legacy_migration_checks_new_destination_ownership(tmp_path, capsys):
    legacy, candidate, old = _legacy(tmp_path, capsys)
    old_bytes = old.read_bytes()
    canonical = tmp_path / candidate.path
    canonical.write_text(GENERATED_SENTINEL + "\nMy custom content\n", encoding="utf-8")
    custom_bytes = canonical.read_bytes()
    manifest = _prepare(tmp_path, capsys, "--platform", "claude")
    assert next(i for i in manifest.items if i.name == legacy.name) == legacy
    assert canonical.read_bytes() == custom_bytes
    assert old.read_bytes() == old_bytes


def test_pristine_legacy_body_migrates_to_canonical_with_native_pointer(
    tmp_path, capsys
):
    legacy, candidate, old = _legacy(tmp_path, capsys)
    manifest = _prepare(tmp_path, capsys, "--platform", "claude")
    item = next(i for i in manifest.items if i.name == legacy.name)
    assert item.path == candidate.path
    assert item.path in old.read_text(encoding="utf-8")
    assert (tmp_path / item.path).is_file()


def test_default_migration_retains_native_ownership_for_later_claude_run(
    tmp_path, capsys
):
    legacy, candidate, old = _legacy(tmp_path, capsys)
    manifest = _prepare(tmp_path, capsys)
    item = next(i for i in manifest.items if i.name == legacy.name)
    assert item.path == candidate.path
    pointer_bytes = old.read_bytes()
    assert candidate.path.encode() in pointer_bytes
    _prepare(tmp_path, capsys, "--platform", "claude")
    assert old.read_bytes() == pointer_bytes
    assert run(["remove", item.name, "--delete-file", "--root", str(tmp_path)]) == 0
    assert not old.exists()


def test_edited_legacy_body_is_preserved_and_still_registered(tmp_path, capsys):
    legacy, candidate, old = _legacy(tmp_path, capsys)
    old.write_text(
        old.read_text(encoding="utf-8") + "\nOwner correction.\n", encoding="utf-8"
    )
    edited = old.read_bytes()
    manifest = _prepare(tmp_path, capsys, "--platform", "claude")
    assert next(i for i in manifest.items if i.name == legacy.name) == legacy
    assert old.read_bytes() == edited
    assert not (tmp_path / candidate.path).exists()


def test_removal_cleans_unchanged_pointer(tmp_path, capsys):
    item = _agent(_prepare(tmp_path, capsys, "--platform", "claude"))
    pointer = tmp_path / ".claude/agents" / f"{item.name}.md"
    assert run(["remove", item.name, "--delete-file", "--root", str(tmp_path)]) == 0
    assert not (tmp_path / item.path).exists()
    assert not pointer.exists()


def test_uninstall_preserves_edited_native_pointer(tmp_path, capsys):
    item = _agent(_prepare(tmp_path, capsys, "--platform", "claude"))
    pointer = tmp_path / ".claude/agents" / f"{item.name}.md"
    pointer.write_text("My own native agent.\n", encoding="utf-8")
    assert run(["uninstall", "--root", str(tmp_path)]) == 0
    assert not (tmp_path / item.path).exists()
    assert pointer.read_text(encoding="utf-8") == "My own native agent.\n"


def test_uninstall_retires_unchanged_pointer_when_body_is_missing(tmp_path, capsys):
    item = _agent(_prepare(tmp_path, capsys, "--platform", "claude"))
    pointer = tmp_path / ".claude/agents" / f"{item.name}.md"
    (tmp_path / item.path).unlink()
    assert run(["uninstall", "--root", str(tmp_path)]) == 0
    assert not pointer.exists()


def test_invalid_utf8_body_is_preserved_on_reapply(tmp_path, capsys):
    item = _agent(_prepare(tmp_path, capsys))
    target = tmp_path / item.path
    target.write_bytes(b"owner bytes\xff\xfe")
    _prepare(tmp_path, capsys)
    assert target.read_bytes() == b"owner bytes\xff\xfe"


def test_unreadable_existing_body_is_preserved(tmp_path, capsys, monkeypatch):
    item = _agent(_prepare(tmp_path, capsys))
    target = tmp_path / item.path
    target.write_text("Owner correction.\n", encoding="utf-8")
    original = target.read_bytes()
    read_text = Path.read_text

    def deny_read(path, *args, **kwargs):
        if path == target:
            raise PermissionError("owner file unavailable")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_read)
    _prepare(tmp_path, capsys)
    assert target.read_bytes() == original


def test_native_preview_lists_pointers_and_preserves_files(tmp_path, capsys):
    (tmp_path / ".context").mkdir()
    assert (
        run(
            [
                "apply",
                "--root",
                str(tmp_path),
                "--platform",
                "claude",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["native_adapters"]
    assert all(
        item["path"].startswith(".claude/") for item in payload["native_adapters"]
    )
    assert not (tmp_path / ".claude").exists()
    assert not list((tmp_path / ".context").iterdir())


def test_native_preview_includes_preserved_canonical_body(tmp_path, capsys):
    item = _agent(_prepare(tmp_path, capsys))
    target = tmp_path / item.path
    target.write_text("Owner's shared mandate.\n", encoding="utf-8")
    assert (
        run(
            [
                "apply",
                "--root",
                str(tmp_path),
                "--platform",
                "claude",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert any(p["name"] == item.name for p in preview["native_adapters"])
    _prepare(tmp_path, capsys, "--platform", "claude")
    assert item.path in (tmp_path / ".claude/agents" / f"{item.name}.md").read_text(
        encoding="utf-8"
    )


def test_default_legacy_migration_is_disclosed_in_preview(tmp_path, capsys):
    legacy, candidate, old = _legacy(tmp_path, capsys)
    original = old.read_bytes()
    assert run(["apply", "--root", str(tmp_path), "--dry-run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(plan["path"] == legacy.path for plan in payload["native_adapters"])
    assert old.read_bytes() == original
    assert not (tmp_path / candidate.path).exists()


def test_linked_manifest_parent_is_refused_before_writes(tmp_path, capsys, monkeypatch):
    context = tmp_path / ".context"
    context.mkdir()
    is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == context or is_symlink(path)
    )
    assert run(["apply", "--root", str(tmp_path)]) == 1
    assert not list(context.iterdir())


def test_native_hooks_preserve_linked_settings_parent(tmp_path, capsys, monkeypatch):
    from dummyindex.cli.equip import dispatch
    from dummyindex.context.domains.equip import StackProfile

    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings = settings_dir / "settings.json"
    settings.write_bytes(b'{"custom": true}\n')
    is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == settings_dir or is_symlink(path)
    )
    monkeypatch.setattr(
        dispatch,
        "detect_stack",
        lambda _: StackProfile(
            label="python", format_command="ruff format <changed-paths>"
        ),
    )
    _prepare(tmp_path, capsys, "--platform", "claude")
    assert settings.read_bytes() == b'{"custom": true}\n'
    assert list(settings_dir.iterdir()) == [settings]
