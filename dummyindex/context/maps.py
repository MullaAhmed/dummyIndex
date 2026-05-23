"""Build .context/map/files.json and .context/map/symbols.json.

Wires the existing dummyindex pipeline (`detect` + `extract` + `build_structure`)
into the v0 context-folder JSON shapes. Pure transformation — no LLM calls.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dummyindex.pipeline.cache import file_hash
from dummyindex.pipeline.detect import detect
from dummyindex.pipeline.extract import extract
from dummyindex.pipeline.structure import build_structure

SCHEMA_VERSION = 1

_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".php": "php",
    ".swift": "swift",
    ".lua": "lua",
    ".zig": "zig",
    ".ps1": "powershell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".m": "objc",
    ".mm": "objc",
    ".jl": "julia",
    ".vue": "vue",
    ".svelte": "svelte",
    ".dart": "dart",
}

_SYMBOL_KINDS = frozenset({"class", "function", "method"})


@dataclass(frozen=True)
class FileEntry:
    path: str
    language: Optional[str]
    size_bytes: int
    loc: int = 0
    role: Optional[str] = None
    summary: Optional[str] = None
    sha256: str = ""


@dataclass(frozen=True)
class SymbolEntry:
    symbol_id: str
    kind: str
    name: str
    path: str
    range: Optional[tuple[int, int]] = None
    parent: Optional[str] = None
    docstring: Optional[str] = None
    exported: bool = True


@dataclass(frozen=True)
class FilesMap:
    schema_version: int
    files: tuple[FileEntry, ...]


@dataclass(frozen=True)
class SymbolsMap:
    schema_version: int
    symbols: tuple[SymbolEntry, ...]


def build_maps(
    root: Path,
    *,
    cache_root: Optional[Path] = None,
) -> tuple[FilesMap, SymbolsMap]:
    """Run detect → extract → build_structure on `root` and return both maps.

    `cache_root` controls where pipeline.extract writes its per-file cache
    (default: `root`). Tests pass a tmp dir to keep fixtures clean.
    """
    root = root.resolve()
    cache = (cache_root or root).resolve()

    detection = detect(root)
    code_files = [Path(p) for p in detection.get("files", {}).get("code", [])]

    extraction = extract(code_files, cache_root=cache)
    structure = build_structure(extraction, code_files, root)

    files_map = _build_files_map(code_files, root)
    symbols_map = _build_symbols_map(structure, root)
    return files_map, symbols_map


def _build_files_map(code_files: list[Path], root: Path) -> FilesMap:
    entries: list[FileEntry] = []
    seen: set[str] = set()
    for raw in sorted(code_files):
        rel = _rel_posix(raw, root)
        if rel is None or rel in seen:
            continue
        p = raw if raw.is_absolute() else (root / raw)
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        loc = _count_loc(p)
        entries.append(
            FileEntry(
                path=rel,
                language=_lang_for(p),
                size_bytes=size,
                loc=loc,
                sha256=file_hash(p, root),
            )
        )
        seen.add(rel)
    return FilesMap(schema_version=SCHEMA_VERSION, files=tuple(entries))


def _build_symbols_map(structure: dict, root: Path) -> SymbolsMap:
    parent_by_child: dict[str, str] = {}
    for edge in structure.get("hierarchy_edges", []):
        if edge.get("relation") in ("contains", "method"):
            src, tgt = edge.get("source"), edge.get("target")
            if src and tgt:
                parent_by_child[tgt] = src

    entries: list[SymbolEntry] = []
    for node in structure.get("nodes", []):
        kind = node.get("kind")
        if kind not in _SYMBOL_KINDS:
            continue
        raw_label = str(node.get("label") or "")
        # dummyindex labels methods as ".method_name()" (leading dot = "this is a
        # method") and top-level functions as "name()". Strip both markers for
        # a clean human-facing name.
        name = raw_label.rstrip("()").lstrip(".") or raw_label
        if not name:
            continue
        rel = _node_path(node, root)
        if rel is None:
            continue
        start = _parse_source_location(node.get("source_location"))
        rng = (start, start) if start is not None else None
        entries.append(
            SymbolEntry(
                symbol_id=node["id"],
                kind=kind,
                name=name,
                path=rel,
                range=rng,
                parent=parent_by_child.get(node["id"]),
                docstring=None,
                exported=not name.startswith("_"),
            )
        )
    entries.sort(key=lambda s: (s.path, (s.range or (0, 0))[0], s.name))
    return SymbolsMap(schema_version=SCHEMA_VERSION, symbols=tuple(entries))


def _node_path(node: dict, root: Path) -> Optional[str]:
    src = node.get("source_file") or ""
    if not src:
        return None
    p = Path(src)
    if p.is_absolute():
        return _rel_posix(p, root)
    # `build_structure` emits repo-relative POSIX paths in `source_file` for file/unit nodes
    return p.as_posix()


def _rel_posix(path: Path, root: Path) -> Optional[str]:
    try:
        p = path if path.is_absolute() else (root / path)
        return p.resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _lang_for(path: Path) -> Optional[str]:
    return _LANG_BY_EXT.get(path.suffix.lower())


def _count_loc(path: Path) -> int:
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _parse_source_location(loc: Any) -> Optional[int]:
    if not isinstance(loc, str):
        return None
    s = loc.strip().lstrip("L")
    if "-" in s:
        s = s.split("-", 1)[0].lstrip("L")
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


# --- Writers -----------------------------------------------------------------


def write_files_map(path: Path, m: FilesMap) -> None:
    _atomic_write_json(path, {
        "schema_version": m.schema_version,
        "files": [_file_to_json(e) for e in m.files],
    })


def write_symbols_map(path: Path, m: SymbolsMap) -> None:
    _atomic_write_json(path, {
        "schema_version": m.schema_version,
        "symbols": [_symbol_to_json(e) for e in m.symbols],
    })


def _file_to_json(e: FileEntry) -> dict[str, Any]:
    return {
        "path": e.path,
        "language": e.language,
        "size_bytes": e.size_bytes,
        "loc": e.loc,
        "role": e.role,
        "summary": e.summary,
        "sha256": e.sha256,
    }


def _symbol_to_json(e: SymbolEntry) -> dict[str, Any]:
    return {
        "symbol_id": e.symbol_id,
        "kind": e.kind,
        "name": e.name,
        "path": e.path,
        "range": list(e.range) if e.range else None,
        "parent": e.parent,
        "docstring": e.docstring,
        "exported": e.exported,
    }


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
