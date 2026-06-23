"""Atomic read/write of ``.context/equipment.json``.

The equipment manifest is the record of what equip put into ``.claude/`` — one
:class:`EquipmentItem` per tuned tool, with its capabilities and the
``.context/`` docs it is grounded in. Writes go through a tmp+rename so a
crashed run never leaves a half-written manifest (mirrors
``build/maps._atomic_write_json``).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import EquipError
from ..models import EquipmentManifest

EQUIPMENT_REL = "equipment.json"


def read_manifest(context_dir: Path) -> EquipmentManifest:
    """Load ``<context_dir>/equipment.json``, or an empty manifest if absent.

    Raises :class:`EquipError` when the file exists but is not valid JSON, or
    carries an unrecognised kind/source value (e.g. a manifest written by a
    NEWER dummyindex) — a manifest the caller can't load is a hard error to
    surface, not silently overwrite. Every caller already wraps this in
    ``except EquipError``, so normalising the enum/shape errors here keeps the
    forward-compat failure mode clean (a clear message, not a raw traceback /
    crashed audit roster) across all of them.
    """
    path = context_dir / EQUIPMENT_REL
    if not path.is_file():
        return EquipmentManifest(schema_version=1, items=())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EquipError(f"equipment.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise EquipError("equipment.json must be a JSON object")
    try:
        return EquipmentManifest.from_dict(data)
    except (ValueError, KeyError, TypeError) as exc:
        raise EquipError(
            f"equipment.json has an unrecognised field or value "
            f"(written by a newer dummyindex?): {exc}"
        ) from exc


def write_manifest(context_dir: Path, manifest: EquipmentManifest) -> Path:
    """Atomically write ``manifest`` to ``<context_dir>/equipment.json``.

    Returns the written path. Creates ``context_dir`` if needed.
    """
    path = context_dir / EQUIPMENT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise EquipError(f"could not write equipment.json: {exc}") from exc
    return path
