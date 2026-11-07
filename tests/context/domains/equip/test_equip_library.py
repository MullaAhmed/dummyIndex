"""Specialist library: store / reuse / reverify."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentKind,
    EquipmentSource,
)
from dummyindex.context.domains.equip.errors import EquipError
from dummyindex.context.domains.equip.lifecycle.library import (
    reuse,
    reverify,
    store,
)

LESSON = {
    "cue": "api change",
    "lesson": "run schema check",
    "evidence": "pr-12",
    "confidence": "high",
}


def _cap() -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="api-dev",
        path=".claude/agents/api-dev.md",
        source=EquipmentSource.GENERATED,
        grounded_in=("src/a.py",),
        capability_id="local/api-dev",
    )


@pytest.fixture
def stored(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    store(tmp_path, _cap(), "BODY\n", LESSON)
    return tmp_path


@pytest.mark.unit
def test_store_then_reuse_copies_body(stored: Path) -> None:
    reuse(stored, "local/api-dev", Path("out/agent.md"))
    assert (stored / "out" / "agent.md").read_text(encoding="utf-8") == "BODY\n"
    assert (stored / ".context/equipment/library/library.json").is_file()
    assert not (stored / ".context/equipment/equipment.json").exists()


@pytest.mark.unit
def test_unchanged_is_ok(stored: Path) -> None:
    assert reverify(stored, "local/api-dev") == "ok"


@pytest.mark.unit
def test_changed_grounding_needs_reverify(stored: Path) -> None:
    (stored / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert reverify(stored, "local/api-dev") == "needs-reverify"


@pytest.mark.unit
def test_deleted_grounding_needs_reverify(stored: Path) -> None:
    (stored / "src" / "a.py").unlink()
    assert reverify(stored, "local/api-dev") == "needs-reverify"


@pytest.mark.unit
def test_missing_entry_needs_reverify(stored: Path) -> None:
    assert reverify(stored, "local/nope") == "needs-reverify"


@pytest.mark.unit
def test_reuse_refuses_edited_target_without_force(stored: Path) -> None:
    target = stored / "agent.md"
    target.write_text("edited\n", encoding="utf-8")
    with pytest.raises(EquipError):
        reuse(stored, "local/api-dev", target)
    assert target.read_text(encoding="utf-8") == "edited\n"
    reuse(stored, "local/api-dev", target, force=True)
    assert target.read_text(encoding="utf-8") == "BODY\n"


@pytest.mark.unit
def test_experience_carries_lesson_fields(stored: Path) -> None:
    path = stored / ".context/equipment/library/local/api-dev/EXPERIENCE.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Experience: local/api-dev\n")
    for field, value in LESSON.items():
        assert f"## {field}\n\n{value}\n" in text


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    [
        {"cue": "x"},
        {**LESSON, "confidence": "certain"},
        {**LESSON, "cue": "  "},
    ],
)
def test_invalid_lesson_rejected(tmp_path: Path, bad: dict) -> None:
    with pytest.raises(EquipError):
        store(tmp_path, _cap(), "B", bad)


@pytest.mark.unit
def test_none_lesson_rejected(tmp_path: Path) -> None:
    with pytest.raises(EquipError):
        store(tmp_path, _cap(), "B", None)  # type: ignore[arg-type]


@pytest.mark.unit
def test_injected_validator_used(tmp_path: Path) -> None:
    seen: list[object] = []
    store(tmp_path, _cap(), "B", LESSON, validator=seen.append)
    assert seen == [LESSON]


def _cap_id(cid: str) -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="x",
        path=".claude/agents/x.md",
        source=EquipmentSource.GENERATED,
        capability_id=cid,
    )


_BAD_IDS = ["/x", "\\x", "../x", "local/../../x", "..", "."]
if sys.platform == "win32":
    _other = "Z" if Path.cwd().drive.upper() != "Z:" else "Y"
    _BAD_IDS += [f"{_other}:evil", f"{_other}:\\evil"]


@pytest.mark.unit
@pytest.mark.parametrize("cid", _BAD_IDS)
def test_unsafe_capability_id_rejected(tmp_path: Path, cid: str) -> None:
    with pytest.raises(EquipError):
        store(tmp_path, _cap_id(cid), "B", LESSON)
    with pytest.raises(EquipError):
        reuse(tmp_path, cid, Path("o.md"))
    assert reverify(tmp_path, cid) == "needs-reverify"
    assert not (tmp_path / "x").exists()


@pytest.mark.unit
@pytest.mark.parametrize("target", ["/x/evil.md", "../evil.md", "a/../../evil.md"])
def test_reuse_target_escape_rejected(stored: Path, target: str) -> None:
    with pytest.raises(EquipError):
        reuse(stored, "local/api-dev", Path(target))


@pytest.mark.unit
def test_edited_library_body_needs_reverify(stored: Path) -> None:
    body = stored / ".context/equipment/library/local/api-dev/BODY.md"
    body.write_text("TAMPERED\n", encoding="utf-8")
    assert reverify(stored, "local/api-dev") == "needs-reverify"


@pytest.mark.unit
def test_crlf_grounding_still_ok(stored: Path) -> None:
    (stored / "src" / "a.py").write_bytes(b"x = 1\r\n")
    assert reverify(stored, "local/api-dev") == "ok"


@pytest.mark.unit
def test_files_are_lf_only(stored: Path) -> None:
    lib = stored / ".context/equipment/library"
    for path in (lib / "library.json", lib / "local/api-dev/EXPERIENCE.md"):
        assert b"\r" not in path.read_bytes()


@pytest.mark.unit
def test_reuse_accepts_manifest_baseline_target(stored: Path) -> None:
    from dummyindex.context.domains.equip import content_hash

    target = stored / "agent.md"
    target.write_text("generated\n", encoding="utf-8")
    with pytest.raises(EquipError, match="--force"):
        reuse(stored, "local/api-dev", target)
    reuse(stored, "local/api-dev", target, baseline=content_hash("generated\n"))
    assert target.read_text(encoding="utf-8") == "BODY\n"
