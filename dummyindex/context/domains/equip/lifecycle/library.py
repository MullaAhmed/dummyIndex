"""Specialist library: store, reuse and re-verify proven specialists.

A specialist body plus its ``EXPERIENCE.md`` (the validated lesson) live under
``.context/equipment/library/<capability_id>/``, tracked in
``.context/equipment/library/library.json`` (never ``equipment.json``). Each
entry records the body's ``origin_hash`` and the hash of every grounding path
at store time; :func:`reverify` compares them to the project as it is now.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.lesson import validate_lesson as _validate_lesson

from ..enums import EquipmentKind
from ..errors import EquipError
from ..identity import capability_id as _capability_id
from ..models import EquipmentItem
from .hashing import content_hash
from .manifest import read_manifest, write_manifest

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


def _safe_id(capability_id: object) -> bool:
    """Plain non-empty ``/``-separated ids: no backslash, colon, NUL or dot segments."""
    if not isinstance(capability_id, str) or not capability_id:
        return False
    if capability_id.startswith("/") or any(c in capability_id for c in "\\:\x00"):
        return False
    return all(seg not in ("", ".", "..") for seg in capability_id.split("/"))


def _entry_dir(root: Path, capability_id: str) -> Path:
    if not _safe_id(capability_id):
        raise EquipError(f"unsafe capability id {capability_id!r}")
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


def reuse(
    root: Path,
    capability_id: str,
    target: Path,
    force: bool = False,
    baseline: str | None = None,
) -> Path:
    """Copy the stored body to ``target``; refuse to clobber a locally edited file.

    ``baseline`` is the recorded hash of what the target holds untouched (the
    manifest ``origin_hash``); the library body also counts as unedited.
    """
    source_dir = _entry_dir(root, capability_id)
    if capability_id not in _read_index(root):
        raise EquipError(f"no library entry for {capability_id!r}")
    source = source_dir / BODY_NAME
    if not source.is_file():
        raise EquipError(f"library body missing for {capability_id!r}")
    body = source.read_bytes().decode("utf-8")
    dest = _inside(root.resolve(), root / target)
    if dest.exists() and not force:
        unedited = {content_hash(_norm(body))}
        if baseline is not None:
            unedited.add(baseline)
        if _file_hash(dest) not in unedited:
            raise EquipError(f"{dest} was edited locally; pass --force to overwrite")
    dest.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(dest, body)
    return dest


def find_item(
    items: tuple[EquipmentItem, ...], capability_id: str
) -> EquipmentItem | None:
    """The manifest item whose capability id is ``capability_id``, if any."""
    for item in items:
        if _capability_id(item) == capability_id:
            return item
    return None


def agent_items(
    items: tuple[EquipmentItem, ...], names: set[str] | None = None
) -> list[EquipmentItem]:
    """Agent items with a body path, restricted to ``names`` when given."""
    return [
        i
        for i in items
        if i.kind is EquipmentKind.AGENT
        and i.path
        and (names is None or i.name in names)
    ]


def reuse_capability(root: Path, capability_id: str, force: bool = False) -> Path:
    """Reuse a stored specialist at its manifest path; re-baseline the manifest."""
    if capability_id not in _read_index(root):
        raise EquipError(f"no library entry for {capability_id!r}")
    context_dir = root / ".context"
    manifest = read_manifest(context_dir)
    item = find_item(manifest.items, capability_id)
    if item is None:
        raise EquipError(
            f"{capability_id!r} is not in the equipment manifest; "
            "run `equip apply` to record it before reuse"
        )
    if not item.path:
        raise EquipError(
            f"{capability_id!r} is a manifest-only adoption with no file path; "
            "nothing to copy to"
        )
    dest = reuse(root, capability_id, Path(item.path), force, item.origin_hash)
    if item.origin_hash is not None:
        body = (_entry_dir(root, capability_id) / BODY_NAME).read_bytes()
        rebased = dataclasses.replace(
            item, origin_hash=content_hash(_norm(body.decode("utf-8")))
        )
        items = tuple(rebased if i.name == item.name else i for i in manifest.items)
        write_manifest(context_dir, dataclasses.replace(manifest, items=items))
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
