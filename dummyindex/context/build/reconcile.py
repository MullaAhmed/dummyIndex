# read-only commit-diff → feature-ownership mapping; never writes, never decides
"""Reconcile report — detect drift between the indexed commit and HEAD.

This is the deterministic *detection* half of the commit-anchored update
(the council/LLM owns placement decisions — see the spec). Given a built
``.context/`` and the repo root, it:

1. reads ``meta.indexed_commit`` (the commit the index was reconciled
   against),
2. asks ``git_delta.changed_paths`` for added / modified / removed paths
   since that commit (working tree included),
3. maps each changed-or-removed path to the feature(s) that own it (each
   ``features/<id>/feature.json`` lists its ``files``).

It **never writes** anything and **never decides taxonomy** — it only
reports. When there is no anchor commit, no git, or no features, it
returns an empty report rather than raising.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dummyindex.context.build.git_delta import changed_paths


@dataclass(frozen=True)
class ReconcileReport:
    """Detection-only summary of how the working tree drifted from the index.

    - ``drifted_features``: feature ids that own at least one changed or
      removed file (sorted, de-duplicated).
    - ``removed_files``: repo-relative paths that were deleted since the
      anchor commit.
    - ``unassigned_new_files``: added paths owned by no feature — the
      council decides where (if anywhere) they belong.
    - ``indexed_commit``: the anchor commit read from meta (``None`` when
      the index has none, e.g. a non-git build).
    """

    drifted_features: tuple[str, ...] = ()
    removed_files: tuple[str, ...] = ()
    unassigned_new_files: tuple[str, ...] = ()
    indexed_commit: Optional[str] = None

    @property
    def has_drift(self) -> bool:
        return bool(
            self.drifted_features
            or self.removed_files
            or self.unassigned_new_files
        )


def compute_reconcile_report(context_dir: Path, root: Path) -> ReconcileReport:
    """Build the read-only reconcile report for a built ``.context/``.

    ``context_dir`` is the ``.context/`` directory; ``root`` is the repo
    root the diff runs against. Returns an empty report (no raise) when
    there's no anchor commit, git is unavailable, or the diff can't be
    computed.
    """
    indexed = _read_indexed_commit(context_dir)
    if not indexed:
        return ReconcileReport(indexed_commit=None)

    delta = changed_paths(root.resolve(), indexed)
    if delta is None:
        # git absent / not a repo / unknown anchor — nothing detectable.
        return ReconcileReport(indexed_commit=indexed)

    owners = _file_owners(context_dir)

    drifted: set[str] = set()
    for path in (*delta.modified, *delta.removed):
        for feature_id in owners.get(path, ()):
            drifted.add(feature_id)

    unassigned = tuple(
        sorted(p for p in delta.added if p not in owners and not _is_context_path(p))
    )

    return ReconcileReport(
        drifted_features=tuple(sorted(drifted)),
        removed_files=tuple(sorted(delta.removed)),
        unassigned_new_files=unassigned,
        indexed_commit=indexed,
    )


def _read_indexed_commit(context_dir: Path) -> Optional[str]:
    """Read ``indexed_commit`` from ``meta.json``, tolerating a missing field.

    Returns ``None`` when meta is absent, unreadable, or carries no
    ``indexed_commit``. Never raises.
    """
    meta_path = context_dir / "meta.json"
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get("indexed_commit")
    return value if isinstance(value, str) and value else None


def _file_owners(context_dir: Path) -> dict[str, tuple[str, ...]]:
    """Map every repo-relative file path to the feature ids that own it.

    Ownership comes from each ``features/<id>/feature.json``'s ``files``
    list. A file owned by multiple features maps to all of them. Missing
    or unreadable feature folders are skipped (no raise).
    """
    features_dir = context_dir / "features"
    if not features_dir.is_dir():
        return {}

    owners: dict[str, set[str]] = {}
    for feature_json in sorted(features_dir.glob("*/feature.json")):
        try:
            payload = json.loads(feature_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        feature_id = payload.get("feature_id") or feature_json.parent.name
        for raw in payload.get("files", []) or []:
            if isinstance(raw, str) and raw:
                owners.setdefault(raw, set()).add(feature_id)

    return {path: tuple(sorted(ids)) for path, ids in owners.items()}


def _is_context_path(path: str) -> bool:
    """True for the index's own files, so its churn isn't reported as new."""
    return path == ".context" or path.startswith(".context/")
