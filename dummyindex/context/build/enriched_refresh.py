# non-destructive refresh: deterministic artefacts only; never touches enrichment
"""Refresh the enrichment-free artefacts of an already-enriched index.

When ``rebuild --changed`` runs against a *curated* index (named or
``INFERRED`` features), a full ``build_all`` would re-run community
detection and overwrite the council's taxonomy + enriched docs — silent
data loss. This module is the non-destructive alternative: it refreshes
**only** the purely-deterministic, enrichment-free artefacts and leaves
everything the council authored untouched.

Refreshed here (deterministic, no judgment):

- ``map/files.json`` / ``map/symbols.json``
- ``conventions/naming.{json,md}`` (the analysed naming rules — **not**
  the council-authored coding-practices / data-access / folder-
  organization / testing docs)
- ``source-docs/INDEX.{json,md}``
- ``features/symbol-graph.json`` (the raw graph; **not**
  ``features/INDEX.json`` or per-feature folders, which ``scaffold_features``
  owns)

Never touched: ``features/INDEX.json``, per-feature folders, any
``features/<id>/spec.md``, ``tree.json`` (preserves enriched abstracts),
and the council ``conventions/*.md``.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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
from dummyindex.context.build.graph import build_graph
from dummyindex.context.build.maps import (
    FilesMap,
    SymbolsMap,
    files_map_from_paths,
    symbols_map_from_structure,
    write_files_map,
    write_symbols_map,
)
from dummyindex.context.build.meta import read_meta, write_meta
from dummyindex.context.domains.source_docs import (
    DocCatalog,
    build_doc_catalog,
    harvest_json_keys,
    write_catalog,
)
from dummyindex.pipeline.build import build_structure
from dummyindex.pipeline.extract import extract
from dummyindex.pipeline.io.detect import detect


@dataclass(frozen=True)
class RefreshResult:
    """What the non-destructive refresh wrote."""

    context_dir: Path
    written: tuple[str, ...]


def refresh_deterministic_artifacts(
    root: Path,
    *,
    cache_root: Path | None = None,
    extra_doc_roots: Sequence[Path] = (),
    dummyindex_version: str | None = None,
) -> RefreshResult:
    """Refresh only the enrichment-free artefacts under ``root/.context/``.

    Re-stamps ``meta.json``'s ``updated_at`` + ``file_count`` / ``symbol_count``
    to the freshly-derived totals, but **never touches ``indexed_commit``**.
    Under the commit-anchored model (Model B) the anchor is the commit the
    index was last *reconciled* against — it advances only on ingest (the
    floor) or a council ``reconcile-stamp``, never on a deterministic refresh.
    Advancing it here would silently forget every change since the last
    reconcile. All other meta fields are preserved.

    ``dummyindex_version``, when given, advances ``meta.dummyindex_version`` to
    the running version — so a healthy curated index stops showing a stale
    stamp forever after a CLI upgrade, *without* a destructive rebuild. The
    field's semantics: "the dummyindex version that last wrote or refreshed
    this index." ``None`` preserves the existing stamp (backward compatible).
    """
    root = root.resolve()
    context_dir = root / ".context"
    cache = (cache_root or root).resolve()
    cache_target = context_dir / "cache"

    with cache_dir_override(cache_target):
        detection = detect(root, extra_doc_roots=tuple(extra_doc_roots))
        code_files = [Path(p) for p in detection.get("files", {}).get("code", [])]
        extraction = extract(code_files, cache_root=cache)
        structure = build_structure(
            extraction, code_files, root, include_extras=False
        )

        files_map = files_map_from_paths(code_files, root)
        symbols_map = symbols_map_from_structure(structure, root)
        rules = analyze_naming(files_map, symbols_map)

        written: list[str] = []

        write_files_map(context_dir / "map" / "files.json", files_map)
        written.append("map/files.json")
        write_symbols_map(context_dir / "map" / "symbols.json", symbols_map)
        written.append("map/symbols.json")

        write_naming_json(context_dir / "conventions" / "naming.json", rules)
        written.append("conventions/naming.json")

        doc_catalog = _build_doc_catalog(
            detection, root, files_map, symbols_map, code_files, extra_doc_roots
        )

        # Naming md needs a generated-at stamp; reuse meta's updated_at via
        # the refreshed meta below, but write it now with the catalog ready.
        # Pass the fresh counts so meta's file_count/symbol_count don't go
        # stale after files/symbols are re-derived above.
        _, updated_at = _refresh_meta(
            context_dir,
            file_count=len(files_map.files),
            symbol_count=len(symbols_map.symbols),
            dummyindex_version=dummyindex_version,
        )
        write_naming_md(
            context_dir / "conventions" / "naming.md", rules, generated_at=updated_at
        )
        written.append("conventions/naming.md")

        try:
            write_catalog(context_dir, doc_catalog)
            written.append("source-docs/INDEX.json")
            written.append("source-docs/INDEX.md")
        except Exception as exc:  # mirror build_all's tolerance
            warnings.warn(f"source-docs catalog refresh failed: {exc!r}")

        try:
            build_graph(extraction, context_dir / "features")
            written.append("features/symbol-graph.json")
        except Exception as exc:
            warnings.warn(f"symbol-graph refresh failed: {exc!r}")

    # Same byte-level hygiene contract as build_all: refreshed artifacts
    # are committed, so they must stay pre-commit-clean (one EOF newline).
    normalize_written_eof_newlines(context_dir, written)

    return RefreshResult(context_dir=context_dir, written=tuple(written))


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
    dummyindex_version: str | None = None,
) -> tuple[Path, str]:
    """Re-stamp ``meta.json`` with a fresh ``updated_at`` + the new counts.

    Updates ``file_count`` / ``symbol_count`` to the freshly-derived totals so
    they don't go stale after a deterministic refresh, and refreshes
    ``updated_at``. **Deliberately leaves ``indexed_commit`` untouched** —
    ``with_updates`` preserves any field not passed, so the reconcile anchor
    stays put (Model B; see the module docstring). When ``dummyindex_version``
    is given and differs from the stored stamp, it advances
    ``dummyindex_version`` too — the only non-destructive way to unfreeze a
    stale version stamp on a curated index. Returns the path and the new
    ``updated_at`` (so the naming.md stamp matches). If meta is missing or
    unreadable, nothing is stamped and the empty string is returned for
    ``updated_at``.
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
    if dummyindex_version is not None and dummyindex_version != meta.dummyindex_version:
        changes["dummyindex_version"] = dummyindex_version
    updated = meta.with_updates(**changes)
    write_meta(meta_path, updated)
    return meta_path, updated.updated_at
