"""End-to-end .context/ build pipeline.

Single detect → extract → build_structure pass feeds every downstream writer,
so `dummyindex context init` doesn't re-walk the repo for each artifact.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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
from dummyindex.context.build.git_delta import head_commit
from dummyindex.context.build.graph import GraphResult, build_graph
from dummyindex.context.build.manifest import write_manifest
from dummyindex.context.build.maps import (
    FilesMap,
    SymbolsMap,
    files_map_from_paths,
    symbols_map_from_structure,
    write_files_map,
    write_symbols_map,
)
from dummyindex.context.build.meta import Meta, new_meta, write_meta
from dummyindex.context.build.tree import Tree, tree_from_structure, write_tree

# The managed-file helpers moved to `upgrade` (the one context-layout
# migration); the names stay importable from `runner`.
from dummyindex.context.build.upgrade import (
    _CONTEXT_GITATTRIBUTES_HEADER,  # noqa: F401 - re-exported for existing importers
    _CONTEXT_GITIGNORE_HEADER,  # noqa: F401 - re-exported for existing importers
    _MANAGED_GITATTRIBUTES_RULES,  # noqa: F401 - re-exported for existing importers
    _MANAGED_GITIGNORE_PATTERNS,  # noqa: F401 - re-exported for existing importers
    LayoutMigration,
    _context_gitignore_body,  # noqa: F401 - re-exported for existing importers
    _ensure_managed_lines,  # noqa: F401 - re-exported for existing importers
    ensure_context_gitattributes,  # noqa: F401 - re-exported for existing importers
    ensure_context_gitignore,  # noqa: F401 - re-exported for existing importers
    migrate_context_layout,
    remove_legacy_enrich_plan,  # noqa: F401 - re-exported for existing importers
)
from dummyindex.context.domains.features import scaffold_features
from dummyindex.context.domains.source_docs import (
    DocCatalog,
    build_doc_catalog,
    harvest_json_keys,
    write_catalog,
)
from dummyindex.context.output.claude_md import reconcile_claude_md
from dummyindex.context.output.docs import (
    generate_index_md,
    generate_project_md,
    write_index_md,
    write_project_md,
)
from dummyindex.context.output.instructions import (
    PLAYBOOK_IDS,
    write_architecture_overview_md,
    write_how_to_use_md,
    write_playbook_md,
)
from dummyindex.pipeline.build import build_structure
from dummyindex.pipeline.extract import extract
from dummyindex.pipeline.io.detect import detect


@dataclass(frozen=True)
class BuildResult:
    root: Path
    context_dir: Path
    file_count: int
    symbol_count: int
    languages: tuple[str, ...]
    written: tuple[str, ...]
    bootstrapped: bool
    graph: GraphResult | None = None
    doc_catalog: DocCatalog | None = None
    migration: LayoutMigration = LayoutMigration()


def build_all(
    scope: Path,
    *,
    out_root: Path | None = None,
    cache_root: Path | None = None,
    bootstrap: bool = False,
    dummyindex_version: str = "0.0.0",
    extra_doc_roots: Sequence[Path] = (),
) -> BuildResult:
    """Run the full .context/ build and write every artifact atomically.

    ``scope`` is the directory scanned for code. ``out_root`` (default ``scope``) is where
    `.context/` and `.claude/CLAUDE.md` go; pass a parent of ``scope`` to index a
    subdirectory at the repo root. Artifact paths are relative to ``out_root``, so
    scanning `/repo/app` from `/repo` yields `app/utils.py`. Returns a BuildResult with
    what was written and the counts.
    """
    scope = scope.resolve()
    out_root = (out_root or scope).resolve()
    from .scope import scan_root

    scope = scan_root(out_root, scope)
    context_dir = out_root / ".context"
    cache = (cache_root or out_root).resolve()

    # Pin the per-file extraction cache to .context/cache/ via the trusted in-process
    # override (cache_dir_override, not the env var), whatever cache root the caller gave.
    cache_target = context_dir / "cache"

    # Migrate an older .context/ forward BEFORE extraction (`scan_root` validated the
    # destination): the cache scope deletes entries stamped by another version, so running
    # it later would wipe this build's entries. The cache dir exists first so a fresh repo
    # is stamped now. Never raises; failures land in `migration.errors`.
    cache_target.mkdir(parents=True, exist_ok=True)
    migration = migrate_context_layout(context_dir, package_version=dummyindex_version)

    with cache_dir_override(cache_target):
        detection = detect(scope, extra_doc_roots=tuple(extra_doc_roots))
        code_files = [Path(p) for p in detection.get("files", {}).get("code", [])]
        extraction = extract(code_files, cache_root=cache)
        from dummyindex.context.build.portable_graph import normalize_extraction_paths

        extraction = normalize_extraction_paths(extraction, out_root)
        # Use out_root as the base for relative paths so the structure tree
        # (and everything derived from it) reads correctly from the .context/
        # location.
        structure = build_structure(
            extraction, code_files, out_root, include_extras=False
        )

    files_map = files_map_from_paths(code_files, out_root)
    symbols_map = symbols_map_from_structure(structure, out_root)
    tree = tree_from_structure(structure, out_root)
    rules = analyze_naming(files_map, symbols_map)

    languages = _derive_languages(files_map)
    meta_config = {
        "extra_doc_roots": [str(Path(p).resolve()) for p in extra_doc_roots],
        "scan_scope": scope.relative_to(out_root).as_posix(),
    }
    meta = new_meta(out_root, dummyindex_version=dummyindex_version).with_updates(
        languages=languages,
        file_count=len(files_map.files),
        symbol_count=len(symbols_map.symbols),
        config=meta_config,
        indexed_commit=head_commit(out_root),
        root=".",
    )

    # Build the source-docs catalog before _write_all so PROJECT.md and the
    # architecture overview can reference it. The catalog also gets written
    # to .context/source-docs/INDEX.{json,md} below.
    doc_paths = collect_doc_paths(detection, out_root, extra_doc_roots)
    newest_code_mtime = newest_mtime(code_files)
    symbol_names: frozenset[str] = frozenset(s.name for s in symbols_map.symbols)
    # The file-path match set covers every detected file, not just code: prose docs cite
    # docs, JSON, configs and generated artifacts, and a code-only set drives false
    # positives. Files outside out_root (external --docs) are left out.
    all_repo_file_paths = _all_repo_file_paths(detection, out_root)
    file_paths_set: frozenset[str] = (
        frozenset(f.path for f in files_map.files) | all_repo_file_paths
    )
    # JSON keys give us "schema fields" for free — see harvest_json_keys.
    json_repo_paths = [
        Path(raw)
        for raw in (detection.get("files", {}) or {}).get("code", [])
        if Path(raw).suffix.lower() == ".json"
    ] + [out_root / rel for rel in all_repo_file_paths if rel.endswith(".json")]
    extra_names = harvest_json_keys(json_repo_paths)
    doc_catalog = build_doc_catalog(
        doc_paths,
        repo_root=out_root,
        symbol_names=symbol_names,
        file_paths=file_paths_set,
        newest_code_mtime=newest_code_mtime,
        extra_doc_roots=tuple(extra_doc_roots),
        extra_names=extra_names,
    )

    written = _write_all(
        context_dir,
        meta,
        files_map,
        symbols_map,
        tree,
        rules,
        out_root,
        doc_catalog=doc_catalog,
    )

    # Symbol-level knowledge graph (deterministic) at features/symbol-graph.json.
    graph_result: GraphResult | None = None
    graph_data_for_features: dict | None = None
    features_dir = context_dir / "features"
    try:
        graph_result = build_graph(extraction, features_dir, root=out_root)
        written.append("features/symbol-graph.json")
        written.extend(graph_result.artifacts)
        # Re-read so feature scaffolding can use the same JSON the agent sees.
        from dummyindex.export.storage import read_graph_payload

        graph_data_for_features = read_graph_payload(graph_result.json_path)
    except Exception as exc:
        # A graph failure must not block the rest of the build: tree.json, maps,
        # conventions and playbooks are the primary product.
        import warnings

        warnings.warn(
            f"graph generation failed: {exc!r}; continuing without it", stacklevel=2
        )

    # Feature scaffolding (deterministic). Needs the graph because features
    # are derived from communities + entry-point traces on the call subgraph.
    if graph_data_for_features is not None:
        try:
            feature_result = scaffold_features(
                context_dir,
                graph_data_for_features,
                root=out_root,
                doc_catalog=doc_catalog,
            )
            written.extend(feature_result.written)
        except Exception as exc:
            import warnings

            warnings.warn(
                f"feature scaffolding failed: {exc!r}; continuing without features/",
                stacklevel=2,
            )

    # Source-doc catalog (advisory; verifiable; references AST). Written
    # last so the agent sees a coherent set: maps + features first, then
    # the prose layer.
    try:
        json_path, md_path = write_catalog(context_dir, doc_catalog)
        written.append("source-docs/INDEX.json")
        written.append("source-docs/INDEX.md")
    except Exception as exc:
        import warnings

        warnings.warn(f"source-docs catalog write failed: {exc!r}", stacklevel=2)

    # Session-memory store: agent-maintained, never regenerated. Seeding the empty tier
    # stubs is idempotent and non-destructive, so memory survives every rebuild. detect()
    # skips .context/session-memory/, so it stays out of the drift manifest.
    try:
        from dummyindex.context.domains.memory import ensure_memory_store

        for tier_name in ensure_memory_store(context_dir):
            written.append(f"session-memory/{tier_name}")
    except Exception as exc:
        import warnings

        warnings.warn(f"memory store seed failed: {exc!r}; continuing", stacklevel=2)

    from dummyindex.context.build.coverage import write_coverage

    write_coverage(
        context_dir, files_map, symbols_map, detection=detection, extraction=extraction
    )
    written.append("coverage.json")

    # INDEX.md is always written last so it reflects what actually landed.
    write_index_md(context_dir / "INDEX.md", generate_index_md(sorted(written)))
    written.append("INDEX.md")

    # Byte-level hygiene pass over everything this build wrote: committed
    # artifacts must be pre-commit-clean (exactly one EOF newline), no
    # matter which domain writer produced them.
    normalize_written_eof_newlines(context_dir, written)

    # Drift manifest — every rebuild stamps current source-file hashes so
    # `dummyindex context check` can detect drift between sessions. Docs
    # are included so edits to README.md / docs/ also trigger a rebuild.
    manifest_files: list[Path] = list(code_files) + [
        Path(d.abs_path)
        for d in doc_catalog.docs
        if not d.is_external  # external docs aren't repo-relative; skip in manifest
    ]
    try:
        write_manifest(context_dir, root=out_root, files=manifest_files)
    except Exception as exc:
        import warnings

        warnings.warn(
            f"manifest write failed: {exc!r}; drift detection disabled", stacklevel=2
        )

    guidance_ready = False
    if bootstrap:
        claude_result = reconcile_claude_md(out_root)
        guidance_ready = not claude_result.warnings
        if claude_result.warnings:
            import warnings

            for warning in claude_result.warnings:
                warnings.warn(f"CLAUDE.md reconcile: {warning}", stacklevel=2)

    return BuildResult(
        root=out_root,
        context_dir=context_dir,
        file_count=meta.file_count,
        symbol_count=meta.symbol_count,
        languages=languages,
        written=tuple(written),
        bootstrapped=guidance_ready,
        graph=graph_result,
        doc_catalog=doc_catalog,
        migration=migration,
    )


def _all_repo_file_paths(detection: dict, repo_root: Path) -> frozenset[str]:
    """Return repo-relative POSIX paths for every file the detector saw,
    across every category. Used to widen the broken-refs matcher.

    Excludes files that resolve outside ``repo_root`` (i.e. anything
    walked via ``--docs PATH`` to an external location).
    """
    out: set[str] = set()
    files = detection.get("files", {}) if isinstance(detection, dict) else {}
    for _ftype, paths in files.items():
        for raw in paths or []:
            try:
                p = Path(raw).resolve()
                rel = p.relative_to(repo_root).as_posix()
            except (OSError, ValueError):
                continue
            out.add(rel)
    return frozenset(out)


def _derive_languages(files_map: FilesMap) -> tuple[str, ...]:
    return tuple(sorted({f.language for f in files_map.files if f.language}))


def _write_all(
    context_dir: Path,
    meta: Meta,
    files_map: FilesMap,
    symbols_map: SymbolsMap,
    tree: Tree,
    rules,
    root: Path,
    *,
    doc_catalog: DocCatalog | None = None,
) -> list[str]:
    # The managed .gitignore/.gitattributes and the legacy-plan cleanup ran
    # in `build_all`'s `migrate_context_layout` call, before extraction.
    written: list[str] = []
    write_meta(context_dir / "meta.json", meta)
    written.append("meta.json")

    write_files_map(context_dir / "map" / "files.json", files_map)
    written.append("map/files.json")
    write_symbols_map(context_dir / "map" / "symbols.json", symbols_map)
    written.append("map/symbols.json")

    write_tree(context_dir / "tree.json", tree)
    written.append("tree.json")

    write_naming_json(context_dir / "conventions" / "naming.json", rules)
    written.append("conventions/naming.json")
    write_naming_md(
        context_dir / "conventions" / "naming.md",
        rules,
        generated_at=meta.updated_at,
    )
    written.append("conventions/naming.md")

    write_project_md(
        context_dir / "PROJECT.md",
        generate_project_md(root, meta, doc_catalog=doc_catalog),
    )
    written.append("PROJECT.md")

    write_how_to_use_md(context_dir / "HOW_TO_USE.md")
    written.append("HOW_TO_USE.md")

    write_architecture_overview_md(
        context_dir / "architecture" / "overview.md",
        root,
        files_map,
        symbols_map,
        meta,
        doc_catalog=doc_catalog,
    )
    written.append("architecture/overview.md")

    for playbook_id in PLAYBOOK_IDS:
        rel = f"playbooks/{playbook_id}.md"
        write_playbook_md(context_dir / rel, playbook_id)
        written.append(rel)

    # INDEX.md is written by the caller after all artifacts (incl. graph) are
    # in, so it lists everything that actually landed.
    return written
