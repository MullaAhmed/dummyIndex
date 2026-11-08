# commit-diff → feature-ownership drift report (read-only); stamp_reconciled is the one write
"""Reconcile report: detect drift between the indexed commit and HEAD.

:func:`compute_reconcile_report` diffs ``meta.indexed_commit`` against HEAD and the
working tree, mapping each changed path to the features that list it. It never writes
or decides taxonomy (the council places files); with no anchor or git it reports only
pending markers. :func:`stamp_reconciled` is the one write: it advances the anchor and
drift manifest together, refusing while un-reconciled work would be silently forgotten.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path

from dummyindex.codex_guidance import (
    is_project_instruction_path,
    project_instruction_paths,
)
from dummyindex.context.build.common import collect_doc_paths
from dummyindex.context.build.git_delta import (
    changed_paths,
    commit_exists,
    head_commit,
    is_ancestor_of_head,
    working_tree_dirty,
)
from dummyindex.context.build.manifest import write_manifest
from dummyindex.context.build.meta import read_meta, write_meta
from dummyindex.context.build.scope import scan_root
from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.config import ConfigError, read_config
from dummyindex.context.domains.features import PENDING_ENRICHMENT_MARKER
from dummyindex.pipeline.io.detect import detect


class AnchorStatus(str, Enum):
    """How the recorded anchor (``meta.indexed_commit``) relates to the repo.

    ``NONE``: no anchor recorded, or no git to check it. ``OK``: an ancestor of HEAD.
    ``MISSING_FROM_REPO``: unknown SHA (rebased/squashed or never fetched); the delta
    can't be computed, so the report must NOT read as clean. ``NOT_ANCESTOR``: not in
    HEAD's history, so a diff may count other branches' work as drift.
    """

    NONE = "none"
    OK = "ok"
    MISSING_FROM_REPO = "missing_from_repo"
    NOT_ANCESTOR = "not_ancestor"


@dataclass(frozen=True)
class ReconcileReport:
    """Detection-only summary of how the working tree drifted from the index.

    ``drifted_features`` own a changed or removed file; ``removed_files`` were deleted
    since the anchor; ``unassigned_new_files`` are added paths no feature owns (the
    council places them); ``awaiting_enrichment`` carry a ``.pending-enrichment`` marker,
    read independently of git so the stamp guard sees them. ``indexed_commit`` is the
    anchor (``None`` when meta has none); ``anchor_status`` is its :class:`AnchorStatus`.
    """

    drifted_features: tuple[str, ...] = ()
    removed_files: tuple[str, ...] = ()
    unassigned_new_files: tuple[str, ...] = ()
    awaiting_enrichment: tuple[str, ...] = ()
    indexed_commit: str | None = None
    anchor_status: AnchorStatus = AnchorStatus.NONE

    @property
    def anchor_broken(self) -> bool:
        """The anchor is orphaned (rebase/squash/never-fetched) — drift is
        not computable, so callers must surface a re-baseline path rather than
        a clean all-clear."""
        return self.anchor_status == AnchorStatus.MISSING_FROM_REPO

    @property
    def has_drift(self) -> bool:
        return bool(
            self.drifted_features
            or self.removed_files
            or self.unassigned_new_files
            or self.awaiting_enrichment
            or self.anchor_broken
        )


def compute_reconcile_report(context_dir: Path, root: Path) -> ReconcileReport:
    """Build the read-only reconcile report for a built ``.context/``.

    ``context_dir`` is the ``.context/`` directory; ``root`` is the repo
    root the diff runs against. Returns an empty report (no raise) when
    there's no anchor commit, git is unavailable, or the diff can't be
    computed.
    """
    resolved_root = root.resolve()
    scope = scan_root(resolved_root).relative_to(resolved_root)

    def in_scope(path: str) -> bool:
        return scope == Path(".") or Path(path).is_relative_to(scope)

    # Marker-based — independent of git, so it survives the no-anchor /
    # no-git short-circuits below (the stamp guard needs it regardless).
    awaiting = _awaiting_enrichment(context_dir)
    excludes = _reconcile_excludes(context_dir)

    indexed = _read_indexed_commit(context_dir)
    if not indexed:
        return ReconcileReport(
            indexed_commit=None,
            awaiting_enrichment=awaiting,
            anchor_status=AnchorStatus.NONE,
        )

    # Orphaned anchor (rebase/squash/never-fetched): the diff would either
    # error out (clean-looking empty report) or, if the dangling object still
    # exists, attribute the whole divergence as drift. Surface it explicitly
    # instead of either false reading.
    if commit_exists(resolved_root, indexed) is False:
        owners = _file_owners(context_dir)
        current: set[str] = set()
        for raw in detect(resolved_root / scope).get("files", {}).get("code", []):
            try:
                path = Path(raw).resolve().relative_to(resolved_root).as_posix()
            except ValueError:
                continue
            if not is_non_source_path(
                path, project_root=resolved_root
            ) and not _matches_any(path, excludes):
                current.add(path)
        return ReconcileReport(
            indexed_commit=indexed,
            awaiting_enrichment=awaiting,
            anchor_status=AnchorStatus.MISSING_FROM_REPO,
            unassigned_new_files=tuple(sorted(current - owners.keys())),
            removed_files=tuple(
                sorted(
                    p
                    for p in owners
                    if in_scope(p) and not (resolved_root / p).is_file()
                )
            ),
            drifted_features=tuple(
                sorted(
                    {
                        feature
                        for path, ids in owners.items()
                        if in_scope(path)
                        for feature in ids
                    }
                )
            ),
        )

    delta = changed_paths(resolved_root, indexed)
    if delta is None:
        # git absent / not a repo — nothing detectable. (The unknown-anchor
        # case is handled above; here it's a genuinely off-git build.)
        return ReconcileReport(
            indexed_commit=indexed,
            awaiting_enrichment=awaiting,
            anchor_status=AnchorStatus.NONE,
        )

    anchor_status = (
        AnchorStatus.OK
        if is_ancestor_of_head(resolved_root, indexed) is not False
        else AnchorStatus.NOT_ANCESTOR
    )

    owners = _file_owners(context_dir)
    codex_instruction_paths = project_instruction_paths(resolved_root)

    def _hidden(path: str) -> bool:
        # dummyindex's own index + tool footprint, plus any user-configured
        # repo-specific noise globs — none of it is feature-ownable work.
        return (
            not in_scope(path)
            or _is_context_path(path)
            or _is_tool_path(
                path,
                project_root=resolved_root,
                instruction_paths=codex_instruction_paths,
            )
            or _matches_any(path, excludes)
        )

    drifted: set[str] = set()
    for path in (*delta.modified, *delta.removed):
        if _hidden(path):
            continue
        for feature_id in owners.get(path, ()):
            drifted.add(feature_id)

    unassigned = tuple(
        sorted(p for p in delta.added if p not in owners and not _hidden(p))
    )
    removed = tuple(sorted(p for p in delta.removed if not _hidden(p)))

    return ReconcileReport(
        drifted_features=tuple(sorted(drifted)),
        removed_files=removed,
        unassigned_new_files=unassigned,
        awaiting_enrichment=awaiting,
        indexed_commit=indexed,
        anchor_status=anchor_status,
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
    """Outcome of :func:`stamp_reconciled`; ``report`` is the report it decided from.

    ``stamped_commit``: the sha written, else ``None``. ``refused``: blocked by
    un-reconciled work or an orphaned anchor. ``off_git``: no HEAD (a no-op, not an
    error). ``dirty_source``: uncommitted source outside ``.context/`` will re-surface as
    drift. ``bootstrapped``: no prior anchor, so older staleness won't show. ``invalid_to``:
    ``--to`` named an unknown commit. Refusals and no-ops write nothing.
    """

    report: ReconcileReport
    stamped_commit: str | None = None
    refused: bool = False
    off_git: bool = False
    dirty_source: bool = False
    bootstrapped: bool = False
    invalid_to: bool = False


def stamp_reconciled(
    context_dir: Path,
    root: Path,
    *,
    force: bool = False,
    to_commit: str | None = None,
) -> StampResult:
    """Advance ``meta.indexed_commit`` to HEAD, or re-baseline to a validated ``to_commit``.

    Unless ``force``, refuses while unassigned files or features awaiting enrichment remain,
    or, absent ``to_commit``, while the anchor is orphaned. Drifted features never block:
    only the stamp clears drift. The only guard is the report from the anchor it rewrites;
    once advanced, later reports read clean. Off-git is a no-op. Success also writes
    ``cache/manifest.json`` and ``cache/doc-basis.json``; a refusal or no-op writes nothing.
    """
    root = root.resolve()
    report = compute_reconcile_report(context_dir, root)

    if to_commit is not None and commit_exists(root, to_commit) is not True:
        # An explicit re-baseline target the repo doesn't have — refuse,
        # write nothing (the caller maps invalid_to → exit 2).
        return StampResult(report=report, invalid_to=True)

    blocked = bool(report.unassigned_new_files or report.awaiting_enrichment)
    # An orphaned anchor reads as broken; only an explicit --to (re-baseline)
    # or --force may advance past it.
    if report.anchor_broken and to_commit is None and not force:
        return StampResult(report=report, refused=True)
    if blocked and not force:
        return StampResult(report=report, refused=True)

    target = to_commit if to_commit is not None else head_commit(root)
    if target is None:
        return StampResult(report=report, off_git=True)

    meta_path = context_dir / "meta.json"
    if not meta_path.is_file():
        return StampResult(report=report)
    try:
        meta = read_meta(meta_path)
    except (ValueError, json.JSONDecodeError, OSError):
        return StampResult(report=report)
    write_meta(meta_path, meta.with_updates(indexed_commit=target))
    _write_doc_basis(context_dir, root)

    # cache/manifest.json means "bytes the docs describe", so it advances with the anchor,
    # not on refresh: drift.py:_content_unchanged uses it to filter git-minted mtime rows,
    # and a refresh-time stamp would erase the edit that triggered the rebuild. Same file
    # set as runner.build_all; any failure warns, never aborts a stamp already written.
    try:
        detection = detect(scan_root(root))
        raw_code = (detection.get("files", {}) or {}).get("code", []) or []
        code_files = [Path(p) for p in raw_code]
        manifest_files: list[Path] = list(code_files) + collect_doc_paths(
            detection, root, ()
        )
        write_manifest(context_dir, root=root, files=manifest_files)
    except Exception as exc:
        import warnings

        warnings.warn(
            f"manifest write failed: {exc!r}; drift detection disabled", stacklevel=2
        )

    return StampResult(
        report=report,
        stamped_commit=target,
        dirty_source=bool(working_tree_dirty(root)),
        bootstrapped=report.indexed_commit is None and to_commit is None,
    )


# The gitignored doc-basis cache: written only at the stamp boundary (the
# moment docs are declared fresh), read by the drift scanner to classify
# mtime-only churn as suppressed. Same tier as ``cache/manifest.json`` —
# per-machine scratch that regenerates on the next stamp.
DOC_BASIS_REL = Path("cache") / "doc-basis.json"
DOC_BASIS_VERSION = 1


def blob_sha(data: bytes) -> str:
    """The git blob sha of ``data`` — no subprocess.

    Pure-python re-implementation of ``git hash-object --no-filters``:
    ``sha1(b"blob <size>\\0" + data)``. Deterministic across machines and
    hashes the exact working-tree bytes without Git clean filters or newline
    normalization. A later working-tree re-hash compares the same byte state.
    """
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _write_doc_basis(context_dir: Path, root: Path) -> None:
    """Snapshot every feature-owned file's blob sha into ``doc-basis.json``.

    Shape: ``{"basis_version": 1, "features": {<id>: {<rel_path>: <blob_sha>}}}`` from
    the working tree at stamp time; files outside root or unreadable are skipped.
    Best-effort: on I/O failure the drift scanner falls back (manifest, then mtime);
    it must never fail an already-stamped boundary.
    """
    try:
        feature_map = _feature_file_shas(context_dir, root)
        payload = (
            json.dumps(
                {"basis_version": DOC_BASIS_VERSION, "features": feature_map},
                indent=2,
            )
            + "\n"
        )
        write_text_atomic(context_dir / DOC_BASIS_REL, payload)
    except OSError:
        return


def _feature_file_shas(context_dir: Path, root: Path) -> dict[str, dict[str, str]]:
    """Feature id → {rel_path: blob sha} for every owned file present on disk."""
    owners = _file_owners(context_dir)
    basis: dict[str, dict[str, str]] = {}
    for rel in sorted(owners):
        fp = (root / rel).resolve()
        try:
            fp.relative_to(root)
        except ValueError:
            continue
        try:
            sha = blob_sha(fp.read_bytes())
        except OSError:
            continue
        for feature_id in owners[rel]:
            basis.setdefault(feature_id, {})[rel] = sha
    return {fid: dict(sorted(shas.items())) for fid, shas in sorted(basis.items())}


def _read_indexed_commit(context_dir: Path) -> str | None:
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


# dummyindex's own install + equip footprint. The taxonomy can never own agent/skill/
# command wiring, so these trees and host-instruction files at any depth are excluded
# from the reconcile delta and drift report.
_TOOL_DIR_NAMES: frozenset[str] = frozenset(
    {".claude", ".agents", ".codex", ".claude-design"}
)


def _is_tool_path(
    path: str,
    *,
    project_root: Path | None = None,
    instruction_paths: Iterable[str] | None = None,
) -> bool:
    """True for dummyindex's own host wiring and design artifacts.

    Claude wiring lives under ``.claude/``; Codex skills live under
    ``.agents/``, native config and custom agents under ``.codex/``, and its
    durable project guidance uses the first active standard or configured
    fallback filename from the root or a nested directory. None is
    feature-ownable source.
    """
    parts = path.split("/")
    instruction_root = project_root if project_root is not None else Path(".")
    return any(part in _TOOL_DIR_NAMES for part in parts) or (
        is_project_instruction_path(
            path,
            instruction_root,
            instruction_paths=instruction_paths,
        )
    )


def is_non_source_path(path: str, *, project_root: Path | None = None) -> bool:
    """True when ``path`` is dummyindex's own footprint, not user source.

    The shared predicate: under ``.context`` or the tool footprint (:func:`_is_tool_path`).
    The reconcile delta, drift report and Stop gate share it, so editing only the index
    or host wiring never counts as drifted code.
    """
    return _is_context_path(path) or _is_tool_path(path, project_root=project_root)


def _matches_any(path: str, globs: tuple[str, ...]) -> bool:
    """True when ``path`` matches any user-configured ``reconcile_exclude`` glob."""
    return any(fnmatch(path, g) for g in globs)


def _reconcile_excludes(context_dir: Path) -> tuple[str, ...]:
    """The user's ``reconcile_exclude`` globs from ``.context/config.json``.

    Empty when there's no config, the field is absent, or the config is
    malformed — the exclusion is a convenience knob, never a hard dependency,
    so a bad config must not crash the read-only report.
    """
    try:
        cfg = read_config(context_dir)
    except ConfigError:
        return ()
    return cfg.reconcile_exclude if cfg is not None else ()
