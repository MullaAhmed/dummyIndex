"""Specialist library: store, reuse and re-verify proven specialists.

A specialist body plus its ``EXPERIENCE.md`` (the validated lesson) live under
``.context/equipment/library/<capability_id>/``, tracked in
``.context/equipment/library/library.json`` (never ``equipment.json``). Each
entry records the body's ``origin_hash`` and the hash of every grounding path
at store time; :func:`reverify` compares them to the project as it is now.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.lesson import validate_lesson as _validate_lesson

from ..errors import EquipError
from ..models import EquipmentItem
from .hashing import content_hash

LESSON_FIELDS = ("cue", "lesson", "evidence", "confidence")
BODY_NAME = "BODY.md"
EXPERIENCE_NAME = "EXPERIENCE.md"
OK = "ok"
NEEDS_REVERIFY = "needs-reverify"

LessonValidator = Callable[[Mapping[str, object]], None]


def validate_lesson(lesson: Mapping[str, object]) -> None:
    """Delegate to the canonical lesson check; map its error to ``EquipError``."""
    try:
        check = _validate_lesson(
            dict(lesson) if isinstance(lesson, Mapping) else lesson
        )
    except EvolveError as exc:
        raise EquipError(f"invalid lesson: {exc}") from exc
    if check.lesson is None:
        raise EquipError("invalid lesson: legacy reflection shape is not storable")


def _library_dir(root: Path) -> Path:
    return root / ".context" / "equipment" / "library"


def _index_path(root: Path) -> Path:
    return _library_dir(root) / "library.json"


def _read_index(root: Path) -> dict:
    path = _index_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EquipError(f"malformed {path}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _inside(base: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if resolved == base or not resolved.is_relative_to(base):
        raise EquipError(f"{candidate} escapes {base}")
    return resolved


def _capability_id(capability: EquipmentItem) -> str:
    return capability.capability_id or f"local/{capability.name}"


def _entry_dir(root: Path, capability_id: str) -> Path:
    base = _library_dir(root).resolve()
    try:
        return _inside(base, base / capability_id)
    except EquipError:
        raise EquipError(f"unsafe capability id {capability_id!r}") from None


def _file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return content_hash(_norm(path.read_bytes().decode("utf-8", errors="replace")))


def _experience(capability_id: str, lesson: Mapping[str, object]) -> str:
    lines = [f"# Experience: {capability_id}", ""]
    for field in LESSON_FIELDS:
        lines += [f"## {field}", "", str(lesson[field]).strip(), ""]
    return "\n".join(lines)


def store(
    root: Path,
    capability: EquipmentItem,
    body: str,
    lesson: Mapping[str, object],
    *,
    validator: LessonValidator = validate_lesson,
) -> str:
    """Write body + EXPERIENCE.md and record the entry; return the capability id."""
    validator(lesson)
    cid = _capability_id(capability)
    directory = _entry_dir(root, cid)
    directory.mkdir(parents=True, exist_ok=True)
    write_text_atomic(directory / BODY_NAME, body)
    write_text_atomic(directory / EXPERIENCE_NAME, _experience(cid, lesson))
    index = _read_index(root)
    index[cid] = {
        "origin_hash": content_hash(_norm(body)),
        "grounding": {g: _file_hash(root / g) for g in capability.grounded_in},
    }
    write_text_atomic(
        _index_path(root), json.dumps(index, indent=2, sort_keys=True) + "\n"
    )
    return cid


def reuse(root: Path, capability_id: str, target: Path, force: bool = False) -> Path:
    """Copy the stored body to ``target``; refuse to clobber a locally edited file."""
    source_dir = _entry_dir(root, capability_id)
    if capability_id not in _read_index(root):
        raise EquipError(f"no library entry for {capability_id!r}")
    source = source_dir / BODY_NAME
    if not source.is_file():
        raise EquipError(f"library body missing for {capability_id!r}")
    body = source.read_bytes().decode("utf-8")
    dest = _inside(root.resolve(), root / target)
    if dest.exists() and not force and _file_hash(dest) != content_hash(_norm(body)):
        raise EquipError(f"{dest} was edited locally; pass force=True to overwrite")
    dest.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(dest, body)
    return dest


def reverify(root: Path, capability_id: str) -> str:
    """Return ``ok`` or ``needs-reverify`` for a stored specialist."""
    entry = _read_index(root).get(capability_id)
    if not isinstance(entry, dict):
        return NEEDS_REVERIFY
    try:
        directory = _entry_dir(root, capability_id)
    except EquipError:
        return NEEDS_REVERIFY
    if _file_hash(directory / BODY_NAME) != entry.get("origin_hash"):
        return NEEDS_REVERIFY
    for rel, recorded in (entry.get("grounding") or {}).items():
        if _file_hash(root / rel) != recorded:
            return NEEDS_REVERIFY
    return OK
