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

The detection half (``compute_reconcile_report``) **never writes** anything
and **never decides taxonomy** — it only reports. When there is no anchor
commit, no git, or no features, it returns an empty report rather than
raising.

``stamp_reconciled`` is the one deliberate write: the transactional boundary
the council calls *after* it has placed every unassigned file and enriched
every placed/drifted feature. It advances ``meta.indexed_commit`` to HEAD —
the only thing (besides a fresh ingest) that moves the anchor under Model B.
It **refuses** (unless forced) while any un-reconciled work remains
(unassigned files or features awaiting enrichment), because advancing past
them would silently forget them — the same data-loss class this redesign
closed, one layer up.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dummyindex.context.build.git_delta import (
    changed_paths,
    head_commit,
    working_tree_dirty,
)
from dummyindex.context.build.meta import read_meta, write_meta
from dummyindex.context.domains.features import PENDING_ENRICHMENT_MARKER


@dataclass(frozen=True)
class ReconcileReport:
    """Detection-only summary of how the working tree drifted from the index.

    - ``drifted_features``: feature ids that own at least one changed or
      removed file (sorted, de-duplicated).
    - ``removed_files``: repo-relative paths that were deleted since the
      anchor commit.
    - ``unassigned_new_files``: added paths owned by no feature — the
      council decides where (if anywhere) they belong.
    - ``awaiting_enrichment``: feature ids carrying a ``.pending-enrichment``
      marker — placed by a reconcile op (``scaffold_feature`` /
      ``assign_files``) but not yet (re-)enriched by the council. Surfaced
      independently of git so the ``reconcile-stamp`` guard can see them.
    - ``indexed_commit``: the anchor commit read from meta (``None`` when
      the index has none, e.g. a non-git build).
    """

    drifted_features: tuple[str, ...] = ()
    removed_files: tuple[str, ...] = ()
    unassigned_new_files: tuple[str, ...] = ()
    awaiting_enrichment: tuple[str, ...] = ()
    indexed_commit: Optional[str] = None

    @property
    def has_drift(self) -> bool:
        return bool(
            self.drifted_features
            or self.removed_files
            or self.unassigned_new_files
            or self.awaiting_enrichment
        )


def compute_reconcile_report(context_dir: Path, root: Path) -> ReconcileReport:
    """Build the read-only reconcile report for a built ``.context/``.

    ``context_dir`` is the ``.context/`` directory; ``root`` is the repo
    root the diff runs against. Returns an empty report (no raise) when
    there's no anchor commit, git is unavailable, or the diff can't be
    computed.
    """
    # Marker-based — independent of git, so it survives the no-anchor /
    # no-git short-circuits below (the stamp guard needs it regardless).
    awaiting = _awaiting_enrichment(context_dir)

    indexed = _read_indexed_commit(context_dir)
    if not indexed:
        return ReconcileReport(indexed_commit=None, awaiting_enrichment=awaiting)

    delta = changed_paths(root.resolve(), indexed)
    if delta is None:
        # git absent / not a repo / unknown anchor — nothing detectable.
        return ReconcileReport(
            indexed_commit=indexed, awaiting_enrichment=awaiting
        )

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
        awaiting_enrichment=awaiting,
        indexed_commit=indexed,
    )


def _awaiting_enrichment(context_dir: Path) -> tuple[str, ...]:
    """Feature ids carrying a ``.pending-enrichment`` marker (placed, unenriched).

    The marker is an explicit, restart-surviving flag the placement ops drop —
    see ``PENDING_ENRICHMENT_MARKER``. Tolerates an absent ``features/`` dir.
    """
    features_dir = context_dir / "features"
    if not features_dir.is_dir():
        return ()
    ids = {
        marker.parent.name
        for marker in features_dir.glob(f"*/{PENDING_ENRICHMENT_MARKER}")
    }
    return tuple(sorted(ids))


@dataclass(frozen=True)
class StampResult:
    """Outcome of advancing the reconcile anchor (``stamp_reconciled``).

    - ``stamped_commit``: the sha written to ``meta.indexed_commit``, or
      ``None`` when nothing was stamped (refused, off-git, or no meta).
    - ``refused``: blocked by un-reconciled work and ``force`` was not set.
    - ``off_git``: no HEAD to anchor to (non-git repo or unborn HEAD) — a
      graceful no-op, not an error (the model falls back to hash-manifest).
    - ``dirty_source``: uncommitted changes outside ``.context/`` exist — a
      warning, since that source re-surfaces as drift next reconcile.
    - ``report``: the reconcile report this decision was made from (always
      present, so the caller can print the blockers it refused / forced past).
    """

    report: ReconcileReport
    stamped_commit: Optional[str] = None
    refused: bool = False
    off_git: bool = False
    dirty_source: bool = False


def stamp_reconciled(
    context_dir: Path, root: Path, *, force: bool = False
) -> StampResult:
    """Advance ``meta.indexed_commit`` to HEAD — the reconcile boundary.

    Refuses (returns ``refused=True``, writes nothing) while the report shows
    **unassigned new files** or **features awaiting enrichment**, unless
    ``force=True``. Deliberately does **not** block on ``drifted_features``:
    re-enriching a drifted feature doesn't clear its drift — only the stamp
    does — so blocking on drift could never advance. Off-git is a no-op.
    """
    root = root.resolve()
    report = compute_reconcile_report(context_dir, root)

    blocked = bool(report.unassigned_new_files or report.awaiting_enrichment)
    if blocked and not force:
        return StampResult(report=report, refused=True)

    head = head_commit(root)
    if head is None:
        return StampResult(report=report, off_git=True)

    meta_path = context_dir / "meta.json"
    if not meta_path.is_file():
        return StampResult(report=report)
    try:
        meta = read_meta(meta_path)
    except (ValueError, json.JSONDecodeError, OSError):
        return StampResult(report=report)
    write_meta(meta_path, meta.with_updates(indexed_commit=head))

    return StampResult(
        report=report,
        stamped_commit=head,
        dirty_source=bool(working_tree_dirty(root)),
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
