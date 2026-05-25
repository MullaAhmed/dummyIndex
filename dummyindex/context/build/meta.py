"""`.context/meta.json` schema, I/O, and Meta dataclass.

Stable surface: `Meta`, `SCHEMA_VERSION`, `new_meta`, `read_meta`, `write_meta`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Meta:
    schema_version: int
    dummyindex_version: str
    created_at: str
    updated_at: str
    root: str
    languages: tuple[str, ...] = ()
    file_count: int = 0
    symbol_count: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def with_updates(self, **changes: Any) -> "Meta":
        current = asdict(self)
        current["languages"] = tuple(current.get("languages", ()))
        current.update(changes)
        current["updated_at"] = _now_iso()
        return Meta(**current)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_meta(root: Path, dummyindex_version: str) -> Meta:
    now = _now_iso()
    return Meta(
        schema_version=SCHEMA_VERSION,
        dummyindex_version=dummyindex_version,
        created_at=now,
        updated_at=now,
        root=str(root.resolve()),
    )


def read_meta(path: Path) -> Meta:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"meta.json must be a JSON object, got {type(raw).__name__}")
    version = raw.get("schema_version")
    if not isinstance(version, int):
        raise ValueError("meta.json missing integer schema_version")
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"meta.json schema_version={version} is newer than this dummyindex build "
            f"(supports up to {SCHEMA_VERSION}). Upgrade dummyindex."
        )
    for required in ("dummyindex_version", "created_at", "updated_at", "root"):
        if required not in raw:
            raise ValueError(f"meta.json missing required field '{required}'")
    return Meta(
        schema_version=version,
        dummyindex_version=str(raw["dummyindex_version"]),
        created_at=str(raw["created_at"]),
        updated_at=str(raw["updated_at"]),
        root=str(raw["root"]),
        languages=tuple(raw.get("languages", ())),
        file_count=int(raw.get("file_count", 0)),
        symbol_count=int(raw.get("symbol_count", 0)),
        config=dict(raw.get("config", {})),
    )


def write_meta(path: Path, meta: Meta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(meta)
    payload["languages"] = list(meta.languages)  # JSON has no tuple type
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
