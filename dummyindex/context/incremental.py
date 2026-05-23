"""Incremental rebuild — quick-exit when no source file has changed.

The check is cheap: hash every detected source file and compare against the
fingerprints in the existing `.context/map/files.json`. If added/modified/
removed sets are all empty, return without touching disk.

When anything has changed, fall through to a full build. The per-file
extraction cache (pipeline.cache) keeps unchanged-file work near zero, so a
"full rebuild" after a one-file edit is still fast.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dummyindex.context.runner import BuildResult, build_all
from dummyindex.pipeline.cache import file_hash
from dummyindex.pipeline.detect import detect


@dataclass(frozen=True)
class ChangeSet:
    added: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.removed)


@dataclass(frozen=True)
class IncrementalResult:
    skipped: bool
    changes: ChangeSet
    build_result: Optional[BuildResult]


def rebuild_changed(
    root: Path,
    *,
    cache_root: Optional[Path] = None,
    bootstrap: bool = False,
    dummyindex_version: str = "0.0.0",
) -> IncrementalResult:
    """Detect changed files since the last build; rebuild only if any changed."""
    root = root.resolve()
    files_json = root / ".context" / "map" / "files.json"

    detection = detect(root)
    current_files = [Path(p) for p in detection.get("files", {}).get("code", [])]
    current_by_path = _hash_files(current_files, root)

    prior_by_path = _read_prior_fingerprints(files_json)

    if prior_by_path is None:
        changes = ChangeSet(
            added=tuple(sorted(current_by_path)),
            modified=(),
            removed=(),
        )
    else:
        changes = _diff(prior_by_path, current_by_path)

    if not changes.has_changes and prior_by_path is not None:
        return IncrementalResult(skipped=True, changes=changes, build_result=None)

    result = build_all(
        root,
        cache_root=cache_root,
        bootstrap=bootstrap,
        dummyindex_version=dummyindex_version,
    )
    return IncrementalResult(skipped=False, changes=changes, build_result=result)


def _hash_files(paths: list[Path], root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in paths:
        p = raw if raw.is_absolute() else (root / raw)
        try:
            rel = p.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if not p.is_file():
            continue
        try:
            out[rel] = file_hash(p, root)
        except OSError:
            continue
    return out


def _read_prior_fingerprints(files_json: Path) -> Optional[dict[str, str]]:
    if not files_json.exists():
        return None
    try:
        payload = json.loads(files_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    out: dict[str, str] = {}
    for entry in payload.get("files", []):
        path = entry.get("path")
        sha = entry.get("sha256")
        if isinstance(path, str) and isinstance(sha, str) and sha:
            out[path] = sha
    return out


def _diff(prior: dict[str, str], current: dict[str, str]) -> ChangeSet:
    added = tuple(sorted(p for p in current if p not in prior))
    removed = tuple(sorted(p for p in prior if p not in current))
    modified = tuple(
        sorted(
            p for p in current
            if p in prior and prior[p] != current[p]
        )
    )
    return ChangeSet(added=added, modified=modified, removed=removed)
