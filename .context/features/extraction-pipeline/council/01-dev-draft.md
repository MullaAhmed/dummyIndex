# extraction-pipeline — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/pipeline/extract/`: the tree-sitter front end.
  - `__init__.py` holds `extract`, `collect_files` and `_DISPATCH`. `generic.py` holds `_extract_generic`, `config.py` holds `LanguageConfig`, and `common.py` holds the id, text and body helpers.
  - `imports.py` and `helpers.py` hold the per-language import handlers and extra walks. `language_configs.py` defines one config per language.
  - `languages/` holds the extractors. Most are thin `_extract_generic` wrappers in `languages/wrappers.py`. Go, Rust, Julia, Elixir, Verilog, Zig, Dart, PowerShell and Blade use custom walks.
  - `python_rationale.py` is the docstring/rationale post-pass. `resolve.py` holds the Python and Java cross-file resolvers. `python_dispatch.py` is the dispatch-idiom post-pass.
- `dummyindex/pipeline/io/`:
  - `cache.py` holds the read seam, the content-hash cache and the version scoping.
  - `paths.py` holds the confinement primitives. `git.py` handles repo detection.
  - `detect.py` lives here but is not owned by this feature.
- `dummyindex/analysis/cluster.py`: community detection.
- `dummyindex/export/`:
  - `graph.py` holds `to_json` and `common.py` holds the score defaults and helpers.
  - `storage.py` is the bounded, sharded symbol-graph writer and the one shared reader.
- `dummyindex/context/build/communities.py`: seed-rank and graph-communities.
- Wiring hosts outside every feature: `context/build/graph.py` (`build_graph`), `runner.py`, `enriched_refresh.py`, and `upgrade.py` (`migrate_context_layout` runs `scope_cache_to_version`).
- Tests:
  - `tests/pipeline/extract/`: `test_extract_hardening.py`, `test_python_dispatch.py`, `test_python_rationale.py`.
  - `tests/pipeline/io/`: `test_cache.py`, `test_git.py`, `test_paths.py`.
  - `tests/pipeline/build/`: `test_references.py`, `test_p2_read_counter.py`.
  - `tests/analysis/test_cluster_determinism.py`.
  - `tests/export/`: `test_graph_determinism.py`, `test_graph_storage.py` (retention, pruning, repair, fail-closed).
  - `tests/context/domains/test_graph_storage_consumers.py` and `tests/context/build/test_communities.py`.

## Architecture in three sentences

`extract()` runs a per-file structural pass, in which each extension maps to an extractor and each result is cached by content hash. A cross-file synthesis pass follows: dispatch idioms, then `id_remap`, then Python/Java imports, then the global-label calls. Every source read in both passes goes through one memoized `read_source_bytes` seam.

`build_graph` turns that output into an undirected NetworkX graph and clusters it with seeded Louvain. It then exports through `to_json` → `write_graph_payload`, which canonicalizes the payload, publishes it plain or as a manifest over shards, and prunes old shards. Last, it derives seed-rank and graph-communities from the same in-memory graph.

Every consumer reads the graph only through `read_graph_payload`. Cache and shard housekeeping happens at write or migration time and never on read. The whole chain makes no LLM calls and is byte-deterministic.

## Data model

- **Node**: `{id, label, file_type, source_file, source_location: "L<n>"}` (`generic.py:66-78`).
  - Labels carry shape markers (`"Foo"`, `"bar()"`, `".method()"`), and the resolvers and the label index strip them (`extract/__init__.py:316-317`).
- **Edge**: `{source, target, relation, confidence, source_file, source_location, weight}`, sometimes with `confidence_score`.
  - `confidence` is a `ConfidenceLevel`: EXTRACTED, INFERRED or AMBIGUOUS.
  - Relations include `contains`, `method`, `calls`, `inherits`/`extends`/`implements`, `imports`/`imports_from`, `uses`, `uses_static_prop`, `references_constant`, `bound_to`, `listened_by` and `references`.
- **Per-file result**: the per-file result is `{nodes, edges, raw_calls}` (`generic.py:779`) or `{nodes: [], edges: [], error}`.
  - `extract()` merges these and adds `file_bytes` and `file_status` (`extract/__init__.py:355-362`).
- **Cache dir** (`.context/cache/`, gitignored, per machine): flat `<sha256>.json` entries, plus the `extraction-version` stamp (`"<version>\n"`), plus files the cache does not own, such as the drift `manifest.json`.
  - Only names matching `cache.py:30` are ever deleted.
- **`symbol-graph.json`, plain form**: canonical node-link with `nodes`, `links`, one top-level `hyperedges` and `graph` metadata, with the hyperedge copy removed (`storage.py:148-192`).
- **`symbol-graph.json`, manifest form** (`storage.py:385-393`): `{format, version, max_file_bytes, graph_sha256, counts{nodes,links,hyperedges}, metadata, shards[{kind, path, sha256, bytes, count}]}`.
  - Each shard file is `{"kind": <family>, "records": [...]}` (`storage.py:196-197`).
  - `graph_sha256` hashes the canonical compact bytes that a plain write would produce (`storage.py:367`), and the reader re-hashes the assembled result against it (`storage.py:492`).
- **`seed-rank.json`**: `SeedRank.to_dict()`, a list of `RankEntry{id, score}`, consumed by `context/domains/features/scan/rank.py`.
- **`graph-communities.json`**: `rollup_communities(...).to_dict()` (`context/domains/features/communities.py`).
  - Features claim members in sorted-`feature_id` order, and a symbol is unowned when no taxonomy exists.
  - Rationale quotes come from `rationale_for` edges, and the earliest source line wins (`context/build/communities.py:240-276`).

## Key decisions

- **Determinism comes from named seams, not assumption.**
  - The seeded partition (`cluster.py:14,47`) and the content-determined re-index (`cluster.py:139-140`).
  - Canonical record sorting (`storage.py:173-191`) and compact `sort_keys` encoding (`storage.py:56-69`).
  - Sorted file collection (`extract/__init__.py:412,449`) and slug IDs (`extract/common.py:15-19`).
  - Sorting lives in the shared writer, not in `to_json`, so every graph payload published through `write_graph_payload` gets one canonical form.
- **Committed bytes never depend on an optional backend.**
  - `_partition` is Louvain-only (`cluster.py:77-84`). graspologic Leiden stays off-path, and its ANSI output is muted only inside `_leiden_partition` (`cluster.py:67-73`, issue #19).
  - PageRank is a pure-Python power iteration, not scipy-backed `networkx.pagerank` (`context/build/communities.py:66-86`). It walks nodes in insertion order (`context/build/communities.py:102`) and rounds scores to 8 decimals.
- **One parametric driver.** `_extract_generic` (`generic.py:28-779`) absorbs the walk and call-graph logic. Language differences live in `LanguageConfig` data plus a few `ts_module` branches. The module documents itself as indivisible and an accepted exception to the file-size convention (`generic.py:10-12`).
- **The cache key is content; the version is scoped out of band.**
  - Path-free hashing (`cache.py:116-136`) survives `mv` and cwd changes.
  - Upgrades are handled by stamp-and-wipe (`cache.py:225-279`) rather than by putting the version in the key. Entry names stay content-addressed, and the migration can report a count.
  - Holding back the stamp after any failed delete (`cache.py:276-278`) makes the step safe to retry.
  - `_write_bytes_atomic` duplicates `atomic_io._replace_bytes` because the layering is one-way, `context → pipeline` (`cache.py:174-179`).
- **Bounded storage keeps only the current generation.**
  - Shards are named by content, so reuse verifies itself. A shard with the right bytes is touched and reused, and one with the wrong bytes is rewritten instead of raising (`storage.py:399-406`).
  - The manifest is published last and atomically, so a failed publish leaves the previous generation readable and deletes nothing (`storage.py:407-410`).
  - Pruning protects `keep | shard_names(live manifest)` so that a concurrent writer's generation survives.
  - A 600 s mtime grace window plus `_touch` covers writers that are mid-publish.
  - Pruning never deletes links, reparse points, non-regular files or foreign names, and a failure only warns, listing at most 5 items (`storage.py:284-337`).
  - The cost is that a reader holding a superseded manifest fails closed instead of finishing (`storage.py:7-12`). The earlier never-delete policy left every superseded shard behind across upgrades (commit `0634bfd`).
  - The parts dir is shared, so the supported layout is one manifest per directory (`storage.py:14-15`).
- **Storage paths are hostile-input safe.**
  - `_plain_path` rejects backslashes, absolute and drive paths, `..`, any symlink or reparse-point component, and any path that escapes after resolution (`storage.py:76-110`).
  - `_read_bytes` opens with `O_NOFOLLOW | O_NONBLOCK` and checks for a regular file and the byte cap via `fstat` (`storage.py:113-135`).
- **Errors are isolated, never fatal.**
  - A per-file `error` result is never cached.
  - Dispatch and cross-file failures are logged as warnings (`extract/__init__.py:231-238,288-308`).
  - The git helpers never raise (`git.py:11-13`).
  - A failure in the derived artifacts warns, and the symbol graph still lands (`context/build/graph.py:77-87`).
- **Dispatch runs before `id_remap`** (`extract/__init__.py:223-247`), so the edges it sources from file nodes are remapped with everything else.
- **Textual references use one regex pass.** `_build_matcher` (`pipeline/build/references.py:120-137`) compiles a lookahead alternation over every needle. This is documented as a constant-factor win, not an asymptotic one (`references.py:74-78`). The basename fallback is gated on a length of at least 5 and on uniqueness.

## Open questions

- `save_cached` still writes through a fixed `<hash>.tmp` sibling (`cache.py:344`), while the stamp writer uses a unique `NamedTemporaryFile`. Two concurrent saves of identical content share one tmp, and `scope_cache_to_version` never sweeps stray `*.tmp` files.
- Version scoping only targets `context_dir / "cache"` (`context/build/upgrade.py:583`), so an in-repo `DUMMYINDEX_CACHE_DIR` cache is never scoped. `cli/enrich.py:40` passes `package_version=None`, so enrich never scopes. It is unclear whether either is intended.
- Some in-source comments lag the code, and the code wins:
  - The `extract` module docstring omits `file_status` (`extract/__init__.py:6-11`).
  - `build_graph` says "Leiden communities" (`context/build/graph.py:52`).
  - `extract/__init__.py:417` cites `cache.py:38`/`generic.py:42`; the reads are now at `cache.py:134` and `generic.py:52`.
  - `context/build/graph.py:73` says the exporter lacks a final newline, but `_json_bytes` appends one (`storage.py:66`).
  - `generic.py:10` says "~600 lines", but the function is 752 lines.
