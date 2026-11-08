# extraction-pipeline — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/pipeline/extract/` — the tree-sitter front end. `__init__.py` is the public surface (`extract`, `collect_files`).
- `generic.py` holds `_extract_generic`, the parametric driver. `config.py` defines `LanguageConfig`.
- `common.py` has `_make_id`, `_read_text`, `_find_body`. `imports.py` and `helpers.py` hold import handlers and extra-walk helpers.
- `language_configs.py` instantiates one `LanguageConfig` per language.
- `languages/` wraps each `extract_<lang>`. Most are thin `_extract_generic` calls (`languages/wrappers.py`).
- A few are custom walks: Go, Rust, Julia, Elixir, Verilog, Zig, Dart, PowerShell, and Blade.
- `python_rationale.py` is the Python docstring/rationale post-pass. `resolve.py` holds the two cross-file resolvers.
- `python_dispatch.py` is the narrow Python dispatch-idiom post-pass: enum-keyed dict handlers and function-body imports.
- `dummyindex/pipeline/io/` — `cache.py` (content-hash per-file cache) and `git.py` (pure-filesystem repo detection).
- `dummyindex/analysis/cluster.py` — community detection. Committed path: NetworkX-Louvain. Leiden is off-path.
- `dummyindex/export/graph.py` + `export/common.py` — node-link JSON serialisation.
- `dummyindex/context/build/communities.py` — derived graph artifacts. It holds the personalized-PageRank `features/seed-rank.json` shortlist and the `features/graph-communities.json` roll-up.
- This feature owns that module. `write_graph_artifacts` writes both after the symbol-graph export.
- Its wiring hosts stay unowned: `context/build/graph.py` (`build_graph` calls `write_graph_artifacts`), `enriched_refresh.py`, and `runner.py`. See concerns, "Ownership & coverage".
- Tests: `tests/pipeline/extract/test_python_rationale.py`, `tests/pipeline/extract/test_python_dispatch.py`, `tests/pipeline/extract/test_extract_hardening.py`, `tests/pipeline/io/test_git.py`, `tests/pipeline/io/test_cache.py`, `tests/pipeline/io/test_paths.py`, `tests/analysis/test_cluster_determinism.py`, `tests/export/test_graph_determinism.py`, `tests/pipeline/build/test_references.py`, `tests/pipeline/build/test_p2_read_counter.py`, `tests/context/build/test_communities.py`.

## Architecture

- `extract()` runs two passes.
- Pass one, per file, maps each extension to an extractor (`_extract_generic` or custom walk) and caches by content hash.
- Pass two synthesises cross-file edges: dispatch-idiom post-pass, Python and Java import resolution, global-label call resolution.
- `cluster()` consumes that graph. It runs seeded NetworkX-Louvain on the committed path (`_RANDOM_SEED=42`, GATE strategy (b)), re-indexed by `(-size, smallest-member)`. Leiden stays off-path.
- `to_json()` serialises a sorted, `sort_keys=True` node-link document.
- `context/build/communities.py` derives `features/seed-rank.json` (pure-Python personalized PageRank) and `features/graph-communities.json` (community cards). It reads the same in-memory graph in `build_graph`.
- The chain is LLM-free and deterministic, so artifacts are byte-identical run to run.

## Data model

- **Node** (`dict`): `{id, label, file_type, source_file, source_location}`. `id` comes from `_make_id` (`common.py:12-16`). `source_location` is `"L<line>"`.
- Class, function, and method labels carry shape markers: `"Foo"`, `"bar()"`, `".method()"`. Resolvers skip labels ending in `")"` or `".py"`.
- **Edge** (`dict`): `{source, target, relation, confidence, source_file, source_location, weight}`, sometimes with `confidence_score`.
- `confidence` is a `ConfidenceLevel` enum (`EXTRACTED` / `INFERRED` / `AMBIGUOUS`).
- Relations include `contains`, `method`, `calls`, `inherits`/`extends`/`implements`, `imports`/`imports_from`, `uses`, `uses_static_prop`, `references_constant`, `bound_to`, `listened_by`, `references`.
- **`extract()` return**: `{"nodes": [...], "edges": [...], "file_bytes": {str(path): bytes}, "input_tokens": 0, "output_tokens": 0}`. `file_bytes` feeds the later textual-reference pass (see spec, P2).
- The per-file return also carries `raw_calls` (`generic.py:650`): unresolved in-file calls for the cross-file loop.
- **`LanguageConfig`** (`config.py:12-47`): node-type frozensets (`class_types`, `function_types`, `import_types`, `call_types`, …) and field names (`name_field`, `body_field`, `call_function_field`).
- Two callables, `import_handler` and `resolve_function_name_fn`, parametrise `_extract_generic`.
- **Communities**: `dict[int, list[str]]`. Key 0 is the largest. Each value is a sorted node-id list (`cluster.py:110`).
- **Cache entry**: `.context/cache/<sha256-of-content>.json`. It holds one file's result (`cache.py:80-108`).
- **`symbol-graph.json`**: networkx node-link data. It adds `community` and `norm_label` per node, and `confidence_score` per link. A top-level `hyperedges` list comes from `G.graph` (`graph.py:29-41`).
- **`seed-rank.json`**: `SeedRank.to_dict()`, an ordered list of `RankEntry{id, score}`. It keeps the top 500. Scores round to 8 decimals. Rationale nodes are dropped. Sort is `(-score, id)`. The scan seed consumes it (`context/domains/features/scan/rank.py`).
- **`graph-communities.json`**: `rollup_communities(...).to_dict()` (`context/domains/features/communities.py`). It has one card per Louvain community.
- Features claim members from the on-disk taxonomy, in sorted-`feature_id` order. Members are unowned when no taxonomy exists yet.
- Each symbol gets rationale quotes from `rationale_for` edges. The earliest source line wins, so the docstring beats later `# NOTE:` comments.

## Key decisions

- **Determinism is enforced at three seams, not assumed.** Clustering seeds both the Leiden and Louvain paths with `_RANDOM_SEED=42` (`cluster.py:11,42,52`).
- It breaks size ties on the lexicographically smallest member (`cluster.py:109`). So community IDs depend on content, not partition order.
- The exporter sorts nodes by `id` and links by `(source, target, relation)`, then dumps with `sort_keys=True` (`graph.py:40-43`). The committed JSON is byte-identical.
- `collect_files` returns sorted paths (`__init__.py:276,293`). Node IDs are normalised slugs (`common.py:12-16`). These were the most recent hardened seams.
- **One parametric driver over twelve hand-written extractors.** `_extract_generic` (`generic.py:23-650`) absorbs the common tree-walk and call-graph logic.
- Per-language differences go into `LanguageConfig` data. A few inline `if config.ts_module == ...` branches remain: Python inheritance, Swift conformance, C#/Java base lists, PHP listeners and bindings.
- The docstring concedes it is ~600 lines. It calls itself "indivisible — splitting it would require threading too much state across modules" (`generic.py:6-13`). An accepted exception to the file-size convention.
- **Cache key is content, not path.** `file_hash` ignores its `root` argument. The argument stays only for API compatibility. It hashes file bytes.
- So re-runs from a different cwd, subagent absolute-vs-relative paths, and `mv` or repo moves all hit one entry (`cache.py:20-40`).
- `.md` frontmatter is stripped first. So metadata-only edits do not bust the cache.
- **Errors are isolated, never fatal.** A per-file parse failure returns an `error` result: not cached, no nodes or edges. It does not abort `extract`.
- Cross-file resolution is wrapped in try/except. It degrades to a logged warning (`__init__.py:202-214`).
- Git helpers treat malformed input as "not a repo" and never raise (`git.py:11-14`). They gate optional installs.
- **graspologic output is muted.** `_partition` redirects stdout and stderr around the Leiden call (`cluster.py:38-44`).
- graspologic emits ANSI sequences that corrupt the PowerShell 5.1 scroll buffer (issue #19).
- **Dispatch-idiom resolution is precision-first and fails soft.** `_resolve_python_dispatch` emits an edge only when the dict value matches a known extracted symbol.
- For `module.attr` values, the object name must be import-bound in the same file. Resolution keys on that binding's *real* imported module stem, not the bound name. So an aliased import resolves too.
- A `(stem, name)` key claimed by more than one source file is ambiguous. It is skipped (`python_dispatch.py:77-103`).
- Nested `a.b.c` and call-result values are never guessed (`python_dispatch.py:298-331`).
- `extract()` runs the pass **before** `id_remap`. So file-node-sourced edges remap with the rest.
- It dedupes against extracted edges by `(source, target, relation)`. It degrades any failure, including a missing `tree_sitter_python`, to a warning or empty result (`extract/__init__.py:211-235`).
- **Committed rank bytes never depend on an optional numeric backend.** `compute_symbol_rank` is pure-Python power iteration. It is not `networkx.pagerank`, because NetworkX 3.x delegates that to scipy.
- This is the same GATE reasoning that pinned committed communities to always-Louvain (`communities.py:66-86`).
- Iteration follows graph insertion order, so float sums reproduce.
- Scores round to 8 decimals to kill float-noise churn. Non-convergence returns the last deterministic iterate. It does not raise.
- A failure in `write_graph_artifacts` warns and never blocks `symbol-graph.json` itself (`context/build/graph.py:68-78`).
- **Textual references are a single regex pass.** `_derive_textual_references` (`references.py:16-103`) builds one combined lookahead alternation.
- It covers every rel-path and eligible-basename needle (`_build_matcher`, `references.py:106-125`). It scans each file once.
- This replaces the old O(F²) per-pair `str.find`. It is behaviour-preserving: a constant-factor win, not an asymptotic one (`references.py:62-66`).
- Basename fallback needs length ≥5 and uniqueness, limiting false positives.

## Open questions

- **[RESOLVED — GATE strategy (b), `b157a1c`; see concerns]** Leiden-vs-Louvain byte-stability. The committed `community` path is NetworkX-Louvain only (`_partition` → `_louvain_partition`, `cluster.py:77-84`).
- Leiden (`_leiden_partition`) stays off the committed path. Docstrings match.
- **[RESOLVED — P2, `b157a1c`; see concerns]** The cross-file resolvers no longer issue an independent disk read.
- All in-build reads go through the memoized `read_source_bytes` seam in one `build_read_cache()`. A fully cached re-run reuses bytes the hash read captured.
