"""Drift detection: which source files changed since the last rebuild?

After every ingest / rebuild, write a per-file SHA-256 manifest at
``.context/cache/manifest.json``. The ``check`` subcommand compares the
manifest against the current source tree and reports drift; with
``--auto-refresh`` it triggers ``rebuild --changed`` when drift exists.

This is the foundation of v0.6's "always-on" guarantee — every Claude
session starts with a SessionStart hook that runs ``check --auto-refresh``,
so the agent never sees a stale index.

Schema (``.context/cache/manifest.json``):
    {
      "schema_version": 1,
      "generated_at": "2026-05-24T20:30:00+00:00",
      "root": "/abs/path/to/project/root",
      "files": {
        "app.py":         {"sha256": "abc...", "size": 123, "mtime": 1700000000.0},
        "lib/util.py":    {"sha256": "def...", "size":  45, "mtime": 1700000050.0},
        ...
      }
    }

Paths are POSIX, repo-relative.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 1
MANIFEST_REL = Path("cache") / "manifest.json"


@dataclass(frozen=True)
class FileEntry:
    sha256: str
    size: int
    mtime: float

    def to_dict(self) -> dict[str, Any]:
        return {"sha256": self.sha256, "size": self.size, "mtime": self.mtime}

    @classmethod
    def from_path(cls, path: Path) -> "FileEntry":
        data = path.read_bytes()
        h = hashlib.sha256(data).hexdigest()
        st = path.stat()
        return cls(sha256=h, size=st.st_size, mtime=st.st_mtime)


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    generated_at: str
    root: str
    files: dict[str, FileEntry] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "root": self.root,
            "files": {p: e.to_dict() for p, e in self.files.items()},
        }


@dataclass(frozen=True)
class DriftReport:
    """The output of ``compare()`` — what changed since the last manifest."""

    added: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]

    @property
    def is_clean(self) -> bool:
        return not (self.added or self.modified or self.removed)

    @property
    def count(self) -> int:
        return len(self.added) + len(self.modified) + len(self.removed)


def write_manifest(
    context_dir: Path,
    *,
    root: Path,
    files: Iterable[Path],
    now: Optional[_dt.datetime] = None,
) -> Path:
    """Atomically write ``cache/manifest.json`` for the given source files."""
    context_dir = context_dir.resolve()
    root = root.resolve()
    out_path = context_dir / MANIFEST_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    entries: dict[str, FileEntry] = {}
    for fp in files:
        try:
            rel = fp.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        try:
            entries[rel] = FileEntry.from_path(fp.resolve())
        except (OSError, FileNotFoundError):
            # File vanished between detect() and manifest write — skip it.
            continue

    payload = Manifest(
        schema_version=SCHEMA_VERSION,
        generated_at=(now or _dt.datetime.now(_dt.timezone.utc)).isoformat(timespec="seconds"),
        root=str(root),
        files=entries,
    ).to_dict()

    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    return out_path


def read_manifest(context_dir: Path) -> Optional[Manifest]:
    """Return the manifest if it exists; None otherwise."""
    path = context_dir / MANIFEST_REL
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    files = {
        p: FileEntry(sha256=v["sha256"], size=int(v["size"]), mtime=float(v["mtime"]))
        for p, v in raw.get("files", {}).items()
    }
    return Manifest(
        schema_version=int(raw.get("schema_version", SCHEMA_VERSION)),
        generated_at=raw.get("generated_at", ""),
        root=raw.get("root", ""),
        files=files,
    )


def compare(
    context_dir: Path,
    *,
    root: Path,
    current_files: Iterable[Path],
) -> DriftReport:
    """Compare current source state to the stored manifest.

    Returns a DriftReport with ``added`` / ``modified`` / ``removed`` POSIX
    paths relative to ``root``. If no manifest exists, every current file is
    classified as ``added`` (forces a rebuild).

    Performance: re-hashes a file only when its size or mtime differs from
    the manifest. SHA-256 is the source of truth for "modified".
    """
    root = root.resolve()
    stored = read_manifest(context_dir)
    stored_files: dict[str, FileEntry] = dict(stored.files) if stored else {}

    seen: set[str] = set()
    added: list[str] = []
    modified: list[str] = []

    for fp in current_files:
        fp_abs = fp.resolve()
        try:
            rel = fp_abs.relative_to(root).as_posix()
        except ValueError:
            continue
        seen.add(rel)
        prev = stored_files.get(rel)
        if prev is None:
            added.append(rel)
            continue
        try:
            st = fp_abs.stat()
        except OSError:
            continue
        # Cheap check first: size + mtime. Only hash if those differ.
        if st.st_size != prev.size or abs(st.st_mtime - prev.mtime) > 1e-6:
            current = FileEntry.from_path(fp_abs)
            if current.sha256 != prev.sha256:
                modified.append(rel)

    removed = sorted(rel for rel in stored_files if rel not in seen)
    return DriftReport(
        added=tuple(sorted(added)),
        modified=tuple(sorted(modified)),
        removed=tuple(removed),
    )
