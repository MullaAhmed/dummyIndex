# extraction-pipeline — spec

`confidence: INFERRED`

## Intent

This feature is the deterministic backbone of dummyindex: it turns a pile of source files into a structural symbol graph without ever calling an LLM. It parses each file with tree-sitter to find classes, functions, methods, imports and call sites; resolves a subset of those references across files; caches each file's result by content hash, scoped to the package version that wrote it, so a re-run re-parses only what changed and an upgrade never reuses an older extractor's output; groups the graph into communities with a seeded, always-available algorithm; and stores the graph, plus a derived rank shortlist and community roll-up, as byte-stable JSON. A graph too large for one bounded file is published as a manifest over content-addressed shards, and only the current generation is kept on disk. Determinism is a hard requirement: the same inputs always give the same node IDs, the same community IDs and byte-identical artifacts.

## User-visible behavior

- **Extraction.** `extract(paths)` dispatches each file by extension (`.blade.php` is matched by name first) and returns `nodes`, `edges`, `file_bytes`, `file_status` and zeroed token counts. `file_status[str(path)]` is `{"state", "reason"}`: `"parsed"`; `"unsupported"` for an extension with no extractor (the file gets an empty result, and the reason says file navigation still works); `"pending"` when the extractor returns an `error` (reason truncated to 1000 chars). An errored result is never cached and never aborts the batch. `context/build/coverage.py:50` consumes `file_status`.
- **Per-file cache.** Each result is stored at `<cache>/<sha256-of-content>.json`, so a `mv` or a different cwd still hits. For `.md` files the YAML frontmatter is stripped before hashing, and the closing fence must be a bare `---` line. A corrupt or foreign-shaped entry is a miss and triggers a re-extract, never a partial merge.
- **Version-scoped cache.** Every `context` layout migration that receives a package version compares `<cache>/extraction-version` with that version. On a mismatch, or a missing or unreadable stamp, it deletes every direct child named `<64-hex>.json` that is a regular, non-linked file, then rewrites the stamp atomically. Links, subdirectories and other files (`manifest.json`, plans, locks) are untouched. If any deletion fails the stamp is not written, so the next run retries. A missing cache dir returns 0 and is never created.
- **Single-read invariant (P2).** Within one `extract` call each source file is read from disk at most once. The hash, the extractor, the Python rationale post-pass, the dispatch post-pass and the cross-file re-parse all go through one memoized seam, so every pass sees the same bytes. Those bytes leave through `file_bytes`, and the textual-reference pass decodes them instead of re-reading.
- **Symlink containment.** `collect_files(..., follow_symlinks=True)` drops any leaf whose realpath escapes the containment root (`root`, else `target`) before it is emitted, so no read ever touches it. The check runs at walk time, so a symlink swapped after enumeration (TOCTOU) remains a residual risk.
- **Stable IDs and cross-file edges.** Node IDs are lowercase underscore slugs built from name parts. On top of the per-file pass, the pipeline adds these edges: Python `from .x import Y` gives class-level `uses` (INFERRED, weight 0.8); Java `import a.b.C;` gives file-level `imports` (EXTRACTED); unresolved in-file calls are matched against a global label index to add `calls` (INFERRED, `confidence_score` 0.8). A label that more than one distinct node normalizes to is skipped, never bound to whichever node was iterated last.
- **Python dispatch idioms.** An enum-keyed dict value that names a known extracted symbol (`{ContextSubcommand.SCAN_CHECK: scan.run}`) yields a `calls` edge from the enclosing scope. A function-body `from X import Y` yields the `imports_from` edge the module-level handler would emit. The pass favors precision over recall: a `module.attr` value resolves only through an import binding's real module stem, ambiguous `(stem, name)` keys and shadowed names are skipped, and nested `a.b.c` or call-result values are never guessed. All of these edges are INFERRED with score 0.8 and deduped against the extracted edges.
- **Communities.** `cluster(G)` returns `{community_id: sorted node_ids}`. Community 0 is the largest, and ties break on the smallest member. Isolates become singleton communities. A community larger than 25% of the graph (and at least 10 nodes) is split by a second pass. The committed partition is NetworkX-Louvain only, seeded with 42, so it does not depend on whether graspologic is installed.
- **Symbol-graph storage.** `to_json` adds per-node `community`/`norm_label` and a default per-link `confidence_score`, then hands the payload to the shared writer. That writer canonicalizes it: nodes, links and hyperedges are sorted by total keys, hyperedges are stored once at the top level, and the output is compact UTF-8 JSON with `sort_keys`, no NaN and a trailing newline. If the payload is at most 1,000,000 bytes, `symbol-graph.json` is plain node-link JSON. If it is larger, the file becomes a manifest (`"format": "dummyindex-symbol-graph"`, version 1) that references per-family shards at `symbol-graph.parts/<sha256>.json`, none of them over the cap. Publication writes shards first, repairing any that hold the wrong bytes and touching any it reuses, then swaps the manifest in atomically, then prunes. Any shard outside the new generation is deleted once its mtime is older than 600 s. A plain publish after a sharded one removes the parts dir once it empties. A record or manifest that is too large on its own is rejected before anything is written, so the previous graph stays readable.
- **Reading the graph.** `read_graph_payload` returns legacy plain JSON as-is, renaming `edges` to `links`. For a manifest it verifies every shard (path, size, sha256, family, count) and the hash of the assembled payload, and never returns a partial graph. A reader holding a superseded manifest fails closed: a missing shard raises `GraphStorageError` naming `dummyindex context rebuild --changed`.
- **Derived artifacts.** On the context-build path, the same in-memory graph also produces `features/seed-rank.json` (a personalized-PageRank shortlist for the scan seed) and `features/graph-communities.json` (one card per community, with the owning feature read from the on-disk taxonomy when there is one). A failure there only warns, and `symbol-graph.json` still lands. `rebuild --changed` regenerates these files and never writes the curated `features/graph.json`.
- **Git detection.** `is_git_repo`, `resolve_git_dir` and `submodule_paths` recognize plain checkouts, submodules and worktrees by reading the filesystem only. Malformed input is reported as "not a repo" and never raises.

## Contracts

Path confinement (`pipeline/io/paths.py`, re-exported at `pipeline/io/__init__.py:24`):
- `resolve_under_root(candidate: Path, root: Path) -> Path | None` — `paths.py:18-34`. Pure apart from `resolve()`. Returns the resolved path if it is `root` or a descendant, else `None`. Catches both `../` traversal and absolute joins. Callers: `cache_dir`, `collect_files`, `context/build/incremental.py:91`, `context/domains/reality_check/verify.py:251`.
- `is_safe_read_target(path: Path, *, max_bytes: int) -> bool` — `paths.py:37-53`. Uses `lstat` to reject symlinks, non-regular files and anything over `max_bytes`. Any `OSError` returns `False`.

Read seam and per-file cache (`pipeline/io/cache.py`):
- `read_source_bytes(path: Path) -> bytes` — `cache.py:61-77`. Inside a build read cache, memoized by `str(path)`.
- `build_read_cache() -> Iterator[None]` — `cache.py:41-58`. A nested entry reuses the outer cache, and the cache is cleared on exit.
- `file_hash(path, root=Path(".")) -> str` — `cache.py:107-121`. SHA-256 of the content only (`root` is ignored), with `.md` frontmatter stripped by `_body_content` (`cache.py:91-104`).
- `cache_dir(root=Path(".")) -> Path` — `cache.py:124-141`. If set, the trusted in-process dir from `set_trusted_cache_dir` (`cache.py:80-88`, driven by `cache_dir_override`) wins unconditionally. Otherwise an ambient `DUMMYINDEX_CACHE_DIR` is honored only when it resolves inside `root`. An out-of-repo value is silently ignored in favor of `<root>/.context/cache/`. Creates the dir.
- `load_cached(path, root) -> dict | None` — `cache.py:260-282`, guarded by `_is_valid_cache_payload` (`cache.py:240-257`): the payload must be a dict, `nodes` and `edges` must be lists, and every node needs a string `id`. Unknown keys are ignored.
- `save_cached(path, result, root) -> None` — `cache.py:285-311`. Writes `json.dumps(result, sort_keys=True)` through a `<hash>.tmp` sibling and `os.replace`, falling back to copy-then-delete on a Windows `PermissionError`. A path that is not a regular file is a no-op.
- `scope_cache_to_version(cache_dir: Path, version: str) -> int` — `cache.py:195-237`. Returns the number of entries deleted. Entry-name regex at `cache.py:29`, stamp name `extraction-version` at `cache.py:32`. The stamp is written by `_write_bytes_atomic` (`cache.py:144-174`). Called from `migrate_context_layout` (`context/build/upgrade.py:539-546`) with `context_dir / "cache"` and reported as `"cache: N stale extraction entries"`. `context/build/runner.py:126` and `context/build/enriched_refresh.py:107` pass the package version. `cli/enrich.py:37` passes `None`, which skips this step.

Extraction driver (`pipeline/extract/__init__.py`):
- `extract(paths: list[Path], cache_root: Path | None = None) -> dict` — `extract/__init__.py:111-329`. The common path prefix is the cache root unless `cache_root` is given. The per-file and cross-file passes run inside one `build_read_cache()` (`extract/__init__.py:147-277`).
- `collect_files(target: Path, *, follow_symlinks=False, root: Path | None = None) -> list[Path]` — `extract/__init__.py:332-412`. Skips dot-paths and `.dummyindexignore` matches and returns sorted paths.
- `_check_tree_sitter_version() -> None` — `extract/__init__.py:53-68`. Raises `ImportError` if tree-sitter is missing and `RuntimeError` if `LANGUAGE_VERSION < 14`.
- `_DISPATCH` (extension → extractor) — `extract/__init__.py:71-106`.

Per-language extraction:
- `_extract_generic(path: Path, config: LanguageConfig) -> dict` — `generic.py:22-773`. Returns `{nodes, edges, raw_calls}` (`generic.py:773`), or `{nodes: [], edges: [], error}` when the grammar is missing or the parse fails (`generic.py:33-50`). Reads the source through `read_source_bytes` (`generic.py:46`).
- `LanguageConfig` dataclass — `config.py:14-48`.
- `_make_id(*parts) -> str` — `extract/common.py:15-19`; `_read_text(node, source) -> str` — `extract/common.py:22-23`; `_find_body(node, config)` — `extract/common.py:26-34`.

Cross-file resolution (both re-read through `read_source_bytes`):
- `_resolve_cross_file_imports(per_file, paths) -> list[dict]` — `resolve.py:19-152`. Emits `uses` at `resolve.py:131-146`.
- `_resolve_cross_file_java_imports(per_file, paths) -> list[dict]` — `resolve.py:155-239`.

Python dispatch idioms (`pipeline/extract/python_dispatch.py`):
- `_resolve_python_dispatch(per_file: list[dict], paths: list[Path]) -> list[dict]` — `python_dispatch.py:413-470`. Returns `[]` without `tree_sitter_python`. Skips a file whose cached result uses another path shape (`file_nid not in file_node_ids`) and any file that fails to parse. Its caller (`extract/__init__.py:192-216`) runs it before the `id_remap` pass, dedups its edges by `(source, target, relation)` and turns any exception into a logged warning.
- `_build_symbol_index(per_file) -> (index, ambiguous)` — `python_dispatch.py:62-86`. Maps `(module stem, name) → node id`. A key claimed by more than one file or node id goes into `ambiguous`.
- `_collect_bindings(root, source) -> (bound_names, from_stems, module_stems)` — `python_dispatch.py:102-187`. `module_stems` maps every import-bound object (`import x [as y]`, `from pkg import x [as y]`) to its real module stem. A name bound ambiguously is dropped.
- `_resolve_dict_value(scan, value, shadowed) -> str | None` — `python_dispatch.py:273-304`; `_walk_file(scan, node, scope_nid, fn_depth, shadowed)` — `python_dispatch.py:351-410`.

Clustering (`analysis/cluster.py`):
- `cluster(G: nx.Graph) -> dict[int, list[str]]` — `cluster.py:80-125`. Converts a DiGraph to undirected first.
- `_partition(G)` — `cluster.py:67-73`. The committed path; it delegates only to `_louvain_partition` (`cluster.py:32-45`).
- `_leiden_partition(G)` — `cluster.py:48-64`. Off the committed path. Raises `ImportError` when graspologic is absent.
- `_split_community(G, nodes)` — `cluster.py:128-146`. A second `_partition` pass that returns the community unsplit if that pass raises.

Export and storage (`export/`):
- `to_json(G, communities, output_path: str, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> None` — `export/graph.py:24-45`. The default `confidence_score` comes from `_CONFIDENCE_SCORE_DEFAULTS` (EXTRACTED 1.0, INFERRED 0.5, AMBIGUOUS 0.2; `export/common.py:9-13`).
- `write_graph_payload(payload: Mapping, output_path, *, max_file_bytes=DEFAULT_MAX_FILE_BYTES) -> None` — `storage.py:332-402`. Canonicalization by `_canonical_payload` (`storage.py:140-184`), which raises on the reserved format marker, conflicting `links`/`edges`, or conflicting hyperedge copies. Shards are packed by `_shards` (`storage.py:187-206`) and pruned by `_prune_shards` (`storage.py:276-329`).
- `read_graph_payload(path) -> dict` — `storage.py:489-503`. Manifest verification in `_read_manifest` (`storage.py:409-486`). Consumers, all under `dummyindex/context/`: `build/runner.py:213`, `domains/features/indexes.py:137`, `domains/features/scan/refs.py:65`, `domains/graph_query/load.py:64`, `domains/reality_check/verify.py:376` and `output/viewer/extras.py:191`.
- `shard_names(manifest_path) -> frozenset[str]` — `storage.py:228-252`. The `<sha256>.json` names a manifest references, read under the byte cap. Returns an empty set for a missing, oversized, undecodable or plain file.
- `GraphStorageError(ValueError)` — `storage.py:36-37`. `DEFAULT_MAX_FILE_BYTES = 1_000_000` and `SHARD_GRACE_SECONDS = 600` — `storage.py:25-26`.
- `_node_community_map(communities) -> dict[str, int]` — `export/common.py:16-18`; `_strip_diacritics(text) -> str` — `export/common.py:21-23`.

Derived graph artifacts (`context/build/communities.py`, called from `build_graph` at `context/build/graph.py:64-74`):
- `compute_symbol_rank(g: nx.Graph) -> dict[str, float]` — `communities.py:56-73`. Personalized PageRank by pure-Python power iteration (`_pagerank`, `communities.py:76-113`) with alpha 0.85, at most 100 iterations and tol 1e-6. If it has not converged, it returns the last iterate. An empty graph returns `{}`.
- `build_seed_rank(scores, node_by_id, *, top_n=500) -> SeedRank` — `communities.py:116-132`. Drops rationale nodes, rounds scores to 8 decimals, sorts by `(-score, id)` and truncates.
- `write_graph_artifacts(g, communities, features_dir, *, root=None) -> tuple[str, ...]` — `communities.py:135-171`. Writes seed-rank, then graph-communities (`rollup_communities`), and returns their `.context/`-relative names. `root` falls back to the root recorded in `meta.json` (`_indexed_root`, `communities.py:314-325`).
- Personalization — `communities.py:177-221`. Entry points (call-subgraph sources over `calls`/`uses`, with orientation taken from `_src`/`_tgt`) get 3.0, other source nodes 1.0, and test paths 0.1 (`_is_test_path`).

Git detection (`pipeline/io/git.py`):
- `is_git_repo(root) -> bool` — `git.py:19-30`; `resolve_git_dir(root) -> Path | None` — `git.py:33-49`, which follows `commondir` for worktrees; `submodule_paths(root) -> tuple[Path, ...]` — `git.py:52-74`.

Textual references (a build-phase consumer, not owned here):
- `_derive_textual_references(effective_files, root_abs, file_ids_by_rel, cross_edges, *, file_bytes=None) -> None` — `pipeline/build/references.py:19-97`. A path present in `file_bytes` is decoded by `_text_for_scan` (`references.py:156-168`). Any other path falls back to `_read_text_safely`.

## Examples

Index a two-file Python project:

1. `collect_files(Path("proj"))` returns `[proj/auth.py, proj/models.py]` (sorted).
2. `extract([...])` checks tree-sitter, takes `proj/` as the cache root and opens one `build_read_cache()`. On the first run `load_cached` misses, so `_DISPATCH[".py"]` → `extract_python` → `_extract_generic` emits the file node `auth`, the class `auth_digestauth` (label `DigestAuth`), its methods and `contains` edges. The result is saved to `<cache>/<sha256>.json` and the status is `"parsed"`. The call-graph pass (`generic.py:421-737`) records callees it cannot resolve in `raw_calls`.
3. The dispatch post-pass, then `id_remap`, then `_resolve_cross_file_imports` run in that order. The last one sees `from .models import Response` and emits `auth_digestauth --uses--> models_response`. Outside the read cache, the global-label loop (`extract/__init__.py:279-320`) binds the remaining unambiguous `raw_calls`.
4. `build_graph` (`context/build/graph.py:34-82`) builds the graph, calls `cluster` (seeded Louvain) and then `to_json(..., "features/symbol-graph.json")`. The compact payload is under 1 MB, so the result is one plain file and any aged shards left from an earlier sharded generation are pruned. `write_graph_artifacts` then writes the seed-rank and graph-communities files.

Re-run with no edits: every `load_cached` hits and no file is re-parsed, so the output is byte-identical. After a package upgrade, the layout migration finds a stale `extraction-version`, deletes the old entries and restamps, and the next `extract` re-parses everything once.

Large graph: compact JSON over 1,000,000 bytes is split into `nodes`/`links`/`hyperedges` shards under `features/symbol-graph.parts/`, and `symbol-graph.json` becomes the manifest. A later publish keeps only the shards its new manifest (or a concurrently published live one) references, and deletes the rest once they are 600 s old. A process still holding the old manifest gets `GraphStorageError: graph shard missing: …; run \`dummyindex context rebuild --changed\``.
