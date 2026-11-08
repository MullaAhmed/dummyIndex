"""Deterministic, atomic placement ops: scaffold/assign/unassign/remove features.

Fold files into the curated taxonomy WITHOUT re-clustering: inputs become
repo-relative POSIX, ``members`` come from ``map/symbols.json``, the hand-kept
``INDEX.json`` is edited and ``INDEX.md`` + ``graph.{json,html}`` regenerated.
All validation precedes the first write; failures raise ``FeatureRenameError``
(CLI exit 2). assign/unassign never rewrite enriched spec/plan/concerns docs.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from dummyindex.pipeline.enums import ConfidenceLevel

from .constants import PENDING_ENRICHMENT_MARKER, SCHEMA_VERSION
from .errors import FeatureRenameError
from .helpers import _rmtree, _validate_feature_id, _write_json, _write_text
from .indexes import (
    _load_symbols_map,
    rebuild_features_graph,
    refresh_features_index_md,
)
from .models import Feature, PlacementResult, RemoveResult
from .render import _stub_feature_spec

# ``community-*`` ids are reserved for deterministic clustering; the council
# must never hand-scaffold one (it would collide with a future re-cluster and
# muddy the curated-vs-deterministic distinction).
_RESERVED_ID_PREFIX = "community-"


def scaffold_feature(
    features_dir: Path,
    *,
    repo_root: Path,
    feature_id: str,
    name: str,
    files: Iterable[Path],
    summary: str | None = None,
) -> PlacementResult:
    """Create a new ``features/<feature_id>/`` folder for net-new ``files``.

    Writes ``feature.json`` (members derived from ``map/symbols.json``, no
    entry points or flows, ``EXTRACTED``), a stub ``spec.md``, the pending-
    enrichment marker and, on catalog matches, ``docs.md``; then indexes it.
    Raises ``FeatureRenameError`` when the id exists or is reserved
    (``community-*``), no files are given, or a file is missing/outside the repo.
    """
    features_dir = features_dir.resolve()
    repo_root = repo_root.resolve()

    feature_id = _validate_placement_id(feature_id)
    feat_dir = features_dir / feature_id
    if feat_dir.exists():
        raise FeatureRenameError(
            f"feature id {feature_id!r} already exists at {feat_dir}; "
            "pick a different --id or use `assign-files`"
        )

    rel_files = _normalize_files(files, repo_root)

    members = _members_for_files(features_dir, rel_files)

    feature = Feature(
        feature_id=feature_id,
        kind="community",
        name=name,
        summary=summary,
        members=members,
        files=rel_files,
        entry_points=(),
        flow_ids=(),
        confidence=ConfidenceLevel.EXTRACTED,
    )

    # --- writes (everything above validated)
    feat_dir.mkdir(parents=True, exist_ok=True)
    touched: list[str] = []

    _write_json(feat_dir / "feature.json", feature.to_dict())
    touched.append(f"features/{feature_id}/feature.json")

    _write_text(feat_dir / "spec.md", _stub_feature_spec(feature, []))
    touched.append(f"features/{feature_id}/spec.md")

    touched.append(_write_pending_marker(feat_dir, feature_id))

    docs_written = _write_docs_md(features_dir, repo_root, feature)
    touched.extend(docs_written)

    _append_index_entry(features_dir, feature)
    touched.append("features/INDEX.json")
    touched.extend(_refresh_index_artifacts(features_dir))

    return PlacementResult(
        feature_id=feature_id,
        created=True,
        files=rel_files,
        members=members,
        files_touched=tuple(touched),
    )


def assign_files(
    features_dir: Path,
    *,
    repo_root: Path,
    feature_id: str,
    files: Iterable[Path],
) -> PlacementResult:
    """Add ``files`` to an existing ``features/<feature_id>/feature.json``.

    Recomputes ``members`` over the union of old + new files, updates INDEX
    counts, re-drops the pending-enrichment marker and regenerates INDEX.md +
    graph. Already-assigned files are skipped silently. Raises
    ``FeatureRenameError`` when the feature doesn't exist, no files are given,
    or a file is missing/outside the repo.
    """
    features_dir = features_dir.resolve()
    repo_root = repo_root.resolve()

    feat_dir = features_dir / feature_id
    feature_json = feat_dir / "feature.json"
    if not feature_json.is_file():
        raise FeatureRenameError(
            f"feature {feature_id!r} not found at {feat_dir}; "
            "scaffold it first with `scaffold-feature`"
        )

    rel_files = _normalize_files(files, repo_root)

    payload = json.loads(feature_json.read_text(encoding="utf-8"))
    existing = list(payload.get("files", []))
    merged_files = tuple(sorted({*existing, *rel_files}))
    members = _members_for_files(features_dir, merged_files)

    # --- writes (everything above validated)
    touched: list[str] = []
    payload["files"] = list(merged_files)
    payload["members"] = list(members)
    _write_json(feature_json, payload)
    touched.append(f"features/{feature_id}/feature.json")

    touched.append(_write_pending_marker(feat_dir, feature_id))

    _update_index_counts(
        features_dir,
        feature_id,
        file_count=len(merged_files),
        member_count=len(members),
    )
    touched.append("features/INDEX.json")
    touched.extend(_refresh_index_artifacts(features_dir))

    return PlacementResult(
        feature_id=feature_id,
        created=False,
        files=merged_files,
        members=members,
        files_touched=tuple(touched),
    )


def unassign_files(
    features_dir: Path,
    *,
    repo_root: Path,
    feature_id: str,
    files: Iterable[Path],
) -> PlacementResult:
    """Remove ``files`` from an existing ``features/<feature_id>/feature.json``.

    Inverse of ``assign_files`` for deleted/moved files: recomputes members,
    updates INDEX and re-drops the pending marker. Files need **not** exist;
    unowned paths are skipped. Raises ``FeatureRenameError`` when the feature
    is missing, no files are given, a file is outside the repo, or none would
    remain (use ``features-remove`` rather than strand an empty feature).
    """
    features_dir = features_dir.resolve()
    repo_root = repo_root.resolve()

    feat_dir = features_dir / feature_id
    feature_json = feat_dir / "feature.json"
    if not feature_json.is_file():
        raise FeatureRenameError(
            f"feature {feature_id!r} not found at {feat_dir}; nothing to unassign"
        )

    rel_drop = _normalize_for_removal(files, repo_root)

    payload = json.loads(feature_json.read_text(encoding="utf-8"))
    existing = list(payload.get("files", []))
    drop = set(rel_drop)
    remaining = tuple(p for p in existing if p not in drop)
    if existing and not remaining:
        raise FeatureRenameError(
            f"unassigning these files would leave {feature_id!r} with no files; "
            "delete the feature with `features-remove` instead of stranding it"
        )
    members = _members_for_files(features_dir, remaining)

    # --- writes (everything above validated)
    touched: list[str] = []
    payload["files"] = list(remaining)
    payload["members"] = list(members)
    _write_json(feature_json, payload)
    touched.append(f"features/{feature_id}/feature.json")

    touched.append(_write_pending_marker(feat_dir, feature_id))

    _update_index_counts(
        features_dir,
        feature_id,
        file_count=len(remaining),
        member_count=len(members),
    )
    touched.append("features/INDEX.json")
    touched.extend(_refresh_index_artifacts(features_dir))

    return PlacementResult(
        feature_id=feature_id,
        created=False,
        files=remaining,
        members=members,
        files_touched=tuple(touched),
    )


def remove_feature(
    features_dir: Path,
    *,
    feature_id: str,
    repo_root: Path,
    force: bool = False,
) -> RemoveResult:
    """Delete a feature whose code is gone — folder + index entries.

    Removes the folder (enriched docs and flows included) and its INDEX entry
    (decrementing ``flow_count``), then regenerates INDEX.md + graph. **Safety
    guard:** raises ``FeatureRenameError`` when the feature still owns files on
    disk (live code) or its ``feature.json`` is unreadable (broken, not dead);
    ``force=True`` overrides both. Also raises on a missing folder or non-slug id.
    """
    features_dir = features_dir.resolve()
    repo_root = repo_root.resolve()
    # Validate the slug BEFORE deriving feat_dir — an unvalidated id like
    # ``../sibling`` would resolve out of the features tree and let _rmtree
    # delete an out-of-tree directory. _validate_feature_id rejects `.` and `/`.
    feature_id = _validate_feature_id(feature_id)
    feat_dir = features_dir / feature_id
    if not feat_dir.is_dir():
        raise FeatureRenameError(
            f"feature folder {feat_dir} not found; nothing to remove"
        )

    if not force:
        live = _live_files(feat_dir, repo_root)
        if live:
            raise FeatureRenameError(
                f"feature {feature_id!r} still owns {len(live)} file(s) that "
                f"exist on disk (e.g. {live[0]}); it's not dead. Unassign the "
                "removed paths with `unassign-files`, or pass --force to delete "
                "it anyway."
            )

    # --- writes (everything above validated)
    touched: list[str] = []
    if _drop_index_entry(features_dir, feature_id):
        touched.append("features/INDEX.json")

    _rmtree(feat_dir)
    touched.append(f"features/{feature_id}/ (removed)")

    # rebuild_features_graph walks features/<id>/feature.json, so the deleted
    # folder is simply absent; INDEX.md regenerates from the trimmed INDEX.json.
    touched.extend(_refresh_index_artifacts(features_dir))

    return RemoveResult(feature_id=feature_id, files_touched=tuple(touched))


def _live_files(feat_dir: Path, repo_root: Path) -> list[str]:
    """Repo-relative files the feature owns that still exist on disk (sorted).

    **Raises** on a missing/corrupt ``feature.json`` rather than failing open:
    returning ``[]`` would pass the guard and let ``_rmtree`` destroy
    enrichment. ``force=True`` skips the guard, so broken folders stay deletable.
    """
    feature_json = feat_dir / "feature.json"
    try:
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FeatureRenameError(
            f"feature.json at {feature_json} is unreadable or corrupt ({exc}); "
            "this is broken state, not a dead feature. Fix it, or pass --force "
            "to delete the folder anyway."
        ) from exc
    return sorted(
        f
        for f in payload.get("files", []) or []
        if isinstance(f, str) and f and (repo_root / f).is_file()
    )


# --- pending-enrichment marker


def clear_pending_enrichment(features_dir: Path, feature_id: str) -> str | None:
    """Remove a feature's ``.pending-enrichment`` marker (idempotent).

    Called after council (re-)enrichment so ``reconcile-stamp`` can advance.
    Returns the cleared relative path, or ``None`` when there was no marker.
    Raises ``FeatureRenameError`` only when the feature folder is missing.
    """
    features_dir = features_dir.resolve()
    feat_dir = features_dir / feature_id
    if not feat_dir.is_dir():
        raise FeatureRenameError(
            f"feature {feature_id!r} not found at {feat_dir}; nothing to mark enriched"
        )
    marker = feat_dir / PENDING_ENRICHMENT_MARKER
    if not marker.exists():
        return None
    marker.unlink()
    return f"features/{feature_id}/{PENDING_ENRICHMENT_MARKER}"


def _write_pending_marker(feat_dir: Path, feature_id: str) -> str:
    """Drop the pending-enrichment marker into ``feat_dir``; return its rel path."""
    _write_text(
        feat_dir / PENDING_ENRICHMENT_MARKER,
        "Placed by a reconcile op; awaiting council (re-)enrichment.\n"
        "Cleared by `dummyindex context mark-enriched --feature "
        f"{feature_id}`.\n",
    )
    return f"features/{feature_id}/{PENDING_ENRICHMENT_MARKER}"


# --- validation


def _validate_placement_id(value: str) -> str:
    """Slug-validate ``value`` and reject the reserved ``community-*`` space."""
    feature_id = _validate_feature_id(value)
    if feature_id.startswith(_RESERVED_ID_PREFIX):
        raise FeatureRenameError(
            f"feature id {value!r} is reserved: 'community-*' ids belong to "
            "deterministic clustering, not hand-scaffolded features"
        )
    return feature_id


def _normalize_files(files: Iterable[Path], repo_root: Path) -> tuple[str, ...]:
    """Resolve every ``--file`` to a repo-relative POSIX path, sorted + unique.

    Errors on an empty list, a path that isn't a real file, or a path that
    resolves outside ``repo_root`` (so a placement can never point a
    feature at something outside the indexed tree).
    """
    raw = list(files)
    if not raw:
        raise FeatureRenameError("at least one --file is required")

    rel: set[str] = set()
    for f in raw:
        resolved = (f if f.is_absolute() else (repo_root / f)).resolve()
        if not resolved.is_file():
            raise FeatureRenameError(f"--file is not a file: {f}")
        try:
            rel.add(resolved.relative_to(repo_root).as_posix())
        except ValueError:
            raise FeatureRenameError(
                f"--file is not under the repo root {repo_root}: {f}"
            ) from None
    return tuple(sorted(rel))


def _normalize_for_removal(files: Iterable[Path], repo_root: Path) -> tuple[str, ...]:
    """Resolve ``--file`` inputs to repo-relative POSIX, **without** stat'ing.

    The removal counterpart of ``_normalize_files``: a file being unassigned
    has usually been *deleted*, so existence is not required (and not checked).
    Still rejects an empty list and any path that resolves outside the repo
    (``Path.resolve`` normalises a non-existent path without touching disk).
    """
    raw = list(files)
    if not raw:
        raise FeatureRenameError("at least one --file is required")

    rel: set[str] = set()
    for f in raw:
        resolved = (f if f.is_absolute() else (repo_root / f)).resolve()
        try:
            rel.add(resolved.relative_to(repo_root).as_posix())
        except ValueError:
            raise FeatureRenameError(
                f"--file is not under the repo root {repo_root}: {f}"
            ) from None
    return tuple(sorted(rel))


def _members_for_files(
    features_dir: Path, rel_files: tuple[str, ...]
) -> tuple[str, ...]:
    """Symbol ids from ``map/symbols.json`` whose ``path`` is one of ``rel_files``.

    The map is a sibling of ``features/`` (``<context>/map/symbols.json``). An
    absent map (older layouts) yields empty members rather than an error.
    """
    symbols = _load_symbols_map(features_dir.parent / "map" / "symbols.json")
    if not symbols:
        return ()
    file_set = set(rel_files)
    members = {
        sid for sid, payload in symbols.items() if payload.get("path") in file_set
    }
    return tuple(sorted(members))


# --- INDEX.json maintenance (hand-maintained — no disk-rebuild helper)


def _read_index(features_dir: Path) -> dict[str, Any]:
    """Read ``features/INDEX.json``, seeding an empty index when absent."""
    index_path = features_dir / "INDEX.json"
    if index_path.exists():
        return json.loads(index_path.read_text(encoding="utf-8"))
    return {"schema_version": SCHEMA_VERSION, "features": [], "flow_count": 0}


def _append_index_entry(features_dir: Path, feature: Feature) -> None:
    """Append ``feature``'s INDEX.json entry, mirroring ``builder._write_all``."""
    idx = _read_index(features_dir)
    entries = idx.get("features", []) or []
    entries.append(
        {
            "feature_id": feature.feature_id,
            "kind": feature.kind,
            "name": feature.name,
            "summary": feature.summary,
            "member_count": len(feature.members),
            "file_count": len(feature.files),
            "entry_point_count": len(feature.entry_points),
            "flow_count": len(feature.flow_ids),
            "confidence": feature.confidence,
            "path": f"features/{feature.feature_id}/",
        }
    )
    idx["features"] = entries
    idx.setdefault("flow_count", 0)
    _write_json(features_dir / "INDEX.json", idx)


def _update_index_counts(
    features_dir: Path,
    feature_id: str,
    *,
    file_count: int,
    member_count: int,
) -> None:
    """Refresh one feature's file/member counts in INDEX.json (in place)."""
    idx = _read_index(features_dir)
    for entry in idx.get("features", []) or []:
        if entry.get("feature_id") == feature_id:
            entry["file_count"] = file_count
            entry["member_count"] = member_count
    _write_json(features_dir / "INDEX.json", idx)


def _drop_index_entry(features_dir: Path, feature_id: str) -> bool:
    """Remove a feature's INDEX.json entry, decrementing top-level flow_count.

    Returns True when an entry was dropped, False when the feature wasn't in
    the index (idempotent no-op). Mirrors the hand-maintained-INDEX approach of
    ``_append_index_entry`` / ``_update_index_counts`` — no disk rebuild.
    """
    idx = _read_index(features_dir)
    entries = idx.get("features", []) or []
    kept = [e for e in entries if e.get("feature_id") != feature_id]
    if len(kept) == len(entries):
        return False
    dropped_flows = sum(
        int(e.get("flow_count", 0) or 0)
        for e in entries
        if e.get("feature_id") == feature_id
    )
    idx["features"] = kept
    idx["flow_count"] = max(0, int(idx.get("flow_count", 0) or 0) - dropped_flows)
    _write_json(features_dir / "INDEX.json", idx)
    return True


def _refresh_index_artifacts(features_dir: Path) -> list[str]:
    """Regenerate INDEX.md + graph.{json,html} from disk after an INDEX edit.

    Reuses the existing index writers (no re-cluster). Returns the touched
    relative paths for the op's ``files_touched`` report. Tolerates a fresh
    index whose graph isn't built yet.
    """
    touched: list[str] = []
    try:
        refresh_features_index_md(features_dir)
        touched.append("features/INDEX.md")
    except FileNotFoundError:
        pass
    try:
        rebuild_features_graph(features_dir)
        touched.append("features/graph.json")
        touched.append("features/graph.html")
    except FileNotFoundError:
        pass
    return touched


# --- docs.md (conditional, mirrors scaffold_features)


def _write_docs_md(features_dir: Path, repo_root: Path, feature: Feature) -> list[str]:
    """Write ``features/<id>/docs.md`` when the source-docs catalog matches.

    Mirrors ``scaffold_features``: guard on a present, non-empty catalog;
    synthesize the ``node_by_id`` map ``_write_feature_docs`` needs from
    ``map/symbols.json`` (label + source_file per member). Best-effort —
    a missing/unreadable catalog just skips docs.md.
    """
    from dummyindex.context.domains.source_docs import read_catalog

    from .docs import _write_feature_docs

    catalog = read_catalog(features_dir.parent)
    if catalog is None or not catalog.docs:
        return []

    symbols = _load_symbols_map(features_dir.parent / "map" / "symbols.json") or {}
    node_by_id = {
        sid: {"label": payload.get("name", sid), "source_file": payload.get("path")}
        for sid, payload in symbols.items()
    }
    return list(_write_feature_docs(features_dir, (feature,), catalog, node_by_id))
