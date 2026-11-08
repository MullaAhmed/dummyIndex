"""Incremental rebuild: quick-exit when no tracked file has changed.

Hashes every detected source and in-repo doc file against the prior fingerprints
(``map/files.json``, plus ``cache/manifest.json`` for docs) and returns without touching
disk when nothing changed. Docs count because the source-docs catalog's staleness
depends on them. Otherwise a curated index gets the non-destructive refresh and any
other index a full build, which the per-file extraction cache keeps fast.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dummyindex.context.build.enriched_refresh import (
    RefreshResult,
    refresh_deterministic_artifacts,
)
from dummyindex.context.build.reconcile import (
    ReconcileReport,
    compute_reconcile_report,
)
from dummyindex.context.build.runner import BuildResult, build_all
from dummyindex.pipeline.io.cache import file_hash
from dummyindex.pipeline.io.detect import detect
from dummyindex.pipeline.io.paths import resolve_under_root


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
    build_result: BuildResult | None
    # On a curated index ``--changed`` refreshes only deterministic artefacts and
    # reports drift instead of re-clustering; ``refresh_result``/``reconcile`` carry it.
    preserved_enriched: bool = False
    refresh_result: RefreshResult | None = None
    reconcile: ReconcileReport | None = None
    # Curation was found only in the feature dirs while ``features/INDEX.json`` reads
    # deterministic-only, i.e. INDEX.json is out of sync and needs repair.
    index_desync: bool = False


def rebuild_changed(
    root: Path,
    *,
    cache_root: Path | None = None,
    bootstrap: bool = False,
    dummyindex_version: str | None = None,
    extra_doc_roots: Sequence[Path] = (),
    full: bool = False,
) -> IncrementalResult:
    """Detect changed files since the last build; rebuild only if any changed.

    A curated index (a feature not ``community-*``, or ``INFERRED``) is not re-clustered:
    deterministic artefacts refresh, a reconcile report is computed, and
    ``meta.indexed_commit`` stays. ``full=True`` forces the destructive re-cluster (the
    caller must warn). ``dummyindex_version=None`` leaves the stamp and cache scope alone
    on that path; a full build stamps ``"0.0.0"``. External doc roots are not diffed.
    """
    root = root.resolve()
    context_dir = root / ".context"
    files_json = context_dir / "map" / "files.json"
    from .scope import scan_root

    scope = scan_root(root)

    detection = detect(scope, extra_doc_roots=tuple(extra_doc_roots))
    files_dict = detection.get("files", {}) or {}
    current_code = [Path(p) for p in files_dict.get("code", [])]
    # Track in-repo docs in the same fingerprint set as code so README edits
    # trigger rebuilds. External (--docs) paths are not repo-relative so they
    # don't participate in incremental change detection.
    current_docs: list[Path] = []
    for ftype in ("document", "paper"):
        for raw in files_dict.get(ftype, []) or []:
            p = Path(raw)
            if resolve_under_root(p, root) is None:
                continue
            current_docs.append(p)

    current_files = current_code + current_docs
    current_by_path = _hash_files(current_files, root)

    prior_by_path = _read_prior_fingerprints(files_json)
    if prior_by_path is None:
        # Fall back to cache/manifest.json. files.json is git-tracked, but cache/ is
        # gitignored and absent on every fresh clone, so files.json is primary and the
        # manifest backstops installs whose files.json predates the refresh-time writer.
        prior_by_path = _read_prior_fingerprints_via_manifest(context_dir)
    else:
        # files.json tracks code only; the manifest supplies the doc fingerprints
        # underneath, and files.json wins key collisions.
        manifest_fps = _read_prior_fingerprints_via_manifest(context_dir)
        if manifest_fps:
            for fp_path, fp_sha in manifest_fps.items():
                prior_by_path.setdefault(fp_path, fp_sha)

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

    # Non-destructive guard: only an explicit `full` (or a fresh `ingest`) may discard
    # curated taxonomy. The status also flags a desync when the curated dirs survived
    # but INDEX.json was clobbered to deterministic-only stubs.
    status = enriched_index_status(context_dir)
    if not full and status.enriched:
        # The refresh keeps the anchor, so reconcile diffs anchor..HEAD(+worktree) in
        # either call order; computed here so the result carries the drift.
        reconcile = compute_reconcile_report(context_dir, root)
        refresh = refresh_deterministic_artifacts(
            root,
            cache_root=cache_root,
            extra_doc_roots=extra_doc_roots,
            dummyindex_version=dummyindex_version,
        )
        return IncrementalResult(
            skipped=False,
            changes=changes,
            build_result=None,
            preserved_enriched=True,
            refresh_result=refresh,
            reconcile=reconcile,
            index_desync=status.desync,
        )

    result = build_all(
        scope,
        out_root=root,
        cache_root=cache_root,
        bootstrap=bootstrap,
        dummyindex_version=dummyindex_version or "0.0.0",
        extra_doc_roots=extra_doc_roots,
    )
    return IncrementalResult(skipped=False, changes=changes, build_result=result)


@dataclass(frozen=True)
class EnrichedIndexStatus:
    """Whether an on-disk index carries curated/enriched taxonomy.

    ``enriched``: a destructive re-cluster would lose curation, per ``features/INDEX.json``
    OR the per-feature dirs (so a clobbered INDEX.json can't disarm it). ``desync``: the
    dirs prove curation but INDEX.json reads deterministic-only; the caller surfaces it so
    the user repairs INDEX.json instead of relying on the dir-scan rescue.
    """

    enriched: bool
    desync: bool = False


def _feature_entry_is_enriched(feature_id: str, confidence: object) -> bool:
    """A single feature is enriched when its id was renamed off ``community-*``
    or its confidence indicates INFERRED."""
    if feature_id and not feature_id.startswith("community-"):
        return True
    if "INFERRED" in str(confidence):
        return True
    return False


def _index_json_says_enriched(context_dir: Path) -> bool | None:
    """Read ``features/INDEX.json`` only. Never raises.

    ``None``: the file is absent. ``True``: unreadable, corrupt or malformed (bias to
    preserve), or lists ≥1 curated feature. ``False``: parses cleanly and lists only
    ``community-*``/``EXTRACTED`` features, or none.
    """
    index_json = context_dir / "features" / "INDEX.json"
    try:
        raw = index_json.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None  # no index file at all
    except OSError:
        return True  # exists but unreadable → assume enriched, preserve
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return True  # corrupt / merge-conflict markers → preserve
    if not isinstance(payload, dict):
        return True  # malformed top-level → preserve
    features = payload.get("features")
    if not isinstance(features, list):
        return True  # missing / malformed features key → preserve
    for feature in features:
        if not isinstance(feature, dict):
            continue
        if _feature_entry_is_enriched(
            str(feature.get("feature_id") or ""), feature.get("confidence")
        ):
            return True
    return False


def _feature_dirs_say_enriched(context_dir: Path) -> bool:
    """Scan ``features/*/feature.json`` on disk for curated taxonomy. Never raises.

    An INDEX.json re-shattered into ``community-*`` stubs must not disarm the guard
    while curated dirs remain: a dir id off ``community-*``, or ``INFERRED`` confidence,
    proves curation survived. An unreadable or corrupt ``feature.json`` counts as
    enriched (bias to preserve).
    """
    features_dir = context_dir / "features"
    if not features_dir.is_dir():
        return False
    try:
        children = sorted(features_dir.iterdir())
    except OSError:
        return True  # can't list but the dir exists → preserve
    for child in children:
        if not child.is_dir():
            continue
        dir_id = child.name
        # `community-unassigned` is the deterministic catch-all bucket, not
        # curation — treat it like any other `community-*` id.
        if dir_id and not dir_id.startswith("community-"):
            return True
        feature_json = child / "feature.json"
        if not feature_json.is_file():
            continue
        try:
            payload = json.loads(feature_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return True  # corrupt feature.json → preserve
        except OSError:
            return True  # present but unreadable → preserve
        if not isinstance(payload, dict):
            return True
        if _feature_entry_is_enriched(
            str(payload.get("feature_id") or dir_id), payload.get("confidence")
        ):
            return True
    return False


def enriched_index_status(context_dir: Path) -> EnrichedIndexStatus:
    """Full enriched-index verdict: INDEX.json OR the per-feature dirs. Never raises.

    It gates a destructive rebuild, so it biases to preserve: only an absent or provably
    deterministic index returns ``enriched=False``. ``desync=True`` when the dirs prove
    curation but INDEX.json reads deterministic-only, so the caller can warn.
    """
    index_verdict = _index_json_says_enriched(context_dir)
    if index_verdict is True:
        return EnrichedIndexStatus(enriched=True, desync=False)

    dirs_enriched = _feature_dirs_say_enriched(context_dir)
    if dirs_enriched:
        # INDEX.json said absent (None) or deterministic-only (False) but the
        # dirs prove curation survived → enriched, and desync when INDEX.json
        # actively disagreed (deterministic-only, not merely absent).
        return EnrichedIndexStatus(enriched=True, desync=index_verdict is False)

    # Neither INDEX.json nor the dirs show curation.
    return EnrichedIndexStatus(enriched=False, desync=False)


def is_enriched_index(context_dir: Path) -> bool:
    """Public bias-to-preserve guard: True when a destructive rebuild would
    discard curated/enriched taxonomy (from INDEX.json or per-feature dirs).

    See :func:`enriched_index_status` for the full semantics. Never raises.
    """
    return enriched_index_status(context_dir).enriched


# Back-compat private alias — historical white-box callers/tests import this.
def _is_enriched_index(context_dir: Path) -> bool:
    return is_enriched_index(context_dir)


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


def _read_prior_fingerprints(files_json: Path) -> dict[str, str] | None:
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
) -> dict[str, str] | None:
    """Pull doc + code fingerprints from cache/manifest.json.

    The fallback when ``map/files.json`` is absent/unreadable, else the doc-fingerprint
    source (files.json tracks code only). Raw-byte shas equal ``file_hash`` digests for
    docs without frontmatter; frontmatter-bearing files can over-report ``modified``.
    A corrupt or truncated manifest degrades to ``None`` instead of aborting.
    """
    from dummyindex.context.build.manifest import read_manifest

    try:
        manifest = read_manifest(context_dir)
    except (OSError, json.JSONDecodeError, ValueError, KeyError):
        return None
    if manifest is None or not manifest.files:
        return None
    return {path: entry.sha256 for path, entry in manifest.files.items()}


def _diff(prior: dict[str, str], current: dict[str, str]) -> ChangeSet:
    added = tuple(sorted(p for p in current if p not in prior))
    removed = tuple(sorted(p for p in prior if p not in current))
    modified = tuple(
        sorted(p for p in current if p in prior and prior[p] != current[p])
    )
    return ChangeSet(added=added, modified=modified, removed=removed)
