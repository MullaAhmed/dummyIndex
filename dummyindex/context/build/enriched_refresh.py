# non-destructive refresh: deterministic artefacts only; never touches enrichment
"""Refresh the enrichment-free artefacts of an already-enriched index.

A full ``build_all`` would re-cluster a curated index and overwrite the council's
taxonomy and docs (silent data loss). This rewrites only deterministic output: maps,
``conventions/naming.*``, ``source-docs/INDEX.*``, the symbol graph and its roll-ups,
tree, meta, coverage and mechanical summary sections. ``features/INDEX.json``, feature
docs, ``features/graph.json`` and council convention docs are never rewritten.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from dummyindex.context.build.common import (
    cache_dir_override,
    collect_doc_paths,
    newest_mtime,
    normalize_written_eof_newlines,
)
from dummyindex.context.build.conventions import (
    analyze_naming,
    write_naming_json,
    write_naming_md,
)
from dummyindex.context.build.coverage import write_coverage
from dummyindex.context.build.graph import build_graph
from dummyindex.context.build.maps import (
    FilesMap,
    SymbolsMap,
    files_map_from_paths,
    symbols_map_from_structure,
    write_files_map,
    write_symbols_map,
)
from dummyindex.context.build.meta import (
    SCHEMA_VERSION,
    read_meta,
    write_meta,
)
from dummyindex.context.build.navigation_refresh import refresh_summaries, refresh_tree
from dummyindex.context.build.upgrade import LayoutMigration, migrate_context_layout
from dummyindex.context.domains.source_docs import (
    DocCatalog,
    build_doc_catalog,
    harvest_json_keys,
    write_catalog,
)
from dummyindex.pipeline.build import build_structure
from dummyindex.pipeline.extract import extract
from dummyindex.pipeline.io.detect import detect
from dummyindex.versioning import VersionOrder, compare_versions, parse_version

# Artefacts whose failure holds the version stamp back. The derived graph
# roll-ups (seed-rank, communities) stay best-effort.
_CATALOG_ARTIFACT = "source-docs/INDEX.json"
_GRAPH_ARTIFACT = "features/symbol-graph.json"


@dataclass(frozen=True)
class RefreshResult:
    """What the non-destructive refresh wrote, migrated, and failed to write.

    ``failed`` holds ``(artifact, error)`` for each required artefact that
    could not be written; when it is non-empty the version stamp was not
    advanced. ``migration`` is the context-layout migration's outcome.
    """

    context_dir: Path
    written: tuple[str, ...]
    migration: LayoutMigration = LayoutMigration()
    failed: tuple[tuple[str, str], ...] = ()


def refresh_deterministic_artifacts(
    root: Path,
    *,
    cache_root: Path | None = None,
    extra_doc_roots: Sequence[Path] = (),
    dummyindex_version: str | None = None,
    allow_downgrade: bool = False,
) -> RefreshResult:
    """Refresh only the enrichment-free artefacts under ``root/.context/``.

    Migrates the layout first (it scopes the extraction cache to ``dummyindex_version``),
    then writes the tree before the maps (it diffs the old ``map/files.json`` to flag
    stale annotations). Meta keeps ``indexed_commit`` (:func:`_refresh_meta`) and the
    version stamp moves last (:func:`_advance_version_stamp`). A missing anchor commit
    drops a ``.pending-enrichment`` marker into every feature.
    """
    root = root.resolve()
    context_dir = root / ".context"
    cache = (cache_root or root).resolve()
    cache_target = context_dir / "cache"
    from .scope import scan_root

    scope = scan_root(root)
    # `scan_root` validated the destination. Migrate BEFORE extraction (the
    # cache scope drops other versions' entries). The cache dir exists first so
    # a context without one is stamped now; otherwise this run's entries go
    # unstamped and the next refresh discards them. Never raises.
    cache_target.mkdir(parents=True, exist_ok=True)
    migration = migrate_context_layout(context_dir, package_version=dummyindex_version)
    failed: list[tuple[str, str]] = []

    with cache_dir_override(cache_target):
        detection = detect(scope, extra_doc_roots=tuple(extra_doc_roots))
        code_files = [Path(p) for p in detection.get("files", {}).get("code", [])]
        extraction = extract(code_files, cache_root=cache)
        from dummyindex.context.build.portable_graph import normalize_extraction_paths

        extraction = normalize_extraction_paths(extraction, root)
        structure = build_structure(extraction, code_files, root, include_extras=False)

        files_map = files_map_from_paths(code_files, root)
        symbols_map = symbols_map_from_structure(structure, root)
        rules = analyze_naming(files_map, symbols_map)

        written: list[str] = []

        refresh_tree(context_dir, structure, root, files_map)
        written.append("tree.json")

        write_files_map(context_dir / "map" / "files.json", files_map)
        written.append("map/files.json")
        write_symbols_map(context_dir / "map" / "symbols.json", symbols_map)
        written.append("map/symbols.json")
        write_coverage(
            context_dir,
            files_map,
            symbols_map,
            detection=detection,
            extraction=extraction,
        )
        written.append("coverage.json")

        write_naming_json(context_dir / "conventions" / "naming.json", rules)
        written.append("conventions/naming.json")

        doc_catalog = _build_doc_catalog(
            detection, root, files_map, symbols_map, code_files, extra_doc_roots
        )

        # Counts/root/languages/updated_at now; the version stamp moves last, below.
        # naming.md reuses this updated_at as its generated-at stamp.
        _, updated_at = _refresh_meta(
            context_dir,
            file_count=len(files_map.files),
            symbol_count=len(symbols_map.symbols),
            root=root,
            languages=tuple(
                sorted({f.language for f in files_map.files if f.language})
            ),
        )

        try:
            write_catalog(context_dir, doc_catalog)
            written.append(_CATALOG_ARTIFACT)
            written.append("source-docs/INDEX.md")
        except Exception as exc:  # mirror build_all's tolerance, but report it
            warnings.warn(f"source-docs catalog refresh failed: {exc!r}", stacklevel=2)
            failed.append((_CATALOG_ARTIFACT, repr(exc)))

        try:
            graph_result = build_graph(extraction, context_dir / "features", root=root)
            written.append(_GRAPH_ARTIFACT)
            written.extend(graph_result.artifacts)
        except Exception as exc:
            warnings.warn(f"symbol-graph refresh failed: {exc!r}", stacklevel=2)
            failed.append((_GRAPH_ARTIFACT, repr(exc)))

        if not failed:
            _advance_version_stamp(
                context_dir, dummyindex_version, allow_downgrade=allow_downgrade
            )

        # Summaries read meta *after* the stamp so PROJECT.md's
        # "dummyIndex version" line matches the stored stamp.
        try:
            summary_meta = read_meta(context_dir / "meta.json")
        except (OSError, ValueError):
            summary_meta = None
        if summary_meta is not None:
            refresh_summaries(
                context_dir,
                root,
                summary_meta,
                files_map,
                symbols_map,
                doc_catalog,
            )
            written.extend(("PROJECT.md", "architecture/overview.md"))
        write_naming_md(
            context_dir / "conventions" / "naming.md", rules, generated_at=updated_at
        )
        written.append("conventions/naming.md")

    # Same byte-level hygiene contract as build_all: refreshed artifacts
    # are committed, so they must stay pre-commit-clean (one EOF newline).
    normalize_written_eof_newlines(context_dir, written)

    # Unknown source basis requires an explicit feature review before re-anchor.
    from .git_delta import commit_exists

    try:
        meta = read_meta(context_dir / "meta.json")
    except (OSError, ValueError):
        meta = None
    if (
        meta
        and meta.indexed_commit
        and commit_exists(root, meta.indexed_commit) is False
    ):
        from dummyindex.context.domains.atomic_io import write_text_atomic

        for feature in (context_dir / "features").glob("*/feature.json"):
            marker = feature.parent / ".pending-enrichment"
            if not marker.exists():
                write_text_atomic(
                    marker,
                    "Recheck current source: prior index anchor is unavailable.\n",
                )

    return RefreshResult(
        context_dir=context_dir,
        written=tuple(written),
        migration=migration,
        failed=tuple(failed),
    )


def _build_doc_catalog(
    detection: dict,
    root: Path,
    files_map: FilesMap,
    symbols_map: SymbolsMap,
    code_files: list[Path],
    extra_doc_roots: Sequence[Path],
) -> DocCatalog:
    """Rebuild the source-docs catalog from the current scan.

    Mirrors the catalog inputs ``build_all`` assembles, restricted to what
    the deterministic refresh needs (no PROJECT.md / overview side-effects).
    """
    doc_paths = collect_doc_paths(detection, root, extra_doc_roots)
    newest_code_mtime = newest_mtime(code_files)
    symbol_names = frozenset(s.name for s in symbols_map.symbols)
    file_paths_set = frozenset(f.path for f in files_map.files)
    json_repo_paths = [
        Path(raw)
        for raw in (detection.get("files", {}) or {}).get("code", [])
        if Path(raw).suffix.lower() == ".json"
    ]
    extra_names = harvest_json_keys(json_repo_paths)
    return build_doc_catalog(
        doc_paths,
        repo_root=root,
        symbol_names=symbol_names,
        file_paths=file_paths_set,
        newest_code_mtime=newest_code_mtime,
        extra_doc_roots=tuple(extra_doc_roots),
        extra_names=extra_names,
    )


def _refresh_meta(
    context_dir: Path,
    *,
    file_count: int,
    symbol_count: int,
    root: Path | None = None,
    languages: tuple[str, ...] | None = None,
) -> tuple[Path, str]:
    """Re-stamp ``meta.json``: counts, ``updated_at``, and ``root="."``/``languages`` if given.

    ``indexed_commit`` is kept: it is the last *reconcile* anchor, moved only by ingest
    or ``reconcile-stamp``, and advancing it here would silently forget every change
    since. ``dummyindex_version``/``schema_version`` move in :func:`_advance_version_stamp`.
    Returns ``(path, updated_at)``; ``updated_at`` is ``""`` if meta is missing/unreadable.
    """
    meta_path = context_dir / "meta.json"
    if not meta_path.is_file():
        return meta_path, ""
    try:
        meta = read_meta(meta_path)
    except (ValueError, json.JSONDecodeError, OSError):
        return meta_path, ""
    changes: dict[str, object] = {
        "file_count": file_count,
        "symbol_count": symbol_count,
    }
    if root is not None:
        changes["root"] = "."
    if languages is not None:
        changes["languages"] = languages
    updated = meta.with_updates(**changes)
    write_meta(meta_path, updated)
    return meta_path, updated.updated_at


def _advance_version_stamp(
    context_dir: Path, version: str | None, *, allow_downgrade: bool
) -> bool:
    """Last write of the refresh: stamp ``meta.json`` with ``version`` and the schema.

    Called only once every required artefact was written, so a failed refresh keeps the
    old stamp. No-op when ``version`` is ``None`` or meta is missing/unreadable. The schema
    becomes :data:`SCHEMA_VERSION` even at an equal version. The version moves when the
    stored one is older or unparseable, or on ``allow_downgrade``; an unparseable
    ``version`` never moves it. ``replace`` keeps ``updated_at``. True if the version moved.
    """
    if version is None:
        return False
    meta_path = context_dir / "meta.json"
    if not meta_path.is_file():
        return False
    try:
        meta = read_meta(meta_path)
    except (ValueError, json.JSONDecodeError, OSError):
        return False
    stored = meta.dummyindex_version
    parses = parse_version(version) is not None
    advance = stored != version and (
        compare_versions(stored, version) is VersionOrder.OLDER
        or (parse_version(stored) is None and parses)
        or (allow_downgrade and parses)
    )
    target = version if advance else stored
    if target == stored and meta.schema_version == SCHEMA_VERSION:
        return False
    write_meta(
        meta_path,
        replace(meta, dummyindex_version=target, schema_version=SCHEMA_VERSION),
    )
    return advance
