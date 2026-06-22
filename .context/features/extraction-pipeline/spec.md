# extraction-pipeline — spec

`confidence: INFERRED`

## Intent

This feature is the deterministic backbone of dummyindex: it turns a pile of source files into a structural symbol graph without ever calling an LLM. It parses each file with tree-sitter to find classes, functions, methods, imports and call sites; it resolves a subset of those references across files; it caches per-file results by content hash so re-runs only re-parse what changed; it groups the resulting graph into communities with a fixed-seed Leiden (falling back to Louvain); and it serialises the graph to a byte-stable JSON artifact. Determinism is a first-class requirement throughout — given the same inputs, every run produces the same node IDs, the same community IDs, and a byte-identical `symbol-graph.json`.

## User-visible behavior

- `extract(paths)` walks a list of files, dispatches each by extension to a language extractor, and returns `{"nodes": [...], "edges": [...], "input_tokens": 0, "output_tokens": 0}`. Unsupported extensions are silently skipped; per-file parse errors are isolated to that file (the file contributes an `error` result, no nodes/edges) and never abort the batch.
- Re-running `extract` on an unchanged tree is fast: each file's result is loaded from `.context/cache/<sha256>.json` instead of being re-parsed. The cache key is the file's content hash, so a `mv` or a different cwd still hits the cache; for `.md` files the YAML frontmatter is stripped before hashing so metadata edits don't invalidate.
- Node IDs are stable, lowercase, alphanumeric-with-underscores slugs derived from name parts (`_make_id`), so the same symbol gets the same ID run-to-run and machine-to-machine.
- Cross-file edges are added on top of the per-file pass: Python `from .x import Y` becomes class-level `uses` (INFERRED) edges, Java `import a.b.C;` becomes file-level `imports` (EXTRACTED) edges, and unresolved in-file calls are matched against a global label index to add `calls` (INFERRED) edges.
- `cluster(G)` returns `{community_id: [node_ids]}` where community 0 is the largest community; IDs are stable run-to-run because the partition is seeded (`_RANDOM_SEED = 42`) and re-indexed by `(-size, smallest-member)`. Oversized communities (>25% of the graph, min 10 nodes) are split by a second pass.
- `to_json(G, communities, output_path)` writes a node-link JSON with per-node `community` / `norm_label` and per-link `confidence_score`, sorted and `sort_keys=True` so the file is byte-identical across runs.
- `is_git_repo` / `resolve_git_dir` / `submodule_paths` recognise git working trees (plain, submodule, worktree) by pure filesystem reads; malformed input is reported as "not a repo" rather than raised.

## Contracts

Extraction driver:
- `extract(paths: list[Path], cache_root: Path | None = None) -> dict` — `pipeline/extract/__init__.py:118-249`
- `collect_files(target: Path, *, follow_symlinks=False, root: Path | None = None) -> list[Path]` — `pipeline/extract/__init__.py:252-293`
- `_check_tree_sitter_version() -> None` — raises if `tree_sitter` is missing or older than Language API v2 — `pipeline/extract/__init__.py:61-75`

Generic per-language driver and shared helpers:
- `_extract_generic(path: Path, config: LanguageConfig) -> dict` — the ~600-line workhorse: walk → nodes/edges, then a call-graph pass — `pipeline/extract/generic.py:23-650`
- `LanguageConfig` dataclass — the parametric knobs every wrapper hands to `_extract_generic` — `pipeline/extract/config.py:12-47`
- `_make_id(*parts: str) -> str` — `pipeline/extract/common.py:12-16`
- `_read_text(node, source: bytes) -> str` — `pipeline/extract/common.py:17-18`
- `_find_body(node, config) ` — `pipeline/extract/common.py:21-29`

Cross-file resolution:
- `_resolve_cross_file_imports(per_file, paths) -> list[dict]` — Python — `pipeline/extract/resolve.py:17-146`
- `_resolve_cross_file_java_imports(per_file, paths) -> list[dict]` — Java — `pipeline/extract/resolve.py:149-231`

Clustering:
- `cluster(G: nx.Graph) -> dict[int, list[str]]` — `analysis/cluster.py:63-110`
- `_partition(G) -> dict[str, int]` — Leiden-then-Louvain, both seeded with `_RANDOM_SEED` — `analysis/cluster.py:25-56`
- `_split_community(G, nodes) -> list[list[str]]` — `analysis/cluster.py:113-128`

Export:
- `to_json(G, communities: dict[int, list[str]], output_path: str) -> None` — `export/graph.py:23-43`
- `_node_community_map(communities) -> dict[str, int]` — `export/common.py:10-12`
- `_strip_diacritics(text: str) -> str` — `export/common.py:15-17`

Per-file cache:
- `file_hash(path, root=Path(".")) -> str` — content-only SHA256, frontmatter-stripped for `.md` — `pipeline/io/cache.py:20-40`
- `cache_dir(root=Path(".")) -> Path` — honours `DUMMYINDEX_CACHE_DIR` — `pipeline/io/cache.py:43-57`
- `load_cached(path, root) -> dict | None` / `save_cached(path, result, root) -> None` — `pipeline/io/cache.py:60-108`

Git detection (pure filesystem):
- `is_git_repo(root) -> bool` — `pipeline/io/git.py:24-35`
- `resolve_git_dir(root) -> Path | None` — `pipeline/io/git.py:38-59`
- `submodule_paths(root) -> tuple[Path, ...]` — `pipeline/io/git.py:62-84`

Textual references (build-phase consumer of this backbone):
- `_derive_textual_references(effective_files, root_abs, file_ids_by_rel, cross_edges) -> None` — single-pass compiled-regex matcher, mutates `cross_edges` in place — `pipeline/build/references.py:16-103`

## Examples

Happy-path trace — index a two-file Python project:

1. `collect_files(Path("proj"))` globs `proj/**/*.py` (skipping dot-dirs and ignore-matched files) and returns `[proj/auth.py, proj/models.py]` (sorted).
2. `extract([proj/auth.py, proj/models.py])`:
   - `_check_tree_sitter_version()` passes.
   - Common root is computed as `proj/`; cache root defaults to it.
   - For each file, `load_cached` misses (first run), so `_DISPATCH[".py"]` → `extract_python` → `_extract_generic` parses it. `auth.py` yields a file node `auth`, a class node `auth_digestauth` (label `DigestAuth`) via `add_node`/`add_edge` (`generic.py:56-77,104-106`), method nodes, and a `contains` edge. The result is written to `.context/cache/<sha256>.json`.
   - The call-graph pass (`generic.py:341-618`) resolves in-file calls to `calls` edges; unresolved callees are recorded in `raw_calls`.
   - `_resolve_cross_file_imports` re-parses `auth.py`, sees `from .models import Response`, looks up `Response` in the global stem→entity map, and emits `auth_digestauth --uses--> models_response` (INFERRED, weight 0.8) — `resolve.py:128-140`.
   - The global-label call resolution loop (`__init__.py:216-242`) wires any remaining `raw_calls` to `calls` edges with confidence_score 0.8.
   - Returns `{"nodes": [...], "edges": [...], "input_tokens": 0, "output_tokens": 0}`.
3. A `networkx` graph is built from those nodes/edges elsewhere in the build, then `cluster(G)` seeds Leiden with 42, splits any community over 25% of the graph, and re-indexes by `(-size, smallest-member)` so community 0 is the largest — stable across reruns (`cluster.py:109-110`).
4. `to_json(G, communities, ".context/features/symbol-graph.json")` attaches `community`/`norm_label`/`confidence_score`, sorts nodes by `id` and links by `(source, target, relation)`, and dumps with `sort_keys=True` — a byte-identical artifact every run (`graph.py:40-43`).

Re-run with no edits: every `load_cached` hits, no file is re-parsed, and steps 3–4 reproduce the identical `symbol-graph.json`.
