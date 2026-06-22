"""End-to-end .context/ build pipeline.

Single detect → extract → build_structure pass feeds every downstream writer,
so `dummyindex context init` doesn't re-walk the repo for each artifact.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from dummyindex.context.build.common import (
    cache_dir_override,
    collect_doc_paths,
    newest_mtime,
    normalize_written_eof_newlines,
)
from dummyindex.context.output.claude_md import reconcile_claude_md
from dummyindex.context.build.conventions import (
    analyze_naming,
    write_naming_json,
    write_naming_md,
)
from dummyindex.context.output.docs import (
    generate_index_md,
    generate_project_md,
    write_index_md,
    write_project_md,
)
from dummyindex.context.domains.features import scaffold_features
from dummyindex.context.build.git_delta import head_commit
from dummyindex.context.build.graph import GraphResult, build_graph
from dummyindex.context.build.manifest import write_manifest
from dummyindex.context.output.instructions import (
    PLAYBOOK_IDS,
    write_architecture_overview_md,
    write_how_to_use_md,
    write_playbook_md,
)
from dummyindex.context.build.maps import (
    FilesMap,
    SymbolsMap,
    files_map_from_paths,
    symbols_map_from_structure,
    write_files_map,
    write_symbols_map,
)
from dummyindex.context.build.meta import Meta, new_meta, write_meta
from dummyindex.context.domains.source_docs import (
    DocCatalog,
    build_doc_catalog,
    harvest_json_keys,
    write_catalog,
)
from dummyindex.context.build.tree import Tree, tree_from_structure, write_tree
from dummyindex.pipeline.io.detect import detect
from dummyindex.pipeline.extract import extract
from dummyindex.pipeline.build import build_structure


@dataclass(frozen=True)
class BuildResult:
    root: Path
    context_dir: Path
    file_count: int
    symbol_count: int
    languages: tuple[str, ...]
    written: tuple[str, ...]
    bootstrapped: bool
    graph: Optional[GraphResult] = None
    doc_catalog: Optional[DocCatalog] = None


def build_all(
    scope: Path,
    *,
    out_root: Optional[Path] = None,
    cache_root: Optional[Path] = None,
    bootstrap: bool = False,
    dummyindex_version: str = "0.0.0",
    extra_doc_roots: Sequence[Path] = (),
) -> BuildResult:
    """Run the full .context/ build and write every artifact atomically.

    Args:
        scope: directory to scan for code. The contents below this path
            are what get extracted and indexed.
        out_root: where `.context/` and `.claude/CLAUDE.md` are written.
            Defaults to ``scope``. Pass a parent of ``scope`` to ingest a
            subdirectory of a larger repo while keeping the index at the
            repo root.

            All file paths inside the generated artifacts (`tree.json`,
            `map/files.json`, `map/symbols.json`) are relative to ``out_root``,
            so a sub-scan of `/repo/app` from out_root `/repo` produces paths
            like `app/utils.py` — sensible from `/repo/.context/`.

    Returns a BuildResult listing what was written and the high-level counts.
    """
    scope = scope.resolve()
    out_root = (out_root or scope).resolve()
    context_dir = out_root / ".context"
    cache = (cache_root or out_root).resolve()

    # Pin the per-file extraction cache to .context/cache/ so the env var
    # picked up by pipeline.cache.cache_dir() points at the same location
    # regardless of caller-provided cache roots.
    cache_target = context_dir / "cache"

    with cache_dir_override(cache_target):
        detection = detect(scope, extra_doc_roots=tuple(extra_doc_roots))
        code_files = [Path(p) for p in detection.get("files", {}).get("code", [])]
        extraction = extract(code_files, cache_root=cache)
        # Use out_root as the base for relative paths so the structure tree
        # (and everything derived from it) reads correctly from the .context/
        # location.
        structure = build_structure(extraction, code_files, out_root, include_extras=False)

    files_map = files_map_from_paths(code_files, out_root)
    symbols_map = symbols_map_from_structure(structure, out_root)
    tree = tree_from_structure(structure, out_root)
    rules = analyze_naming(files_map, symbols_map)

    languages = _derive_languages(files_map)
    meta_config = {
        "extra_doc_roots": [str(Path(p).resolve()) for p in extra_doc_roots],
    }
    meta = new_meta(out_root, dummyindex_version=dummyindex_version).with_updates(
        languages=languages,
        file_count=len(files_map.files),
        symbol_count=len(symbols_map.symbols),
        config=meta_config,
        indexed_commit=head_commit(out_root),
    )

    # Build the source-docs catalog before _write_all so PROJECT.md and the
    # architecture overview can reference it. The catalog also gets written
    # to .context/source-docs/INDEX.{json,md} below.
    doc_paths = collect_doc_paths(detection, out_root, extra_doc_roots)
    newest_code_mtime = newest_mtime(code_files)
    symbol_names: frozenset[str] = frozenset(s.name for s in symbols_map.symbols)
    # File-path match set covers *every* tracked file, not just code.
    # Prose docs reference docs, JSON, configs, generated artifacts —
    # restricting to code drives false positives. We compose:
    #   - paths in `files_map` (code files, repo-relative)
    #   - the doc paths themselves (mostly repo-relative; external ones
    #     get filtered when they can't be made relative to out_root)
    #   - every other tracked file from detection (papers, images, etc.)
    all_repo_file_paths = _all_repo_file_paths(detection, out_root)
    file_paths_set: frozenset[str] = frozenset(
        f.path for f in files_map.files
    ) | all_repo_file_paths
    # JSON keys give us "schema fields" for free — see harvest_json_keys.
    json_repo_paths = [
        Path(raw) for raw in (detection.get("files", {}) or {}).get("code", [])
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
        context_dir, meta, files_map, symbols_map, tree, rules, out_root,
        doc_catalog=doc_catalog,
    )

    # Symbol-level knowledge graph (deterministic). v0.6+ writes under
    # .context/features/symbol-graph.json — the legacy .context/graph/ folder
    # is gone (pyvis HTML hairball dropped).
    graph_result: Optional[GraphResult] = None
    graph_data_for_features: Optional[dict] = None
    features_dir = context_dir / "features"
    try:
        graph_result = build_graph(extraction, features_dir)
        written.append("features/symbol-graph.json")
        # Re-read so feature scaffolding can use the same JSON the agent sees.
        graph_data_for_features = json.loads(
            graph_result.json_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        # Don't let graph generation failures block the rest of the .context/ build.
        # The agent-shaped files (tree.json, maps, conventions, playbooks) are the
        # primary product; the graph is a useful-but-secondary visualization.
        import warnings
        warnings.warn(f"graph generation failed: {exc!r}; continuing without it")

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
                f"feature scaffolding failed: {exc!r}; continuing without features/"
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
        warnings.warn(f"source-docs catalog write failed: {exc!r}")

    # Session-memory store (agent-maintained; never regenerated). Seed empty
    # tier stubs so the SessionStart hook + /dummyindex-remember have a home.
    # Idempotent and non-destructive — existing memory survives every rebuild.
    # The store lives at .context/session-memory/ which detect() does NOT scan,
    # so its files are intentionally NOT tracked in the drift manifest.
    try:
        from dummyindex.context.domains.memory import ensure_memory_store

        for tier_name in ensure_memory_store(context_dir):
            written.append(f"session-memory/{tier_name}")
    except Exception as exc:
        import warnings

        warnings.warn(f"memory store seed failed: {exc!r}; continuing")

    # INDEX.md is always written last so it reflects what actually landed.
    write_index_md(
        context_dir / "INDEX.md", generate_index_md(sorted(written))
    )
    written.append("INDEX.md")

    # Byte-level hygiene pass over everything this build wrote: committed
    # artifacts must be pre-commit-clean (exactly one EOF newline), no
    # matter which domain writer produced them.
    normalize_written_eof_newlines(context_dir, written)

    # Drift manifest — every rebuild stamps current source-file hashes so
    # `dummyindex context check` can detect drift between sessions. Docs
    # are included so edits to README.md / docs/ also trigger a rebuild.
    manifest_files: list[Path] = list(code_files) + [
        Path(d.abs_path) for d in doc_catalog.docs
        if not d.is_external  # external docs aren't repo-relative; skip in manifest
    ]
    try:
        write_manifest(context_dir, root=out_root, files=manifest_files)
    except Exception as exc:
        import warnings
        warnings.warn(f"manifest write failed: {exc!r}; drift detection disabled")

    if bootstrap:
        claude_result = reconcile_claude_md(out_root)
        if claude_result.warnings:
            import warnings
            for warning in claude_result.warnings:
                warnings.warn(f"CLAUDE.md reconcile: {warning}")

    return BuildResult(
        root=out_root,
        context_dir=context_dir,
        file_count=meta.file_count,
        symbol_count=meta.symbol_count,
        languages=languages,
        written=tuple(written),
        bootstrapped=bootstrap,
        graph=graph_result,
        doc_catalog=doc_catalog,
    )


def _all_repo_file_paths(detection: dict, repo_root: Path) -> frozenset[str]:
    """Return repo-relative POSIX paths for every file the detector saw,
    across every category. Used to widen the broken-refs matcher.

    Excludes files that resolve outside ``repo_root`` (i.e. anything
    walked via ``--docs PATH`` to an external location).
    """
    out: set[str] = set()
    files = detection.get("files", {}) if isinstance(detection, dict) else {}
    for ftype, paths in files.items():
        for raw in paths or []:
            try:
                p = Path(raw).resolve()
                rel = p.relative_to(repo_root).as_posix()
            except (OSError, ValueError):
                continue
            out.add(rel)
    return frozenset(out)


# Single source of truth for the patterns dummyindex manages inside
# .context/.gitignore. Both the fresh-file body and the upgrade-merge below
# derive from this tuple so they can never drift. Bare filenames (no slash)
# match at any depth, which is how the per-feature scratch/log artefacts
# (e.g. features/<id>/council/_council-log.json) get ignored.
_MANAGED_GITIGNORE_PATTERNS: tuple[str, ...] = (
    "cache/",
    "_doc_backups/",
    # Internal scratch/log artefacts — local work-lists and audit trails the
    # session writes, never committed docs. `_enrich_plan.json` is belt-and-
    # suspenders: new runs write it under cache/, but repos indexed by 0.15.0
    # may still have a transitional copy at the .context/ root.
    "_enrich_plan.json",
    "_structural-plan.json",
    "_council-log.json",
    "_reality-check.json",
    "_reality-check.md",
)

_CONTEXT_GITIGNORE_HEADER = (
    "# Generated by dummyindex. These are local scratch/cache artefacts that\n"
    "# regenerate automatically — don't commit them.\n"
)

# Machine-layer artefacts marked `linguist-generated` in the managed
# .context/.gitattributes. DESIGN DECISION: these stay *committed* — a fresh
# clone must navigate .context/ without running the CLI, and the
# commit-anchored reconcile model diffs against the committed index — but
# their rebuild churn is generated noise, so GitHub folds them out of PR
# review. Deliberately no `-diff` attribute: it would also suppress local
# `git diff` and hide merge conflicts.
_MANAGED_GITATTRIBUTES_RULES: tuple[str, ...] = (
    "tree.json linguist-generated",
    "map/files.json linguist-generated",
    "map/symbols.json linguist-generated",
    "features/symbol-graph.json linguist-generated",
    "features/graph.json linguist-generated",
    "features/graph.html linguist-generated",
)

_CONTEXT_GITATTRIBUTES_HEADER = (
    "# Generated by dummyindex. The machine-layer artefacts below are\n"
    "# committed by design but their diffs are rebuild noise —\n"
    "# `linguist-generated` collapses them in GitHub PR review.\n"
)


def _context_gitignore_body() -> str:
    """Render the full managed body: header comment + one pattern per line."""
    return _CONTEXT_GITIGNORE_HEADER + "".join(
        f"{pattern}\n" for pattern in _MANAGED_GITIGNORE_PATTERNS
    )


def _ensure_managed_lines(
    path: Path, header: str, managed_lines: tuple[str, ...]
) -> None:
    """Write/upgrade a managed line-oriented file (gitignore/gitattributes).

    Fresh file: write header + every managed line. Existing file: append only
    the managed lines that are missing (stripped line comparison), preserving
    user-added lines and any header — pure-merge, never drops a user line.
    Idempotent: a second call with nothing missing rewrites nothing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            header + "".join(f"{line}\n" for line in managed_lines),
            encoding="utf-8",
        )
        return

    current = path.read_text(encoding="utf-8")
    present = {line.strip() for line in current.splitlines() if line.strip()}
    missing = [line for line in managed_lines if line not in present]
    if not missing:
        return
    addition = "".join(f"{line}\n" for line in missing)
    path.write_text(current.rstrip() + "\n" + addition, encoding="utf-8")


def ensure_context_gitignore(context_dir: Path) -> None:
    """Write/upgrade the managed .gitignore inside .context/.

    Public on purpose: the non-build verbs that create scratch artefacts
    (e.g. ``enrich-plan``) call this too, so a repo maintained purely via
    the reconcile path still receives new managed patterns. Merge semantics
    are documented on :func:`_ensure_managed_lines`.
    """
    _ensure_managed_lines(
        context_dir / ".gitignore",
        _CONTEXT_GITIGNORE_HEADER,
        _MANAGED_GITIGNORE_PATTERNS,
    )


def ensure_context_gitattributes(context_dir: Path) -> None:
    """Write/upgrade the managed .gitattributes inside .context/.

    Marks the heavy machine-layer artefacts ``linguist-generated`` (see
    ``_MANAGED_GITATTRIBUTES_RULES`` for the commit-policy rationale) while
    the curated taxonomy stays reviewable. Same pure-merge semantics as the
    managed .gitignore.
    """
    _ensure_managed_lines(
        context_dir / ".gitattributes",
        _CONTEXT_GITATTRIBUTES_HEADER,
        _MANAGED_GITATTRIBUTES_RULES,
    )


def remove_legacy_enrich_plan(context_dir: Path) -> bool:
    """Unlink the pre-0.21 root-level ``.context/_enrich_plan.json``.

    Versions <= 0.20 wrote the transient enrichment work-list at the
    .context/ root; current code writes it under ``cache/`` (gitignored).
    The bare-name gitignore pattern only hides the stale copy from git —
    this removes the file itself on the next build / enrich-plan run.
    The current ``cache/_enrich_plan.json`` is never touched. Returns
    ``True`` when a stale copy was removed.
    """
    legacy = context_dir / "_enrich_plan.json"
    if not legacy.is_file():
        return False
    legacy.unlink()
    return True


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
    doc_catalog: Optional[DocCatalog] = None,
) -> list[str]:
    ensure_context_gitignore(context_dir)
    ensure_context_gitattributes(context_dir)
    remove_legacy_enrich_plan(context_dir)

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
