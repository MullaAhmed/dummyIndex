"""`equip remove NAME` — surgical removal of a single manifest entry.

REGRESSION (audit 2026-06-13, C2-P1): there was no way to un-adopt one entry —
`uninstall` is all-or-nothing and `reset` refuses anything not lifecycle-managed
— so users hand-edited the tool-owned equipment.json. Policy by source:
INSTALLED (adopted) drops the record only; MARKETPLACE drops the record and
un-wires settings (unless --keep-wiring / another item still needs the
marketplace); GENERATED/VENDORED file-backed items refuse without
--delete-file (never-destructive by default).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import run as run_equip
from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    SCHEMA_VERSION,
    content_hash,
    write_manifest,
)


def _adopted() -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="Frontend Developer",
        path="",
        source=EquipmentSource.INSTALLED,
        capabilities=("frontend",),
        subagent_type="Frontend Developer",
    )


def _marketplace(name: str = "pg-tuner@official") -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.PLUGIN,
        name=name,
        path=".claude/settings.json",
        source=EquipmentSource.MARKETPLACE,
        capabilities=("database",),
        marketplace="official",
        origin_repo="anthropics/claude-plugins-official",
        mechanism="native",
    )


def _generated(root: Path) -> EquipmentItem:
    rel = ".claude/agents/python-implementer.md"
    body = "---\nname: python-implementer\n---\nbody\n"
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="python-implementer",
        path=rel,
        source=EquipmentSource.GENERATED,
        capabilities=("implement",),
        version="1.0.0",
        origin_hash=content_hash(body),
    )


def _write(root: Path, *items: EquipmentItem) -> None:
    write_manifest(
        root / ".context",
        EquipmentManifest(schema_version=SCHEMA_VERSION, items=tuple(items)),
    )


def _names(root: Path) -> set[str]:
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    return {i["name"] for i in data["items"]}


def _settings(root: Path, *, marketplaces: dict | None = None, enabled: dict | None = None) -> Path:
    path = root / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {}
    if marketplaces:
        payload["extraKnownMarketplaces"] = marketplaces
    if enabled:
        payload["enabledPlugins"] = enabled
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.integration
def test_remove_adopted_drops_record_only(tmp_path: Path) -> None:
    _write(tmp_path, _adopted(), _generated(tmp_path))
    rc = run_equip(["remove", "Frontend Developer", "--root", str(tmp_path)])
    assert rc == 0
    assert "Frontend Developer" not in _names(tmp_path)
    assert "python-implementer" in _names(tmp_path)
    assert (tmp_path / ".claude" / "agents" / "python-implementer.md").is_file()


@pytest.mark.integration
def test_remove_marketplace_unwires_settings(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        marketplaces={"official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}},
        enabled={"pg-tuner@official": True},
    )
    _write(tmp_path, _marketplace())
    rc = run_equip(["remove", "pg-tuner@official", "--root", str(tmp_path)])
    assert rc == 0
    assert "pg-tuner@official" not in _names(tmp_path)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "pg-tuner@official" not in data.get("enabledPlugins", {})
    assert "official" not in data.get("extraKnownMarketplaces", {})


@pytest.mark.integration
def test_remove_marketplace_keeps_shared_marketplace(tmp_path: Path) -> None:
    # Another manifest item still references the marketplace — only the plugin
    # enable key is dropped, the marketplace entry stays.
    settings = _settings(
        tmp_path,
        marketplaces={"official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}},
        enabled={"pg-tuner@official": True, "other@official": True},
    )
    _write(tmp_path, _marketplace(), _marketplace("other@official"))
    rc = run_equip(["remove", "pg-tuner@official", "--root", str(tmp_path)])
    assert rc == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "official" in data["extraKnownMarketplaces"]
    assert data["enabledPlugins"] == {"other@official": True}
    assert _names(tmp_path) == {"other@official"}


@pytest.mark.integration
def test_remove_marketplace_keep_wiring_flag(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        marketplaces={"official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}},
        enabled={"pg-tuner@official": True},
    )
    _write(tmp_path, _marketplace())
    rc = run_equip(["remove", "pg-tuner@official", "--keep-wiring", "--root", str(tmp_path)])
    assert rc == 0
    assert "pg-tuner@official" not in _names(tmp_path)
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["enabledPlugins"] == {"pg-tuner@official": True}  # wiring untouched


@pytest.mark.integration
def test_remove_generated_refuses_without_delete_file(tmp_path: Path, capsys) -> None:
    _write(tmp_path, _generated(tmp_path))
    rc = run_equip(["remove", "python-implementer", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "--delete-file" in err
    assert "python-implementer" in _names(tmp_path)  # record kept
    assert (tmp_path / ".claude" / "agents" / "python-implementer.md").is_file()


@pytest.mark.integration
def test_remove_generated_with_delete_file(tmp_path: Path) -> None:
    _write(tmp_path, _generated(tmp_path), _adopted())
    rc = run_equip(["remove", "python-implementer", "--delete-file", "--root", str(tmp_path)])
    assert rc == 0
    assert "python-implementer" not in _names(tmp_path)
    assert not (tmp_path / ".claude" / "agents" / "python-implementer.md").exists()
    assert "Frontend Developer" in _names(tmp_path)  # untouched


@pytest.mark.integration
def test_remove_unknown_name_is_typed_error_rc1(tmp_path: Path, capsys) -> None:
    _write(tmp_path, _adopted())
    rc = run_equip(["remove", "no-such-item", "--root", str(tmp_path)])
    assert rc == 1
    assert "no-such-item" in capsys.readouterr().err


def test_remove_requires_name_rc2(tmp_path: Path) -> None:
    assert run_equip(["remove", "--root", str(tmp_path)]) == 2


def test_remove_rejects_extra_args_rc2(tmp_path: Path) -> None:
    assert run_equip(["remove", "a", "b", "--root", str(tmp_path)]) == 2
