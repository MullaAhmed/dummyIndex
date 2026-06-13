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
    # Non-destructive enriched path (Phase 1): when the on-disk index is
    # curated/enriched, ``--changed`` refreshes only deterministic artefacts
    # and reports drift instead of re-clustering. ``preserved_enriched`` is
    # True in that case; ``refresh_result`` / ``reconcile`` carry the detail.
    preserved_enriched: bool = False
    refresh_result: Optional[RefreshResult] = None
    reconcile: Optional[ReconcileReport] = None
    # True when the curated taxonomy was detected only via the on-disk
    # feature dirs while ``features/INDEX.json`` reads deterministic-only —
    # i.e. INDEX.json is broken / out of sync and needs repair.
    index_desync: bool = False


def rebuild_changed(
    root: Path,
    *,
    cache_root: Optional[Path] = None,
    bootstrap: bool = False,
    dummyindex_version: str = "0.0.0",
    extra_doc_roots: Sequence[Path] = (),
    full: bool = False,
) -> IncrementalResult:
    """Detect changed files since the last build; rebuild only if any changed.

    ``extra_doc_roots`` are forwarded to ``build_all`` so a rebuild
    preserves whatever external doc locations the original ingest used.
    They don't influence the change-detection itself (which fingerprints
    code files); they only matter once a rebuild actually fires.

    **Non-destructive by default (Phase 1).** When the on-disk index is
    *enriched/curated* (≥1 feature whose id isn't ``community-*`` or whose
    confidence is ``INFERRED``), a change does **not** trigger a full
    ``build_all`` — that would re-run community detection and clobber the
    council's taxonomy + enriched docs. Instead only the deterministic,
    enrichment-free artefacts are refreshed and a reconcile report is
    computed. The reconcile anchor (``meta.indexed_commit``) is **not**
    advanced here — it tracks the last *reconcile*, and only a council
    ``reconcile-stamp`` (or a fresh ingest) moves it (Model B). A
    deterministic-only index (all ``community-*``/``EXTRACTED``) has nothing
    enriched to lose, so it still full-builds.

    ``full=True`` forces the old full re-cluster regardless — the caller is
    responsible for warning that it discards curated taxonomy + enrichment.
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

    # Non-destructive guard: an enriched/curated index must never be
    # re-clustered or re-stubbed by `--changed`. Only an explicit `full`
    # (or a fresh `ingest`) may discard curated taxonomy. The status also
    # reports a desync when the curated dirs survived but INDEX.json was
    # clobbered to deterministic-only stubs.
    status = enriched_index_status(context_dir)
    if not full and status.enriched:
        # The refresh leaves ``meta.indexed_commit`` untouched (Model B), so
        # reconcile always diffs the persisted anchor..HEAD(+worktree) and
        # captures committed drift regardless of call order. Computed here so
        # the result carries the drift for the caller to surface.
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
        root,
        cache_root=cache_root,
        bootstrap=bootstrap,
        dummyindex_version=dummyindex_version,
        extra_doc_roots=extra_doc_roots,
    )
    return IncrementalResult(skipped=False, changes=changes, build_result=result)


@dataclass(frozen=True)
class EnrichedIndexStatus:
    """Whether an on-disk index carries curated/enriched taxonomy.

    - ``enriched``: True when *anything* curated would be lost by a
      destructive re-cluster — read from ``features/INDEX.json`` OR the
      per-feature dirs on disk (so a clobbered INDEX.json can't disarm it).
    - ``desync``: True when the on-disk feature dirs prove the index is
      enriched but ``features/INDEX.json`` itself looks deterministic-only —
      i.e. INDEX.json is broken/out of sync with the curated dirs. The
      caller surfaces this so the user repairs INDEX.json instead of relying
      on the silent dir-scan rescue forever.
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


def _index_json_says_enriched(context_dir: Path) -> Optional[bool]:
    """Read ``features/INDEX.json`` only. Returns:

    - ``None`` when the index is genuinely absent (nothing to lose there).
    - ``True`` when INDEX.json is unreadable/corrupt/malformed (bias to
      preserve) OR lists ≥1 curated feature.
    - ``False`` when INDEX.json parses cleanly and lists only
      ``community-*`` / ``EXTRACTED`` features (or is explicitly empty).

    Never raises.
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
    """Scan ``features/*/feature.json`` on disk for curated taxonomy.

    A clobbered ``features/INDEX.json`` (re-shattered to ``community-*``
    stubs) must NOT disarm the guard while the curated per-feature dirs are
    still on disk. Any dir whose id isn't ``community-*`` — or whose
    ``feature.json`` carries INFERRED confidence — proves curation survived.
    Cheap: one glob, reading only ``feature_id`` + ``confidence``. Biases to
    preserve: an unreadable/corrupt ``feature.json`` counts as enriched.
    Never raises.
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
    """Full enriched-index verdict: INDEX.json OR the per-feature dirs.

    This gates a *destructive* full rebuild, so it **biases to preserve**:
    when the index might be enriched but we can't prove it isn't, return
    ``enriched=True`` (keep the curated taxonomy). Only a genuinely-absent or
    provably-empty index returns ``enriched=False``.

    The dir-scan closes the self-disarm hole: once ``features/INDEX.json``
    has been re-shattered into ``community-*`` stubs, the curated per-feature
    directories still on disk keep the guard armed. When the dir-scan proves
    enriched but INDEX.json reads deterministic-only, ``desync=True`` flags
    the broken INDEX.json so the caller can warn.

    Never raises.
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
