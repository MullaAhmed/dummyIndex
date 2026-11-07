"""`equip reuse` + lesson-gated library storing from apply/patch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import run
from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    write_manifest,
)
from dummyindex.context.domains.equip.lifecycle import library

pytestmark = pytest.mark.integration

CID = "local/api-dev"
LESSON = {
    "cue": "api change",
    "lesson": "run schema check",
    "evidence": "pr-12",
    "confidence": "high",
}
REL = ".claude/agents/api-dev.md"


def _item() -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="api-dev",
        path=REL,
        source=EquipmentSource.GENERATED,
        grounded_in=("src/a.py",),
        capability_id=CID,
    )


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    write_manifest(
        tmp_path / ".context", EquipmentManifest(schema_version=4, items=(_item(),))
    )
    library.store(tmp_path, _item(), "BODY\n", LESSON)
    return tmp_path


def _reuse(root: Path, *extra: str) -> int:
    return run(["reuse", CID, "--root", str(root), *extra])


def test_reuse_copies_body_ok(proj: Path, capsys) -> None:
    assert _reuse(proj) == 0
    assert (proj / REL).read_text(encoding="utf-8") == "BODY\n"
    assert "status=ok" in capsys.readouterr().out


def test_needs_reverify_after_grounding_change(proj: Path, capsys) -> None:
    (proj / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert _reuse(proj) == 0
    assert "status=needs-reverify" in capsys.readouterr().out


def test_refuses_locally_edited_target_without_force(proj: Path, capsys) -> None:
    target = proj / REL
    target.parent.mkdir(parents=True)
    target.write_text("LOCAL EDIT\n", encoding="utf-8")
    assert _reuse(proj) != 0
    assert "edited locally" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "LOCAL EDIT\n"
    assert _reuse(proj, "--force") == 0
    assert target.read_text(encoding="utf-8") == "BODY\n"


def test_missing_id_errors(proj: Path, capsys) -> None:
    assert run(["reuse", "local/nope", "--root", str(proj)]) == 1
    assert "no library entry" in capsys.readouterr().err


def test_apply_without_lesson_stores_nothing(tmp_path: Path, capsys) -> None:
    (tmp_path / ".context").mkdir()
    assert run(["apply", "--root", str(tmp_path), "--json"]) == 0
    assert not (tmp_path / ".context/equipment/library").exists()


def test_apply_with_lesson_stores_agents(tmp_path: Path, capsys) -> None:
    (tmp_path / ".context").mkdir()
    lesson = tmp_path / "lesson.json"
    lesson.write_text(json.dumps(LESSON), encoding="utf-8")
    argv = ["apply", "--root", str(tmp_path), "--json", "--lesson-file", str(lesson)]
    assert run(argv) == 0
    assert (tmp_path / ".context/equipment/library/library.json").is_file()


def _lesson_file(root: Path, data: dict) -> Path:
    path = root / "lesson.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _with_item(root: Path, item: EquipmentItem) -> None:
    from dummyindex.context.domains.equip import read_manifest

    manifest = read_manifest(root / ".context")
    write_manifest(
        root / ".context",
        EquipmentManifest(
            schema_version=4,
            items=tuple(i for i in manifest.items if i.name != item.name) + (item,),
        ),
    )


def test_apply_stores_only_this_runs_specialists(tmp_path: Path) -> None:
    (tmp_path / ".context").mkdir()
    other = tmp_path / ".claude/agents/other.md"
    other.parent.mkdir(parents=True)
    other.write_text("USER BODY\n", encoding="utf-8")
    _with_item(
        tmp_path,
        EquipmentItem(
            kind=EquipmentKind.AGENT,
            name="other",
            path=".claude/agents/other.md",
            source=EquipmentSource.GENERATED,
            capability_id="local/other",
        ),
    )
    lesson = _lesson_file(tmp_path, LESSON)
    argv = ["apply", "--root", str(tmp_path), "--json", "--lesson-file", str(lesson)]
    assert run(argv) == 0
    index = json.loads(
        (tmp_path / ".context/equipment/library/library.json").read_text("utf-8")
    )
    assert index
    assert "local/other" not in index


def test_apply_invalid_lesson_exits_2_writes_nothing(tmp_path: Path, capsys) -> None:
    (tmp_path / ".context").mkdir()
    lesson = _lesson_file(tmp_path, {"cue": "x"})
    argv = ["apply", "--root", str(tmp_path), "--lesson-file", str(lesson)]
    assert run(argv) == 2
    assert "invalid lesson" in capsys.readouterr().err
    assert not (tmp_path / ".context/equipment.json").exists()
    assert not (tmp_path / ".context/equipment/library").exists()


def _generated(root: Path) -> EquipmentItem:
    from dummyindex.context.domains.equip import content_hash

    path = root / REL
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "---\nversion: 1.0.0\n---\nOLD body\n"
    path.write_text(text, encoding="utf-8")
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="api-dev",
        path=REL,
        source=EquipmentSource.GENERATED,
        grounded_in=("src/a.py",),
        capability_id=CID,
        version="1.0.0",
        origin_hash=content_hash(text),
    )
    _with_item(root, item)
    return item


def _patch_file(root: Path) -> Path:
    path = root / "patch.json"
    path.write_text(json.dumps({"old": "OLD", "new": "NEW"}), encoding="utf-8")
    return path


def test_patch_invalid_lesson_exits_2_touches_nothing(tmp_path: Path) -> None:
    (tmp_path / ".context").mkdir()
    _generated(tmp_path)
    before = (tmp_path / REL).read_bytes()
    bad = _lesson_file(tmp_path, {**LESSON, "confidence": "certain"})
    argv = ["patch", "--item", "api-dev", "--from-file", str(_patch_file(tmp_path))]
    assert run([*argv, "--lesson-file", str(bad), "--root", str(tmp_path)]) == 2
    assert (tmp_path / REL).read_bytes() == before
    assert not (tmp_path / ".context/equipment/library").exists()


def test_patch_lesson_file_stores_patched_item(tmp_path: Path) -> None:
    (tmp_path / ".context").mkdir()
    _generated(tmp_path)
    good = _lesson_file(tmp_path, LESSON)
    argv = ["patch", "--item", "api-dev", "--from-file", str(_patch_file(tmp_path))]
    assert run([*argv, "--lesson-file", str(good), "--root", str(tmp_path)]) == 0
    stored = tmp_path / ".context/equipment/library/local/api-dev/BODY.md"
    assert "NEW body" in stored.read_text(encoding="utf-8")


def test_reuse_pristine_generated_target_rebaselines(tmp_path: Path) -> None:
    from dummyindex.context.domains.equip import content_hash, read_manifest

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    item = _generated(tmp_path)
    library.store(tmp_path, item, "BODY\n", LESSON)
    assert _reuse(tmp_path) == 0
    assert (tmp_path / REL).read_text(encoding="utf-8") == "BODY\n"
    stored = read_manifest(tmp_path / ".context").items[0]
    assert stored.origin_hash == content_hash("BODY\n")


def test_reuse_force_rebaselines_edited_target(tmp_path: Path) -> None:
    from dummyindex.context.domains.equip import content_hash, read_manifest

    item = _generated(tmp_path)
    library.store(tmp_path, item, "BODY\n", LESSON)
    (tmp_path / REL).write_text("LOCAL\n", encoding="utf-8")
    assert _reuse(tmp_path) == 1
    assert _reuse(tmp_path, "--force") == 0
    stored = read_manifest(tmp_path / ".context").items[0]
    assert stored.origin_hash == content_hash("BODY\n")


def test_reuse_id_not_in_manifest_errors(tmp_path: Path, capsys) -> None:
    library.store(tmp_path, _item(), "BODY\n", LESSON)
    assert _reuse(tmp_path) == 1
    assert "not in the equipment manifest" in capsys.readouterr().err
    assert not (tmp_path / REL).exists()
    assert not (tmp_path / ".context/equipment/api-dev.md").exists()


def test_reuse_adopted_without_path_errors(tmp_path: Path, capsys) -> None:
    adopted = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="api-dev",
        path="",
        source=EquipmentSource.GENERATED,
        capability_id=CID,
    )
    _with_item(tmp_path, adopted)
    library.store(tmp_path, adopted, "BODY\n", LESSON)
    assert _reuse(tmp_path) == 1
    assert "no file path" in capsys.readouterr().err
