"""Equipment deletion for GC (contract 19): ``delete_workspace(kind=EQUIPMENT)``.

Removes one generated agent/skill: body, native adapter, grounding sidecar and
manifest row, plus a same-named project skill row in ``config.toml``. The
library entry stays. Fixtures live under ``tmp_path``; no git and no ``~/.claude``
are touched because the equipment path never runs the workspace recoverability
check. Every refusal must leave the project byte-identical.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.equip.constants import SCHEMA_VERSION
from dummyindex.context.domains.equip.enums import (
    EquipmentKind,
    EquipmentScope,
    EquipmentSource,
    RequestedBy,
)
from dummyindex.context.domains.equip.generate.adapters import native_adapter_content
from dummyindex.context.domains.equip.lifecycle.hashing import content_hash
from dummyindex.context.domains.equip.lifecycle.manifest import (
    read_manifest,
    write_manifest,
)
from dummyindex.context.domains.equip.models import EquipmentItem, EquipmentManifest
from dummyindex.context.domains.gc import CandidateKind, GcTargetError, delete_workspace
from dummyindex.context.domains.gc.errors import GcPathError

pytestmark = pytest.mark.unit

BODY = "# implementer\n\nDo the task.\n"
LIBRARY_JSON = '{"entries": []}\n'
CONFIG = """# user comment, keep me
schema_version = 1

[dummyindex]

[[skills]]
name = "impl-p1"
from = "project"

[[skills]]
name = "other"
from = "dummyindex"

[equipment]
require_native_adapters = false
"""


def _seed(
    root: Path,
    name: str = "impl-p1",
    *,
    body: str = BODY,
    path: str | None = None,
    source: EquipmentSource = EquipmentSource.GENERATED,
    scope: EquipmentScope = EquipmentScope.TASK,
    task_refs: tuple[str, ...] = ("proposal:p1",),
    adapter: bool = True,
    sidecar: bool = True,
) -> EquipmentItem:
    """One generated specialist on disk, pristine unless ``body`` differs from its hash."""
    context_dir = root / ".context"
    context_dir.mkdir(parents=True, exist_ok=True)
    rel = path or f".context/equipment/{name}.md"
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=name,
        path=rel,
        source=source,
        subagent_type=name,
        version="1.0.0",
        origin_hash=content_hash(BODY),
        scope=scope,
        requested_by=RequestedBy.PROPOSAL,
        task_refs=task_refs,
    )
    _write(root / rel, body)
    if adapter and source is EquipmentSource.GENERATED:
        _write(
            root / ".claude" / "agents" / f"{name}.md",
            native_adapter_content(item),
        )
    if sidecar:
        _write(root / ".context" / "equipment" / "grounding" / f"{name}.md", "digest\n")
    write_manifest(
        context_dir, EquipmentManifest(schema_version=SCHEMA_VERSION, items=(item,))
    )
    return item


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_library_and_config(root: Path, config: str = CONFIG) -> None:
    _write(root / ".context" / "equipment" / "library" / "library.json", LIBRARY_JSON)
    _write(root / ".context" / "config.toml", config)


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every project file's bytes, minus the writer lock the guards create."""
    out: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".context/cache/"):
            continue
        out[rel] = path.read_bytes()
    return out


def _delete(root: Path, **kwargs):
    return delete_workspace(
        root / ".context", kind=CandidateKind.EQUIPMENT, slug="impl-p1", **kwargs
    )


# --- happy path


def test_yes_removes_body_adapter_sidecar_and_manifest_row(tmp_path: Path) -> None:
    _seed(tmp_path)
    _seed_library_and_config(tmp_path)

    result = _delete(tmp_path, force=False)

    assert result.deleted is True
    assert result.refused is False
    assert not (tmp_path / ".context" / "equipment" / "impl-p1.md").exists()
    assert not (tmp_path / ".claude" / "agents" / "impl-p1.md").exists()
    assert not (
        tmp_path / ".context" / "equipment" / "grounding" / "impl-p1.md"
    ).exists()
    assert read_manifest(tmp_path / ".context").items == ()


def test_library_entry_survives_so_reuse_can_restore_it(tmp_path: Path) -> None:
    _seed(tmp_path)
    _seed_library_and_config(tmp_path)

    _delete(tmp_path)

    library = tmp_path / ".context" / "equipment" / "library" / "library.json"
    assert library.read_text(encoding="utf-8") == LIBRARY_JSON


def test_project_skill_row_dropped_and_comments_kept(tmp_path: Path) -> None:
    _seed(tmp_path)
    _seed_library_and_config(tmp_path)

    _delete(tmp_path)

    config = (tmp_path / ".context" / "config.toml").read_text(encoding="utf-8")
    assert 'name = "impl-p1"' not in config
    assert "# user comment, keep me" in config
    assert 'name = "other"' in config
    assert "require_native_adapters = false" in config


def test_config_left_byte_identical_without_a_matching_project_row(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    _seed_library_and_config(
        tmp_path, CONFIG.replace('from = "project"', 'from = "dummyindex"', 1)
    )
    before = (tmp_path / ".context" / "config.toml").read_bytes()

    _delete(tmp_path)

    assert (tmp_path / ".context" / "config.toml").read_bytes() == before


# --- refusals: nothing changes


def test_user_modified_body_refused_without_force_changes_nothing(
    tmp_path: Path,
) -> None:
    _seed(tmp_path, body="# implementer, hand-edited\n")
    _seed_library_and_config(tmp_path)
    before = _snapshot(tmp_path)

    with pytest.raises(GcTargetError, match="edited since generation"):
        _delete(tmp_path)

    assert _snapshot(tmp_path) == before


def test_user_modified_body_removed_with_force(tmp_path: Path) -> None:
    _seed(tmp_path, body="# implementer, hand-edited\n")
    _seed_library_and_config(tmp_path)

    result = _delete(tmp_path, force=True)

    assert result.deleted is True
    assert not (tmp_path / ".context" / "equipment" / "impl-p1.md").exists()
    assert read_manifest(tmp_path / ".context").items == ()


def test_path_outside_allowed_roots_refused_changes_nothing(tmp_path: Path) -> None:
    _seed(tmp_path, path="src/helper.py")
    _seed_library_and_config(tmp_path)
    before = _snapshot(tmp_path)

    with pytest.raises(GcPathError):
        _delete(tmp_path, force=True)

    assert _snapshot(tmp_path) == before


def test_live_task_ref_refused_even_with_force(tmp_path: Path) -> None:
    _seed(tmp_path)
    _write(
        tmp_path / ".context" / "proposals" / "p1" / "proposal.json",
        '{"slug": "p1", "status": "in_progress"}\n',
    )
    _seed_library_and_config(tmp_path)
    before = _snapshot(tmp_path)

    with pytest.raises(GcTargetError, match="live ref"):
        _delete(tmp_path, force=True)

    assert _snapshot(tmp_path) == before


def test_vendored_item_is_not_gc_deletable(tmp_path: Path) -> None:
    _seed(tmp_path, source=EquipmentSource.VENDORED)
    _seed_library_and_config(tmp_path)
    before = _snapshot(tmp_path)

    with pytest.raises(GcTargetError, match="only generated"):
        _delete(tmp_path, force=True)

    assert _snapshot(tmp_path) == before


# --- dry-run and slug isolation


def test_dry_run_deletes_nothing_and_describes_the_plan(tmp_path: Path) -> None:
    _seed(tmp_path)
    _seed_library_and_config(tmp_path)
    before = _snapshot(tmp_path)

    result = _delete(tmp_path, dry_run=True)

    assert result.would_delete is True
    assert result.deleted is False
    assert result.reason is not None
    assert ".context/equipment/impl-p1.md" in result.reason
    assert "config.toml project skill row" in result.reason
    assert _snapshot(tmp_path) == before


def test_dry_run_still_runs_the_user_edit_guard(tmp_path: Path) -> None:
    _seed(tmp_path, body="# hand-edited\n")
    _seed_library_and_config(tmp_path)

    with pytest.raises(GcTargetError, match="edited since generation"):
        _delete(tmp_path, dry_run=True)


def test_equipment_slug_never_touches_an_audit_of_the_same_name(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    _seed_library_and_config(tmp_path)
    decoy = tmp_path / ".context" / "audits" / "impl-p1" / "report.md"
    _write(decoy, "# findings\n")

    _delete(tmp_path, force=True)

    assert decoy.read_text(encoding="utf-8") == "# findings\n"


def test_unknown_equipment_slug_is_a_no_op(tmp_path: Path) -> None:
    _seed(tmp_path, name="other-one")
    _seed_library_and_config(tmp_path)
    before = _snapshot(tmp_path)

    result = _delete(tmp_path, force=True)

    assert result.deleted is False
    assert result.refused is False
    assert result.reason == "nothing to delete"
    assert _snapshot(tmp_path) == before


def test_equipment_kind_rejects_a_path_target(tmp_path: Path) -> None:
    _seed(tmp_path)
    with pytest.raises(GcTargetError, match="--slug only"):
        delete_workspace(
            tmp_path / ".context",
            kind=CandidateKind.EQUIPMENT,
            path=str(tmp_path / ".context" / "equipment" / "impl-p1.md"),
        )
    assert (tmp_path / ".context" / "equipment" / "impl-p1.md").is_file()


# --- config.toml is never left half-written on a failed delete


def test_failed_remove_restores_config_bytes_and_keeps_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dummyindex.context.domains.equip.errors import EquipError
    from dummyindex.context.domains.gc import delete as delete_mod

    _seed(tmp_path)
    _seed_library_and_config(tmp_path)
    before_config = (tmp_path / ".context" / "config.toml").read_bytes()
    before_body = (tmp_path / ".context" / "equipment" / "impl-p1.md").read_bytes()

    def _boom(*args, **kwargs):
        raise EquipError("simulated remove failure")

    monkeypatch.setattr(delete_mod, "remove_item", _boom)

    with pytest.raises(GcTargetError, match="simulated remove failure"):
        _delete(tmp_path)

    assert (tmp_path / ".context" / "config.toml").read_bytes() == before_config
    assert (tmp_path / ".context" / "equipment" / "impl-p1.md").read_bytes() == (
        before_body
    )
    assert [i.name for i in read_manifest(tmp_path / ".context").items] == ["impl-p1"]
    assert not (tmp_path / ".context" / "config.toml.gc-restore").exists()


# --- an unreadable config.toml never blocks deleting an agent


def test_invalid_config_does_not_block_agent_delete_and_warns(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    broken = "[dummyindex\nschema_version = = 1\n"
    _seed_library_and_config(tmp_path, broken)
    before = (tmp_path / ".context" / "config.toml").read_bytes()

    dry = _delete(tmp_path, dry_run=True)
    assert dry.would_delete is True
    assert "warning:" in (dry.reason or "")
    assert "config.toml" in (dry.reason or "")

    result = _delete(tmp_path)

    assert result.deleted is True
    assert result.refused is False
    assert "warning:" in (result.reason or "")
    assert not (tmp_path / ".context" / "equipment" / "impl-p1.md").exists()
    assert not (tmp_path / ".claude" / "agents" / "impl-p1.md").exists()
    assert read_manifest(tmp_path / ".context").items == ()
    assert (tmp_path / ".context" / "config.toml").read_bytes() == before
