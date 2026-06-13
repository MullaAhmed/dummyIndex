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
from dummyindex.context.domains.atomic_io import write_text_atomic
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
from dummyindex.context.domains.equip.lifecycle.status import (
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


# ----- evolved-item protection (sanctioned patches survive refresh) ---------


def test_is_evolved_detects_patch_level() -> None:
    import dataclasses

    from dummyindex.context.domains.equip import is_evolved

    base = _item("python-implementer", _IMPL_REL, _IMPL_BODY)
    assert is_evolved(base) is False                                  # 1.0.0
    assert is_evolved(dataclasses.replace(base, version="1.0.1")) is True
    assert is_evolved(dataclasses.replace(base, version="1.2.0")) is False
    assert is_evolved(dataclasses.replace(base, version=None)) is False


@pytest.mark.integration
def test_refresh_skips_evolved_items(tmp_path: Path) -> None:
    from dummyindex.context.domains.equip import apply_patch

    root = tmp_path
    manifest = _equipped_fixture(root)
    apply_patch(
        root=root, manifest=manifest, name="python-implementer",
        old="body", new="body plus learned guidance",
    )
    # Even with a genuinely different fresh template, the evolved item is kept.
    fresh = dict(_renders(root))
    fresh["python-implementer"] = _IMPL_BODY.replace("body", "totally new template")
    report = refresh(root, fresh_renders=fresh)
    assert "python-implementer" in report.skipped_evolved
    assert "body plus learned guidance" in (root / _IMPL_REL).read_text(encoding="utf-8")


@pytest.mark.integration
def test_refresh_version_normalized_staleness(tmp_path: Path) -> None:
    # A refresh bumps to 1.1.0 and writes that into the frontmatter. The same
    # template re-offered must then read as `unchanged`, not permanently stale.
    root = tmp_path
    _equipped_fixture(root)
    fresh = dict(_renders(root))
    fresh["python-implementer"] = _IMPL_BODY.replace("body", "new template body")
    first = refresh(root, fresh_renders=fresh)
    assert "python-implementer" in first.refreshed
    assert "version: 1.1.0" in (root / _IMPL_REL).read_text(encoding="utf-8")
    second = refresh(root, fresh_renders=fresh)
    assert "python-implementer" in second.unchanged


@pytest.mark.integration
def test_reset_discards_evolution_and_minor_bumps(tmp_path: Path) -> None:
    from dummyindex.context.domains.equip import apply_patch, read_manifest

    root = tmp_path
    manifest = _equipped_fixture(root)
    apply_patch(
        root=root, manifest=manifest, name="python-implementer",
        old="body", new="patched body",
    )
    manifest_after = read_manifest(root / ".context")
    item = reset(root, manifest_after, "python-implementer", fresh_render=_IMPL_BODY)
    assert item.version == "1.1.0"                       # evolution discarded marker
    disk = (root / _IMPL_REL).read_text(encoding="utf-8")
    assert "patched body" not in disk
    assert "version: 1.1.0" in disk                      # frontmatter synced
    assert classify_item(root, item) is ItemState.PRISTINE


@pytest.mark.integration
def test_wire_hooks_scrubs_legacy_unsuffixed_sentinel(tmp_path: Path) -> None:
    # An install from before per-event sentinel keying must be replaced, not
    # duplicated, when wire_hooks runs again.
    from dummyindex.context.domains.equip import wire_hooks
    from dummyindex.context.domains.equip.models import HookSpec

    sp = tmp_path / ".claude" / "settings.json"
    legacy = {
        "matcher": "Write|Edit",
        "hooks": [{"type": "command", "command": f"# {EQUIP_SENTINEL}\nruff format\n"}],
    }
    install_hook_entry(sp, "PostToolUse", legacy, sentinel=f"{EQUIP_SENTINEL}\n")
    spec = HookSpec(
        name="ruff-format", event="PostToolUse", matcher="Write|Edit",
        command=f"# {EQUIP_SENTINEL}:PostToolUse\nruff format\n",
    )
    wire_hooks(sp, (spec,))
    import json as _json
    entries = _json.loads(sp.read_text(encoding="utf-8"))["hooks"]["PostToolUse"]
    commands = [h["command"] for e in entries for h in e["hooks"]]
    assert len(commands) == 1                                  # no duplicate
    assert f"{EQUIP_SENTINEL}:PostToolUse" in commands[0]      # the new keying


# ----- adopted entries are visible in status (audit 2026-06-13, C2-P2) -------
# Status used to skip INSTALLED items entirely, so hand-deleting an adopted
# record produced byte-identical status output — the absence was invisible.


def _adopted_registry_item() -> EquipmentItem:
    from dummyindex.context.domains.equip.enums import EquipmentSource

    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="Frontend Developer",
        path="",
        source=EquipmentSource.INSTALLED,
        capabilities=("frontend",),
        subagent_type="Frontend Developer",
    )


def _adopted_project_item(rel: str = ".claude/agents/db-helper.md") -> EquipmentItem:
    from dummyindex.context.domains.equip.enums import EquipmentSource

    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="db-helper",
        path=rel,
        source=EquipmentSource.INSTALLED,
        capabilities=("database",),
        subagent_type="db-helper",
    )


@pytest.mark.unit
def test_status_reports_registry_adoption_as_adopted(tmp_path: Path) -> None:
    from dummyindex.context.domains.equip import status

    manifest = EquipmentManifest(schema_version=4, items=(_adopted_registry_item(),))
    report = status(tmp_path, manifest)
    states = {n: s for n, s, _v in report.items}
    assert states["Frontend Developer"] is ItemState.ADOPTED


@pytest.mark.unit
def test_status_reports_path_backed_adoption_present_and_missing(tmp_path: Path) -> None:
    from dummyindex.context.domains.equip import status

    item = _adopted_project_item()
    manifest = EquipmentManifest(schema_version=4, items=(item,))
    # file absent → missing
    report = status(tmp_path, manifest)
    assert {n: s for n, s, _v in report.items}["db-helper"] is ItemState.MISSING
    # file present → adopted
    f = tmp_path / item.path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("# my agent\n", encoding="utf-8")
    report = status(tmp_path, manifest)
    assert {n: s for n, s, _v in report.items}["db-helper"] is ItemState.ADOPTED


@pytest.mark.unit
def test_deleting_adopted_record_changes_status_output(tmp_path: Path) -> None:
    # The visibility guarantee: removing the record drops a row.
    from dummyindex.context.domains.equip import status

    with_item = EquipmentManifest(schema_version=4, items=(_adopted_registry_item(),))
    without = EquipmentManifest(schema_version=4, items=())
    assert len(status(tmp_path, with_item).items) == 1
    assert len(status(tmp_path, without).items) == 0


@pytest.mark.integration
def test_status_cli_json_includes_adopted_rows(tmp_path: Path, capsys) -> None:
    import json as _json

    from dummyindex.cli.equip import run as run_equip
    from dummyindex.context.domains.equip import SCHEMA_VERSION, write_manifest

    write_manifest(
        tmp_path / ".context",
        EquipmentManifest(schema_version=SCHEMA_VERSION, items=(_adopted_registry_item(),)),
    )
    capsys.readouterr()
    assert run_equip(["status", "--root", str(tmp_path), "--json"]) == 0
    payload = _json.loads(capsys.readouterr().out)
    assert payload["items"] == [
        {"name": "Frontend Developer", "state": "adopted", "version": None}
    ]


@pytest.mark.integration
def test_status_cli_empty_manifest_message_covers_all_kinds(tmp_path: Path, capsys) -> None:
    # Quick win: the empty message said 'no generated items' even though the
    # manifest tracks adopted/marketplace/vendored records too.
    from dummyindex.cli.equip import run as run_equip
    from dummyindex.context.domains.equip import SCHEMA_VERSION, write_manifest

    write_manifest(
        tmp_path / ".context",
        EquipmentManifest(schema_version=SCHEMA_VERSION, items=()),
    )
    capsys.readouterr()
    assert run_equip(["status", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "no tracked items" in out


@pytest.mark.integration
def test_read_manifest_unknown_enum_raises_equiperror_not_valueerror(
    tmp_path: Path,
) -> None:
    """Forward-compat: a manifest carrying a kind/source this version doesn't
    know (e.g. written by a newer dummyindex) must surface as EquipError — the
    error every caller already catches — not a bare ValueError that crashes the
    audit roster and every equip verb with a raw traceback."""
    import json

    from dummyindex.context.domains.equip import EquipError, read_manifest

    ctx = tmp_path / ".context"
    ctx.mkdir()
    (ctx / "equipment.json").write_text(
        json.dumps({
            "schema_version": 99,
            "items": [{
                "kind": "workflow",  # not a known EquipmentKind in this version
                "name": "future-tool",
                "path": ".claude/agents/future-tool.md",
                "source": "generated",
                "capabilities": [],
            }],
        }),
        encoding="utf-8",
    )
    with pytest.raises(EquipError):
        read_manifest(ctx)
