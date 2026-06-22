# extraction-pipeline — spec

`confidence: INFERRED`

## Intent

This feature is the deterministic backbone of dummyindex: it turns a pile of source files into a structural symbol graph without ever calling an LLM. It parses each file with tree-sitter to find classes, functions, methods, imports and call sites; it resolves a subset of those references across files; it caches per-file results by content hash so re-runs only re-parse what changed; it groups the resulting graph into communities with a fixed-seed Leiden (falling back to Louvain); and it serialises the graph to a byte-stable JSON artifact. Determinism is a first-class requirement throughout — given the same inputs, every run produces the same node IDs, the same community IDs, and a byte-identical `symbol-graph.json`.

## User-visible behavior

- `extract(paths)` walks a list of files, dispatches each by extension to a language extractor, and returns `{"nodes": [...], "edges": [...], "file_bytes": {str(path): bytes}, "input_tokens": 0, "output_tokens": 0}`. Unsupported extensions are silently skipped; per-file parse errors are isolated to that file (the file contributes an `error` result, no nodes/edges) and never abort the batch. `file_bytes` carries the source bytes the extraction already read so the downstream textual-reference pass (`build/references.py` via `build/structure.py`) decodes those cached bytes instead of re-reading disk (P2).
- Re-running `extract` on an unchanged tree is fast: each file's result is loaded from `.context/cache/<sha256>.json` instead of being re-parsed. The cache key is the file's content hash, so a `mv` or a different cwd still hits the cache; for `.md` files the YAML frontmatter is stripped before hashing so metadata edits don't invalidate. The closing frontmatter fence is matched line-anchored (`^---\s*$`), so an in-body `---hack` token no longer truncates the hashed body. `load_cached` re-extracts (returns a miss, never a partial merge) on a corrupt/foreign-shaped entry — a non-dict payload, non-list `nodes`/`edges`, or a node missing a string `id` — but a well-formed entry written by `save_cached` still hits (accept-superset schema, no mass invalidation).
- **Single-read invariant (P2).** Within one `extract` call every source file's bytes are read at most once: the hash read, the extractor read, the Python-rationale post-pass, and the cross-file import re-parse all funnel through one `read_source_bytes(path)` seam, memoized for the build by a `build_read_cache()` context manager. All passes therefore see one consistent byte-state — a file mutated mid-build no longer yields a stale-node/new-byte mix. The captured bytes are threaded out via `file_bytes` so the later textual-reference pass reuses them rather than re-reading (≤2 reads per file across the whole build).
- **Symlink containment.** When `collect_files(..., follow_symlinks=True)` walks a tree, a leaf whose realpath escapes the containment root (the explicit `root`, else `target`) is filtered out **at leaf emission** via `resolve_under_root`, before either read sink ever touches it — so an out-of-tree symlink target is never read into the graph. This is walk-time containment; a post-enumeration symlink swap (TOCTOU) is a documented residual.
- Node IDs are stable, lowercase, alphanumeric-with-underscores slugs derived from name parts (`_make_id`), so the same symbol gets the same ID run-to-run and machine-to-machine.
- Cross-file edges are added on top of the per-file pass: Python `from .x import Y` becomes class-level `uses` (INFERRED) edges, Java `import a.b.C;` becomes file-level `imports` (EXTRACTED) edges, and unresolved in-file calls are matched against a global label index to add `calls` (INFERRED) edges.
- `cluster(G)` returns `{community_id: [node_ids]}` where community 0 is the largest community; IDs are stable run-to-run because the partition is seeded (`_RANDOM_SEED = 42`) and re-indexed by `(-size, smallest-member)`. Oversized communities (>25% of the graph, min 10 nodes) are split by a second pass. The committed `community` field is produced by **NetworkX-Louvain only** (GATE strategy (b), `spec.md` 2026-06-23) — `_partition` calls `_louvain_partition`, never Leiden — so the persisted partition is byte-reproducible across machines regardless of whether graspologic is installed. Leiden (`_leiden_partition`) remains available off the committed path for non-committed/on-demand use only.
- `to_json(G, communities, output_path)` writes a node-link JSON with per-node `community` / `norm_label` and per-link `confidence_score`, sorted and `sort_keys=True` so the file is byte-identical across runs. `hyperedges` are sorted by a **total** key (`json.dumps(h, sort_keys=True)` — the hyperedge schema is open, so a single field is insufficient) at both emission sites: the top-level `data["hyperedges"]` and the `data["graph"]["hyperedges"]` copy that `node_link_data` carries over from `G.graph`.
- `is_git_repo` / `resolve_git_dir` / `submodule_paths` recognise git working trees (plain, submodule, worktree) by pure filesystem reads; malformed input is reported as "not a repo" rather than raised.

## Contracts

Path-confinement primitive (new — the shared lowest-layer guard):
- `resolve_under_root(candidate: Path, root: Path) -> Path | None` — **pure** (only `resolve()`): returns the resolved path iff it is `root` or a descendant of `root.resolve()`, else `None`; catches both `../` traversal and absolute-path joins (`root / "/etc/x"` collapses to `/etc/x`). Accepts already-resolved and not-yet-resolved candidates. — `pipeline/io/paths.py`
- `is_safe_read_target(path: Path, *, max_bytes: int) -> bool` — **does** I/O (`os.lstat`/`os.stat`): rejects symlinks (`S_ISLNK`), non-regular files (FIFO/device/socket), and files larger than `max_bytes`; never raises (any `OSError` → `False`). — `pipeline/io/paths.py`
- Both re-exported from `pipeline/io/__init__.py`. They consolidate ~6 inline `x.resolve().relative_to(root)` guards across the codebase; migrating those call sites is a documented follow-up — this module only introduces the primitive.

Single-read seam + build read cache (new — P2):
- `read_source_bytes(path: Path) -> bytes` — the single named seam every source-byte read routes through; inside a `build_read_cache()` block the first read is memoized by `str(path)` and later reads of that path return the cached bytes. — `pipeline/io/cache.py`
- `build_read_cache() -> Iterator[None]` — context manager opening a build-scoped, path-keyed read cache; nested entries reuse the outer cache; cleared on exit so a later build re-reads disk. — `pipeline/io/cache.py`

Extraction driver:
- `extract(paths: list[Path], cache_root: Path | None = None) -> dict` — now also returns `file_bytes`; wraps its per-file + cross-file passes in one `build_read_cache()` — `pipeline/extract/__init__.py`
- `collect_files(target: Path, *, follow_symlinks=False, root: Path | None = None) -> list[Path]` — under `follow_symlinks=True`, leaves whose realpath escapes the containment root are filtered at emission via `resolve_under_root` — `pipeline/extract/__init__.py`
- `_check_tree_sitter_version() -> None` — raises if `tree_sitter` is missing or older than Language API v2 — `pipeline/extract/__init__.py`

Generic per-language driver and shared helpers:
- `_extract_generic(path: Path, config: LanguageConfig) -> dict` — the ~600-line workhorse: walk → nodes/edges, then a call-graph pass; reads source via `read_source_bytes` (the P2 seam), not `path.read_bytes` directly — `pipeline/extract/generic.py:23-650`
- `LanguageConfig` dataclass — the parametric knobs every wrapper hands to `_extract_generic` — `pipeline/extract/config.py:12-47`
- `_make_id(*parts: str) -> str` — `pipeline/extract/common.py:12-16`
- `_read_text(node, source: bytes) -> str` — `pipeline/extract/common.py:17-18`
- `_find_body(node, config) ` — `pipeline/extract/common.py:21-29`

Cross-file resolution (both re-read source via `read_source_bytes`, so a cached re-run reuses the build read cache instead of touching disk again):
- `_resolve_cross_file_imports(per_file, paths) -> list[dict]` — Python — `pipeline/extract/resolve.py:17-146`
- `_resolve_cross_file_java_imports(per_file, paths) -> list[dict]` — Java — `pipeline/extract/resolve.py:149-231`

Clustering (committed `community` is Louvain-only — GATE strategy (b)):
- `cluster(G: nx.Graph) -> dict[int, list[str]]` — `analysis/cluster.py`
- `_partition(G) -> dict[str, int]` — committed-bytes path; delegates to `_louvain_partition` only — `analysis/cluster.py`
- `_louvain_partition(G) -> dict[str, int]` — NetworkX-Louvain, seeded with `_RANDOM_SEED`; the only partition feeding committed bytes — `analysis/cluster.py`
- `_leiden_partition(G) -> dict[str, int]` — graspologic-Leiden, seeded; off the committed path, for non-committed/on-demand use, raises `ImportError` if graspologic is absent — `analysis/cluster.py`
- `_split_community(G, nodes) -> list[list[str]]` — second pass via `_partition` (Louvain) — `analysis/cluster.py`

Export:
- `to_json(G, communities: dict[int, list[str]], output_path: str) -> None` — sorts nodes, links, and `hyperedges` (total-key sort at both the top-level and `data["graph"]` copy) before `sort_keys=True` dump — `export/graph.py`
- `_node_community_map(communities) -> dict[str, int]` — `export/common.py:10-12`
- `_strip_diacritics(text: str) -> str` — `export/common.py:15-17`

Per-file cache:
- `file_hash(path, root=Path(".")) -> str` — content-only SHA256 (via `read_source_bytes`), frontmatter-stripped for `.md` (line-anchored `^---\s*$` closing fence) — `pipeline/io/cache.py`
- `cache_dir(root=Path(".")) -> Path` — two override channels: (1) the **trusted in-process** override set by `cache_dir_override`/`set_trusted_cache_dir` (`_TRUSTED_CACHE_DIR`), honored unconditionally; (2) the **ambient** `DUMMYINDEX_CACHE_DIR` env var (documented opt-out, **preserved not deprecated**) now **confined to the repo root** via `resolve_under_root` — an out-of-repo value is silently ignored and falls back to `<root>/.context/cache/`, never raises — `pipeline/io/cache.py`
- `set_trusted_cache_dir(target: Path | None) -> None` — sets/clears the trusted in-process cache dir; the channel `cache_dir_override` uses instead of the env var — `pipeline/io/cache.py`
- `load_cached(path, root) -> dict | None` — applies an **accept-superset schema guard** (`_is_valid_cache_payload`): a non-dict payload, non-list `nodes`/`edges`, or a node lacking a string `id` is a miss (re-extract, never merge); unknown keys ignored, well-formed entries still hit — `pipeline/io/cache.py`
- `save_cached(path, result, root) -> None` — dumps `json.dumps(result, sort_keys=True)` for cache-content hygiene (cache isn't committed) — `pipeline/io/cache.py`
- `_is_valid_cache_payload(payload) -> bool` — anti-corruption schema guard (not anti-poisoning; the real containment is cache-dir confinement) — `pipeline/io/cache.py`

Git detection (pure filesystem):
- `is_git_repo(root) -> bool` — `pipeline/io/git.py:24-35`
- `resolve_git_dir(root) -> Path | None` — `pipeline/io/git.py:38-59`
- `submodule_paths(root) -> tuple[Path, ...]` — `pipeline/io/git.py:62-84`

Textual references (build-phase consumer of this backbone):
- `_derive_textual_references(effective_files, root_abs, file_ids_by_rel, cross_edges, *, file_bytes=None) -> None` — single-pass compiled-regex matcher, mutates `cross_edges` in place; when `file_bytes` (the extraction's `file_bytes` map, threaded through `build_structure`) carries a scanned path, its text is decoded from those bytes via `_text_for_scan` instead of a second disk read (P2); files absent from the map fall back to `_read_text_safely` — `pipeline/build/references.py`

## Examples

Happy-path trace — index a two-file Python project:

1. `collect_files(Path("proj"))` globs `proj/**/*.py` (skipping dot-dirs and ignore-matched files) and returns `[proj/auth.py, proj/models.py]` (sorted).
2. `extract([proj/auth.py, proj/models.py])`:
   - `_check_tree_sitter_version()` passes.
   - Common root is computed as `proj/`; cache root defaults to it.
   - For each file, `load_cached` misses (first run), so `_DISPATCH[".py"]` → `extract_python` → `_extract_generic` parses it. `auth.py` yields a file node `auth`, a class node `auth_digestauth` (label `DigestAuth`) via `add_node`/`add_edge` (`generic.py:56-77,104-106`), method nodes, and a `contains` edge. The result is written to `.context/cache/<sha256>.json`.
   - The call-graph pass (`generic.py:341-618`) resolves in-file calls to `calls` edges; unresolved callees are recorded in `raw_calls`.
   - `_resolve_cross_file_imports` re-parses `auth.py`, sees `from .models import Response`, looks up `Response` in the global stem→entity map, and emits `auth_digestauth --uses--> models_response` (INFERRED, weight 0.8) — `resolve.py:128-140`.
   - The global-label call resolution loop wires any remaining `raw_calls` to `calls` edges with confidence_score 0.8 — but a label that >1 distinct node normalizes to is recorded in `ambiguous_labels` and **skipped** (never silently bound to the last-iterated node).
   - Returns `{"nodes": [...], "edges": [...], "file_bytes": {...}, "input_tokens": 0, "output_tokens": 0}`.
3. A `networkx` graph is built from those nodes/edges elsewhere in the build, then `cluster(G)` runs **NetworkX-Louvain** (committed-bytes path, GATE strategy (b)) seeded with 42, splits any community over 25% of the graph, and re-indexes by `(-size, smallest-member)` so community 0 is the largest — stable across reruns **and machines**.
4. `to_json(G, communities, ".context/features/symbol-graph.json")` attaches `community`/`norm_label`/`confidence_score`, sorts nodes by `id`, links by `(source, target, relation)`, and `hyperedges` by `json.dumps(h, sort_keys=True)`, then dumps with `sort_keys=True` — a byte-identical artifact every run.

Re-run with no edits: every `load_cached` hits, no file is re-parsed, and steps 3–4 reproduce the identical `symbol-graph.json`. The whole extraction runs inside one `build_read_cache()`, so each file is read once for the hash and reused for the cross-file resolve and the later textual-reference pass.
