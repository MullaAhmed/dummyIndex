# extraction-pipeline — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/pipeline/extract/` — the tree-sitter front end. `__init__.py` is the public surface (`extract`, `collect_files`); `generic.py` holds `_extract_generic`, the parametric driver; `config.py` defines `LanguageConfig`; `common.py` has `_make_id`/`_read_text`/`_find_body`; `imports.py` + `helpers.py` hold per-language import handlers and extra-walk helpers; `language_configs.py` instantiates one `LanguageConfig` per language; `languages/` wraps each `extract_<lang>` (most are thin `_extract_generic` calls in `languages/wrappers.py`, a few — Go, Rust, Julia, Elixir, Verilog, Zig, Dart, PowerShell, Blade — are custom walks); `python_rationale.py` is the Python docstring/rationale post-pass; `resolve.py` holds the two cross-file resolvers.
- `dummyindex/pipeline/io/` — `cache.py` (content-hash per-file cache) and `git.py` (pure-filesystem repo detection).
- `dummyindex/analysis/cluster.py` — Leiden/Louvain community detection.
- `dummyindex/export/graph.py` + `export/common.py` — node-link JSON serialisation.
- Tests: `tests/pipeline/extract/test_python_rationale.py`, `tests/pipeline/io/test_git.py`, `tests/analysis/test_cluster_determinism.py`, `tests/export/test_graph_determinism.py`, `tests/pipeline/build/test_references.py`.

## Architecture in three sentences

`extract()` runs a two-pass pipeline: a per-file structural pass (extension → extractor → `_extract_generic` or a custom walk, each result cached by content hash) followed by cross-file edge synthesis (Python/Java import resolution plus global-label call resolution). The graph that pass produces is consumed downstream by `cluster()` — which seeds Leiden (or Louvain on fallback) with a fixed `_RANDOM_SEED=42` and re-indexes communities by `(-size, smallest-member)` for stable IDs — and by `to_json()`, which serialises a sorted, `sort_keys=True` node-link document. The whole chain is intentionally LLM-free and deterministic so the committed `symbol-graph.json` is byte-identical run-to-run.

## Data model

- **Node** (`dict`): `{id, label, file_type, source_file, source_location}`. `id` from `_make_id` (`common.py:12-16`); `source_location` is `"L<line>"`. Class/function/method labels carry shape markers — `"Foo"`, `"bar()"`, `".method()"` — which downstream code keys off (e.g. resolvers skip labels ending in `")"` or `".py"`).
- **Edge** (`dict`): `{source, target, relation, confidence, source_file, source_location, weight}`, sometimes with `confidence_score`. `confidence` is a `ConfidenceLevel` enum (`EXTRACTED` / `INFERRED` / `AMBIGUOUS`); relations include `contains`, `method`, `calls`, `inherits`/`extends`/`implements`, `imports`/`imports_from`, `uses`, `uses_static_prop`, `references_constant`, `bound_to`, `listened_by`, `references`.
- **`extract()` return**: `{"nodes": [...], "edges": [...], "input_tokens": 0, "output_tokens": 0}`. The per-file extractor return additionally carries `raw_calls` (`generic.py:650`) — unresolved in-file calls handed to the cross-file resolution loop.
- **`LanguageConfig`** (`config.py:12-47`): node-type frozensets (`class_types`, `function_types`, `import_types`, `call_types`, …), field names (`name_field`, `body_field`, `call_function_field`), and two callables (`import_handler`, `resolve_function_name_fn`) that parametrise `_extract_generic`.
- **Communities**: `dict[int, list[str]]`, key 0 = largest, each value a sorted node-id list (`cluster.py:110`).
- **Cache entry**: `.context/cache/<sha256-of-content>.json` holding one file's extraction result (`cache.py:80-108`).
- **`symbol-graph.json`**: networkx node-link data with added `community`, `norm_label` (per node) and `confidence_score` (per link), plus a top-level `hyperedges` list pulled from `G.graph` (`graph.py:29-41`).

## Key decisions

- **Determinism is enforced at three seams, not assumed.** Clustering seeds both the Leiden and Louvain paths with `_RANDOM_SEED=42` (`cluster.py:11,42,52`) and breaks size ties on the lexicographically smallest member (`cluster.py:109`), so community IDs are content-determined, not partition-order-determined. The exporter sorts nodes by `id` and links by `(source, target, relation)` then dumps with `sort_keys=True` (`graph.py:40-43`) so the committed JSON is byte-identical. `collect_files` returns sorted paths (`__init__.py:276,293`). Node IDs are normalised slugs (`common.py:12-16`). These three were the explicitly hardened seams in the most recent change.
- **One parametric driver over twelve hand-written extractors.** `_extract_generic` (`generic.py:23-650`) absorbs the common tree-walk and call-graph logic; per-language differences are pushed into `LanguageConfig` data and a few inline `if config.ts_module == ...` branches (Python inheritance, Swift conformance, C#/Java base lists, PHP listeners/bindings). The docstring concedes it is ~600 lines and "indivisible — splitting it would require threading too much state across modules" (`generic.py:6-13`), an accepted exception to the file-size convention.
- **Cache key is content, not path.** `file_hash` deliberately ignores its `root` argument (kept only for API compatibility) and hashes file bytes — so re-runs from a different cwd, subagent absolute-vs-relative paths, and `mv`/repo moves all hit the same entry (`cache.py:20-40`). `.md` frontmatter is stripped first so metadata-only edits don't bust the cache.
- **Errors are isolated, never fatal.** A per-file parse failure returns an `error` result (not cached, contributing no nodes/edges) rather than aborting `extract`. Cross-file resolution is wrapped in try/except and degrades to a logged warning (`__init__.py:202-214`). Git helpers treat malformed input as "not a repo" rather than raising (`git.py:11-14`), because they gate optional install steps.
- **graspologic output is muted.** `_partition` redirects stdout and stderr around the Leiden call (`cluster.py:38-44`) because graspologic emits ANSI escape sequences that corrupt PowerShell 5.1's scroll buffer (issue #19).
- **Textual references are a single regex pass.** `_derive_textual_references` (`references.py:16-103`) builds one combined lookahead alternation over every rel-path-and-eligible-basename needle (`_build_matcher`, `references.py:106-125`) and scans each file once, replacing the old O(F²) per-pair `str.find`. It's documented as behaviour-preserving — a constant-factor win, not an asymptotic one (`references.py:62-66`) — with basename fallback gated on length ≥5 and uniqueness to limit false positives.

## Open questions

- `cluster()` docstrings still say "Run Leiden community detection" / "best quality" (`cluster.py:64,30`) but the code falls back to Louvain when graspologic is absent; community IDs are seeded-stable on either path, yet the actual partitioning differs between the two backends. Is byte-stability of `symbol-graph.json` guaranteed only when graspologic presence is itself stable across machines, or is the Louvain fallback considered an acceptable divergence?
- `_resolve_cross_file_imports` reparses each Python file from disk a second time (`resolve.py:78-79`), independent of the cached per-file result. On a fully-cached re-run the structural pass is skipped but this resolver still re-reads and re-parses every `.py` — is that intentional, or a missed cache-reuse opportunity?
