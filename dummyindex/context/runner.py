"""End-to-end .context/ build pipeline.

Single detect → extract → build_structure pass feeds every downstream writer,
so `dummyindex context init` doesn't re-walk the repo for each artifact.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dummyindex.context.bootstrap import bootstrap_claude_md
from dummyindex.context.conventions import (
    analyze_naming,
    write_naming_json,
    write_naming_md,
)
from dummyindex.context.docs import (
    generate_index_md,
    generate_project_md,
    write_index_md,
    write_project_md,
)
from dummyindex.context.maps import (
    FilesMap,
    SymbolsMap,
    files_map_from_paths,
    symbols_map_from_structure,
    write_files_map,
    write_symbols_map,
)
from dummyindex.context.meta import Meta, new_meta, write_meta
from dummyindex.context.tree import Tree, tree_from_structure, write_tree
from dummyindex.pipeline.detect import detect
from dummyindex.pipeline.extract import extract
from dummyindex.pipeline.structure import build_structure


@dataclass(frozen=True)
class BuildResult:
    root: Path
    context_dir: Path
    file_count: int
    symbol_count: int
    languages: tuple[str, ...]
    written: tuple[str, ...]
    bootstrapped: bool


def build_all(
    root: Path,
    *,
    cache_root: Optional[Path] = None,
    bootstrap: bool = False,
    dummyindex_version: str = "0.0.0",
) -> BuildResult:
    """Run the full .context/ build and write every artifact atomically.

    Returns a BuildResult listing what was written and the high-level counts.
    """
    root = root.resolve()
    context_dir = root / ".context"
    cache = (cache_root or root).resolve()

    detection = detect(root)
    code_files = [Path(p) for p in detection.get("files", {}).get("code", [])]
    extraction = extract(code_files, cache_root=cache)
    structure = build_structure(extraction, code_files, root)

    files_map = files_map_from_paths(code_files, root)
    symbols_map = symbols_map_from_structure(structure, root)
    tree = tree_from_structure(structure, root)
    rules = analyze_naming(files_map, symbols_map)

    languages = _derive_languages(files_map)
    meta = new_meta(root, dummyindex_version=dummyindex_version).with_updates(
        languages=languages,
        file_count=len(files_map.files),
        symbol_count=len(symbols_map.symbols),
    )

    written = _write_all(context_dir, meta, files_map, symbols_map, tree, rules, root)

    if bootstrap:
        bootstrap_claude_md(root / "CLAUDE.md")

    return BuildResult(
        root=root,
        context_dir=context_dir,
        file_count=meta.file_count,
        symbol_count=meta.symbol_count,
        languages=languages,
        written=tuple(written),
        bootstrapped=bootstrap,
    )


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
) -> list[str]:
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
        context_dir / "PROJECT.md", generate_project_md(root, meta)
    )
    written.append("PROJECT.md")

    write_index_md(
        context_dir / "INDEX.md", generate_index_md(sorted(written))
    )
    written.append("INDEX.md")
    return written
