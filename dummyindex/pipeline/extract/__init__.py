"""Deterministic structural extraction from source code using tree-sitter.

Public surface (kept stable for `dummyindex.__init__`'s lazy `__getattr__`
map and for tests):

- `extract(paths, cache_root=None)` → `{"nodes": [...], "edges": [...],
  "file_bytes": {str(path): bytes}}` — `file_bytes` carries the source bytes the
  extraction already read so the downstream textual-reference pass
  (`build/references.py`, via `build/structure.py`) consumes the cached bytes
  instead of re-reading disk (P2: each file read ≤2× per build, all passes the
  same bytes).
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

from ..io.cache import build_read_cache, load_cached, read_source_bytes, save_cached
from ..io.paths import resolve_under_root
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
    # P2: bytes read for each path during this extraction, keyed by str(path).
    # Threaded out through the return so the textual-reference pass reuses them
    # instead of re-reading disk. Populated from the same build-scoped read cache
    # that collapses the hash / extractor / rationale / cross-file reads into a
    # single Path.read_bytes per file.
    file_bytes: dict[str, bytes] = {}

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
    # One build-scoped read cache spans the per-file pass AND the cross-file
    # resolve passes, so the hash read, the extractor read, the Python rationale
    # post-pass, and the cross-file import re-parse all share a single
    # Path.read_bytes per path (P2). The bytes are captured into file_bytes so
    # the textual-reference pass (run later in build_structure) reuses them.
    with build_read_cache():
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
                # load_cached read the bytes through the shared cache to hash
                # them; capture that same byte-state for the reference pass.
                file_bytes[str(path)] = read_source_bytes(path)
                continue
            result = extractor(path)
            if "error" not in result:
                save_cached(path, result, cache_root or root)
            per_file.append(result)
            file_bytes[str(path)] = read_source_bytes(path)
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
            # Immutability: the dicts in all_nodes/all_edges are aliased from the
            # load_cached-returned payloads (and re-consumed by later passes), so
            # build NEW dicts ({**n, "id": ...}) rather than mutate in place.
            all_nodes = [
                {**n, "id": id_remap[n["id"]]} if n.get("id") in id_remap else n
                for n in all_nodes
            ]
            all_edges = [
                {
                    **e,
                    **({"source": id_remap[e["source"]]} if e.get("source") in id_remap else {}),
                    **({"target": id_remap[e["target"]]} if e.get("target") in id_remap else {}),
                }
                for e in all_edges
            ]

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

    # Map normalized label -> nid, but track when >1 *distinct* node claims the
    # same key. A colliding key is ambiguous: the call-resolution loop below
    # SKIPS it rather than silently binding to whichever node was iterated last.
    global_label_to_nid: dict[str, str] = {}
    ambiguous_labels: set[str] = set()
    for n in all_nodes:
        raw = n.get("label", "")
        normalised = raw.strip("()").lstrip(".")
        if not normalised:
            continue
        key = normalised.lower()
        existing = global_label_to_nid.get(key)
        if existing is None:
            global_label_to_nid[key] = n["id"]
        elif existing != n["id"]:
            ambiguous_labels.add(key)

    existing_pairs = {(e["source"], e["target"]) for e in all_edges}
    for result in per_file:
        for rc in result.get("raw_calls", []):
            callee = rc.get("callee", "")
            if not callee:
                continue
            callee_key = callee.lower()
            if callee_key in ambiguous_labels:
                # Two distinct symbols normalize to this label — skip rather
                # than bind to an arbitrary (last-iterated) node.
                continue
            tgt = global_label_to_nid.get(callee_key)
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
        "file_bytes": file_bytes,
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
    # Containment root for the follow_symlinks walk: the explicit `root` if
    # given, else `target`. A leaf whose realpath escapes this root is rejected
    # BEFORE emission so neither downstream read sink (the cache-hash read at
    # cache.py:38 nor the extractor read at generic.py:42) ever touches an
    # out-of-tree target.
    containment_root = (root if root is not None else target).resolve()
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
                # WALK-TIME containment: reject leaves whose realpath escapes
                # the containment root (e.g. a symlink pointing outside it).
                # This is walk-time, not read-time — a post-enumeration symlink
                # swap (TOCTOU) is a documented residual; a true read-time
                # guard would live in generic.py (deferred to a later task).
                if resolve_under_root(Path(os.path.realpath(p)), containment_root) is None:
                    continue
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
