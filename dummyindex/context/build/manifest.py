"""Drift detection: which source files changed since the last rebuild?

A full build and ``reconcile-stamp`` write per-file SHA-256s to
``.context/cache/manifest.json``; ``check`` compares them with the current tree
(``--auto-refresh`` then runs ``rebuild --changed``). Shape: ``{"schema_version": 1,
"generated_at": <iso>, "root": <abs path>, "files": {<repo-relative POSIX path>:
{"sha256", "size", "mtime"}}}``.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    def from_path(cls, path: Path) -> FileEntry:
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
    now: _dt.datetime | None = None,
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
        generated_at=(now or _dt.datetime.now(_dt.timezone.utc)).isoformat(
            timespec="seconds"
        ),
        root=str(root),
        files=entries,
    ).to_dict()

    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    tmp.replace(out_path)
    return out_path


def read_manifest(context_dir: Path) -> Manifest | None:
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

    Returns ``added``/``modified``/``removed`` POSIX paths relative to ``root``; with no
    manifest every current file is ``added``. Re-hashes only files whose size or mtime
    changed; SHA-256 decides "modified".
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
