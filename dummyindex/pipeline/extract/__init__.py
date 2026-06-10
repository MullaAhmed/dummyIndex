"""Deterministic structural extraction from source code using tree-sitter.

Public surface (kept stable for `dummyindex.__init__`'s lazy `__getattr__`
map and for tests):

- `extract(paths, cache_root=None)` → `{"nodes": [...], "edges": [...]}`
- `collect_files(target, *, follow_symlinks=False, root=None)` → `list[Path]`

The implementation is split across siblings:

- `config.py` — `LanguageConfig` dataclass
- `_common.py` — id / name / body / read helpers
- `_imports.py` — per-language `_import_<lang>` handlers
- `_helpers.py` — extra-walk helpers and C/C++ name resolvers
- `language_configs.py` — `LanguageConfig` instances per language
- `_generic.py` — `_extract_generic` (the parametric driver)
- `_python_rationale.py` — Python docstring + rationale post-pass
- `_resolve.py` — cross-file import resolvers (Python, Java)
- `languages/` — per-language `extract_<lang>` functions
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from ..io.cache import load_cached, save_cached
from .common import _make_id
from .resolve import _resolve_cross_file_imports, _resolve_cross_file_java_imports
from .languages import (
    extract_blade,
    extract_c,
    extract_cpp,
    extract_csharp,
    extract_dart,
    extract_elixir,
    extract_go,
    extract_java,
    extract_js,
    extract_julia,
    extract_kotlin,
    extract_lua,
    extract_php,
    extract_powershell,
    extract_python,
    extract_ruby,
    extract_rust,
    extract_scala,
    extract_swift,
    extract_verilog,
    extract_zig,
)

__all__ = ["extract", "collect_files"]


def _check_tree_sitter_version() -> None:
    """Raise a clear error if tree-sitter is too old for the new Language API."""
    try:
        from tree_sitter import LANGUAGE_VERSION
    except ImportError:
        raise ImportError(
            "tree-sitter is not installed. Run: pip install 'tree-sitter>=0.23.0'"
        )
    if LANGUAGE_VERSION < 14:
        import tree_sitter as _ts
        raise RuntimeError(
            f"tree-sitter {getattr(_ts, '__version__', 'unknown')} is too old. "
            f"dummyindex requires tree-sitter >= 0.23.0 (Language API v2). "
            f"Run: pip install --upgrade tree-sitter"
        )


_DISPATCH: dict[str, Any] = {
    ".py": extract_python,
    ".js": extract_js,
    ".jsx": extract_js,
    ".mjs": extract_js,
    ".ts": extract_js,
    ".tsx": extract_js,
    ".go": extract_go,
    ".rs": extract_rust,
    ".java": extract_java,
    ".c": extract_c,
    ".h": extract_c,
    ".cpp": extract_cpp,
    ".cc": extract_cpp,
    ".cxx": extract_cpp,
    ".hpp": extract_cpp,
    ".rb": extract_ruby,
    ".cs": extract_csharp,
    ".kt": extract_kotlin,
    ".kts": extract_kotlin,
    ".scala": extract_scala,
    ".php": extract_php,
    ".swift": extract_swift,
    ".lua": extract_lua,
    ".toc": extract_lua,
    ".zig": extract_zig,
    ".ps1": extract_powershell,
    ".ex": extract_elixir,
    ".exs": extract_elixir,
    ".jl": extract_julia,
    ".vue": extract_js,
    ".svelte": extract_js,
    ".dart": extract_dart,
    ".v": extract_verilog,
    ".sv": extract_verilog,
}

_PROGRESS_INTERVAL = 100


def extract(paths: list[Path], cache_root: Path | None = None) -> dict:
    """Extract AST nodes and edges from a list of code files.

    Two-pass process:
    1. Per-file structural extraction (classes, functions, imports)
    2. Cross-file import resolution: turns file-level imports into
       class-level INFERRED edges (DigestAuth --uses--> Response)

    Args:
        paths: files to extract from
        cache_root: explicit root for .context/cache/ (overrides the
            inferred common path prefix). Pass Path('.') when running on a
            subdirectory so the cache stays at ./.context/cache/.
    """
    _check_tree_sitter_version()
    per_file: list[dict] = []

    try:
        if not paths:
            root = Path(".")
        elif len(paths) == 1:
            root = paths[0].parent
        else:
            min_parts = min(len(p.parts) for p in paths)
            common_len = 0
            for i in range(min_parts):
                if len({p.parts[i] for p in paths}) == 1:
                    common_len += 1
                else:
                    break
            root = Path(*paths[0].parts[:common_len]) if common_len else Path(".")
    except Exception:
        root = Path(".")
    root = root.resolve()

    total = len(paths)
    for i, path in enumerate(paths):
        if total >= _PROGRESS_INTERVAL and i % _PROGRESS_INTERVAL == 0 and i > 0:
            print(f"  AST extraction: {i}/{total} files ({i * 100 // total}%)", flush=True)
        if path.name.endswith(".blade.php"):
            extractor = extract_blade
        else:
            extractor = _DISPATCH.get(path.suffix)
        if extractor is None:
            continue
        cached = load_cached(path, cache_root or root)
        if cached is not None:
            per_file.append(cached)
            continue
        result = extractor(path)
        if "error" not in result:
            save_cached(path, result, cache_root or root)
        per_file.append(result)
    if total >= _PROGRESS_INTERVAL:
        print(f"  AST extraction: {total}/{total} files (100%)", flush=True)

    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    for result in per_file:
        all_nodes.extend(result.get("nodes", []))
        all_edges.extend(result.get("edges", []))

    id_remap: dict[str, str] = {}
    for path in paths:
        old_id = _make_id(str(path))
        try:
            new_id = _make_id(str(path.relative_to(root)))
        except ValueError:
            continue
        if old_id != new_id:
            id_remap[old_id] = new_id
    if id_remap:
        for n in all_nodes:
            if n.get("id") in id_remap:
                n["id"] = id_remap[n["id"]]
        for e in all_edges:
            if e.get("source") in id_remap:
                e["source"] = id_remap[e["source"]]
            if e.get("target") in id_remap:
                e["target"] = id_remap[e["target"]]

    py_paths = [p for p in paths if p.suffix == ".py"]
    if py_paths:
        py_results = [r for r, p in zip(per_file, paths) if p.suffix == ".py"]
        try:
            cross_file_edges = _resolve_cross_file_imports(py_results, py_paths)
            all_edges.extend(cross_file_edges)
        except Exception as exc:
            logging.getLogger(__name__).warning("Cross-file import resolution failed, skipping: %s", exc)

    java_paths = [p for p in paths if p.suffix == ".java"]
    if java_paths:
        java_results = [r for r, p in zip(per_file, paths) if p.suffix == ".java"]
        try:
            all_edges.extend(_resolve_cross_file_java_imports(java_results, java_paths))
        except Exception as exc:
            logging.getLogger(__name__).warning("Java cross-file import resolution failed, skipping: %s", exc)

    global_label_to_nid: dict[str, str] = {}
    for n in all_nodes:
        raw = n.get("label", "")
        normalised = raw.strip("()").lstrip(".")
        if normalised:
            global_label_to_nid[normalised.lower()] = n["id"]

    existing_pairs = {(e["source"], e["target"]) for e in all_edges}
    for result in per_file:
        for rc in result.get("raw_calls", []):
            callee = rc.get("callee", "")
            if not callee:
                continue
            tgt = global_label_to_nid.get(callee.lower())
            caller = rc["caller_nid"]
            if tgt and tgt != caller and (caller, tgt) not in existing_pairs:
                existing_pairs.add((caller, tgt))
                all_edges.append({
                    "source": caller,
                    "target": tgt,
                    "relation": "calls",
                    "confidence": ConfidenceLevel.INFERRED,
                    "confidence_score": 0.8,
                    "source_file": rc.get("source_file", ""),
                    "source_location": rc.get("source_location"),
                    "weight": 1.0,
                })

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def collect_files(target: Path, *, follow_symlinks: bool = False, root: Path | None = None) -> list[Path]:
    if target.is_file():
        return [target]
    _EXTENSIONS = {
        ".py", ".js", ".ts", ".tsx", ".go", ".rs",
        ".java", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
        ".rb", ".cs", ".kt", ".kts", ".scala", ".php", ".swift",
        ".lua", ".toc", ".zig", ".ps1",
    }
    from dummyindex.pipeline.io.detect import _load_dummyindexignore, _is_ignored
    ignore_root = root if root is not None else target
    patterns = _load_dummyindexignore(ignore_root)

    def _ignored(p: Path) -> bool:
        return bool(patterns and _is_ignored(p, ignore_root, patterns))

    if not follow_symlinks:
        results: list[Path] = []
        for ext in sorted(_EXTENSIONS):
            results.extend(
                p for p in target.rglob(f"*{ext}")
                if not any(part.startswith(".") for part in p.parts)
                and not _ignored(p)
            )
        return sorted(results)
    results = []
    for dirpath, dirnames, filenames in os.walk(target, followlinks=True):
        if os.path.islink(dirpath):
            real = os.path.realpath(dirpath)
            parent_real = os.path.realpath(os.path.dirname(dirpath))
            if parent_real == real or parent_real.startswith(real + os.sep):
                dirnames.clear()
                continue
        dp = Path(dirpath)
        if any(part.startswith(".") for part in dp.parts):
            dirnames.clear()
            continue
        for fname in filenames:
            p = dp / fname
            if p.suffix in _EXTENSIONS and not fname.startswith(".") and not _ignored(p):
                results.append(p)
    return sorted(results)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m dummyindex.pipeline.extract <file_or_dir> ...", file=sys.stderr)
        sys.exit(1)

    paths: list[Path] = []
    for arg in sys.argv[1:]:
        paths.extend(collect_files(Path(arg)))

    result = extract(paths)
    print(json.dumps(result, indent=2))
