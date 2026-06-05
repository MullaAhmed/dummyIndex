"""Tests for the hash-baselined equip lifecycle (spec §7).

Origin-hash baselines decide what is safe to evolve: a generated file whose disk
hash still equals its recorded ``origin_hash`` is PRISTINE (safe to refresh); a
changed hash is USER_MODIFIED (skipped forever); an absent file is MISSING.
``refresh`` re-renders only PRISTINE-and-stale items and re-baselines them;
``reset`` restores one item; ``uninstall`` removes only our pristine files + our
settings hook + the manifest, leaving user-modified files and user hooks.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.claude_settings import install_hook_entry
from dummyindex.context.domains._io import write_text_atomic
from dummyindex.context.domains.equip import (
    EQUIPMENT_REL,
    EQUIP_SENTINEL,
    EquipmentItem,
    EquipmentManifest,
    content_hash,
    write_manifest,
)
from dummyindex.context.domains.equip.enums import (
    EquipmentKind,
    EquipmentSource,
    ItemState,
)
from dummyindex.context.domains.equip.lifecycle import (
    classify_item,
    refresh,
    reset,
    status,
    uninstall,
)


# ----- fixture helpers ------------------------------------------------------

_IMPL_REL = ".claude/agents/python-implementer.md"
_VERIFY_REL = ".claude/skills/proj-verify/SKILL.md"

_IMPL_BODY = "---\nname: python-implementer\nversion: 1.0.0\n---\n<!-- dummyindex:generated -->\nbody\n"
_VERIFY_BODY = "---\nname: proj-verify\nversion: 1.0.0\n---\n<!-- dummyindex:generated -->\nverify\n"


def _renders(_root: Path) -> dict[str, str]:
    """Fresh renders keyed by item name. Identical to the on-disk fixture, so
    a clean refresh is a no-op unless a test mutates one first."""
    return {"python-implementer": _IMPL_BODY, "proj-verify": _VERIFY_BODY}


def _item(name: str, rel: str, body: str) -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT if "agents" in rel else EquipmentKind.SKILL,
        name=name,
        path=rel,
        source=EquipmentSource.GENERATED,
        capabilities=("implement",),
        version="1.0.0",
        origin_hash=content_hash(body),
    )


def _equipped_fixture(root: Path) -> EquipmentManifest:
    """Apply a 2-item toolkit + a settings hook directly (no CLI; Phase 2)."""
    write_text_atomic(root / _IMPL_REL, _IMPL_BODY)
    write_text_atomic(root / _VERIFY_REL, _VERIFY_BODY)
    hook_body = {
        "matcher": "Write|Edit",
        "hooks": [{"type": "command", "command": f"# {EQUIP_SENTINEL}\nruff format\n"}],
    }
    install_hook_entry(
        root / ".claude" / "settings.json", "PostToolUse", hook_body, sentinel=EQUIP_SENTINEL
    )
    hook_item = EquipmentItem(
        kind=EquipmentKind.HOOK,
        name="ruff-format",
        path=".claude/settings.json",
        source=EquipmentSource.GENERATED,
        capabilities=("format",),
    )
    manifest = EquipmentManifest(
        schema_version=2,
        items=(
            _item("python-implementer", _IMPL_REL, _IMPL_BODY),
            _item("proj-verify", _VERIFY_REL, _VERIFY_BODY),
            hook_item,
        ),
    )
    write_manifest(root / ".context", manifest)
    return manifest


def _manifest_item(manifest: EquipmentManifest, name: str) -> EquipmentItem:
    return next(i for i in manifest.items if i.name == name)


# ----- classify + refresh ---------------------------------------------------


@pytest.mark.integration
def test_classify_and_refresh_respect_user_edits(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped_fixture(root)
    impl = _manifest_item(manifest, "python-implementer")
    assert classify_item(root, impl) is ItemState.PRISTINE

    target = root / _IMPL_REL
    target.write_text(target.read_text() + "\nuser tweak\n", encoding="utf-8")
    assert classify_item(root, impl) is ItemState.USER_MODIFIED

    report = refresh(root, fresh_renders=_renders(root))
    assert "python-implementer" in report.skipped_user_modified
    # the user's edit survived
    assert "user tweak" in target.read_text(encoding="utf-8")


@pytest.mark.integration
def test_classify_missing(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped_fixture(root)
    impl = _manifest_item(manifest, "python-implementer")
    (root / _IMPL_REL).unlink()
    assert classify_item(root, impl) is ItemState.MISSING


@pytest.mark.integration
def test_refresh_rerenders_pristine_stale_and_bumps(tmp_path: Path) -> None:
    root = tmp_path
    _equipped_fixture(root)
    fresh = dict(_renders(root))
    fresh["python-implementer"] = _IMPL_BODY + "\nNEW upstream line\n"
    report = refresh(root, fresh_renders=fresh)
    assert "python-implementer" in report.refreshed
    target = root / _IMPL_REL
    assert "NEW upstream line" in target.read_text(encoding="utf-8")
    # re-baselined + minor-bumped in the persisted manifest
    from dummyindex.context.domains.equip import read_manifest

    after = read_manifest(root / ".context")
    impl = _manifest_item(after, "python-implementer")
    assert impl.version == "1.1.0"
    assert classify_item(root, impl) is ItemState.PRISTINE


@pytest.mark.integration
def test_refresh_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path
    _equipped_fixture(root)
    fresh = dict(_renders(root))
    fresh["python-implementer"] = _IMPL_BODY + "\nNEW\n"
    refresh(root, fresh_renders=fresh, dry_run=True)
    assert "NEW" not in (root / _IMPL_REL).read_text(encoding="utf-8")


# ----- reset ----------------------------------------------------------------


@pytest.mark.integration
def test_reset_rebaselines(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped_fixture(root)
    target = root / _IMPL_REL
    target.write_text(target.read_text() + "\nhand edit\n", encoding="utf-8")
    item = reset(root, manifest, "python-implementer", fresh_render=_IMPL_BODY)
    # restored to the pristine render, re-baselined, minor-bumped
    assert "hand edit" not in target.read_text(encoding="utf-8")
    assert item.version == "1.1.0"
    assert classify_item(root, item) is ItemState.PRISTINE


# ----- uninstall ------------------------------------------------------------


@pytest.mark.integration
def test_uninstall_only_ours(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped_fixture(root)
    # user-modifies one of ours → it must survive
    verify = root / _VERIFY_REL
    verify.write_text(verify.read_text() + "\nmine now\n", encoding="utf-8")
    # add a user hook under a different sentinel → must survive
    install_hook_entry(
        root / ".claude" / "settings.json",
        "PostToolUse",
        {"matcher": "*", "hooks": [{"type": "command", "command": "# USER\necho hi\n"}]},
        sentinel="USER",
    )

    report = uninstall(root, manifest)

    # pristine generated file removed
    assert not (root / _IMPL_REL).exists()
    assert "python-implementer" in report.removed
    # user-modified generated file survives + reported
    assert verify.exists()
    assert "proj-verify" in report.skipped_user_modified
    # our settings hook gone, user hook preserved
    import json

    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        h["command"]
        for e in settings["hooks"]["PostToolUse"]
        for h in e["hooks"]
    ]
    assert not any(EQUIP_SENTINEL in c for c in commands)
    assert any("USER" in c for c in commands)
    # manifest deleted
    assert not (root / ".context" / EQUIPMENT_REL).exists()


@pytest.mark.integration
def test_uninstall_dry_run_keeps_everything(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped_fixture(root)
    uninstall(root, manifest, dry_run=True)
    assert (root / _IMPL_REL).exists()
    assert (root / ".context" / EQUIPMENT_REL).exists()


# ----- status ---------------------------------------------------------------


@pytest.mark.integration
def test_status_reports_states(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped_fixture(root)
    target = root / _IMPL_REL
    target.write_text(target.read_text() + "\nedit\n", encoding="utf-8")
    report = status(root, manifest)
    states = {name: state for name, state, _ver in report.items}
    assert states["python-implementer"] is ItemState.USER_MODIFIED
    assert states["proj-verify"] is ItemState.PRISTINE
