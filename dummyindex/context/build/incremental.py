"""Incremental rebuild — quick-exit when no tracked file has changed.

The check is cheap: hash every detected source + doc file and compare
against the fingerprints in `.context/cache/manifest.json`. If
added/modified/removed sets are all empty, return without touching disk.

When anything has changed, fall through to a full build. The per-file
extraction cache (pipeline.cache) keeps unchanged-file work near zero, so a
"full rebuild" after a one-file edit is still fast.

Docs land in the same manifest as code, so a README edit triggers a
rebuild too — important once `source-docs/INDEX.{json,md}` exists,
because its staleness signals depend on doc content.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from dummyindex.context.build.runner import BuildResult, build_all
from dummyindex.pipeline.io.cache import file_hash
from dummyindex.pipeline.io.detect import detect


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
    extra_doc_roots: Sequence[Path] = (),
) -> IncrementalResult:
    """Detect changed files since the last build; rebuild only if any changed.

    ``extra_doc_roots`` are forwarded to ``build_all`` so a rebuild
    preserves whatever external doc locations the original ingest used.
    They don't influence the change-detection itself (which fingerprints
    code files); they only matter once a rebuild actually fires.
    """
    root = root.resolve()
    context_dir = root / ".context"
    files_json = context_dir / "map" / "files.json"

    detection = detect(root, extra_doc_roots=tuple(extra_doc_roots))
    files_dict = detection.get("files", {}) or {}
    current_code = [Path(p) for p in files_dict.get("code", [])]
    # Track in-repo docs in the same fingerprint set as code so README edits
    # trigger rebuilds. External (--docs) paths are not repo-relative so they
    # don't participate in incremental change detection.
    current_docs: list[Path] = []
    for ftype in ("document", "paper"):
        for raw in files_dict.get(ftype, []) or []:
            p = Path(raw)
            try:
                p.resolve().relative_to(root)
            except ValueError:
                continue
            current_docs.append(p)

    current_files = current_code + current_docs
    current_by_path = _hash_files(current_files, root)

    prior_by_path = _read_prior_fingerprints_via_manifest(context_dir)
    if prior_by_path is None:
        # First run after a pre-manifest install — fall back to the older
        # files.json fingerprints. That set only has code, so doc edits
        # won't be visible on the very first incremental pass; the rebuild
        # they trigger will re-stamp the manifest with both kinds.
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
        extra_doc_roots=extra_doc_roots,
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


def _read_prior_fingerprints_via_manifest(
    context_dir: Path,
) -> Optional[dict[str, str]]:
    """Pull doc + code fingerprints from cache/manifest.json.

    The manifest is the source of truth for "what's tracked across
    rebuilds" — it includes docs (since the source-docs catalog feature
    landed), so this is the right place to compare against.
    """
    from dummyindex.context.build.manifest import read_manifest

    manifest = read_manifest(context_dir)
    if manifest is None or not manifest.files:
        return None
    return {path: entry.sha256 for path, entry in manifest.files.items()}


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
