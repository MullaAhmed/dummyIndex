# extraction-pipeline — plan

`confidence: INFERRED`

## Where it lives

Boundary: source paths in → `extract()` dict, seeded communities, a bounded `symbol-graph.json` and two derived artifacts out. No CLI verb, no taxonomy; `index-lifecycle` wires it.

- `pipeline/extract/`:
  - `__init__.py`: `extract`, `collect_files` and the extension-keyed dispatch table `_DISPATCH` (`:71-106`). `.blade.php` is matched by name first (`:154-157`).
  - Parametric driver `_extract_generic` (`generic.py`), configured by `LanguageConfig` records (`config.py:14-48`; instances in `language_configs.py`) with injected strategy hooks `import_handler` and `resolve_function_name_fn` (`config.py:45,48`).
  - 12 thin wrappers (`languages/wrappers.py:30-91`); `extract_python` adds the `python_rationale.py` post-pass (`:30-35`).
  - Off the driver: custom tree-sitter walks (Go, Rust, Julia, Elixir, Verilog, Zig, PowerShell) and regex with no tree-sitter (Blade, Dart). Cross-file post-passes: `python_dispatch.py`, `resolve.py`.
- `pipeline/io/`: `cache.py` (read seam, content-hash cache, version scoping), `paths.py`, `git.py`.
- `analysis/cluster.py`; `export/graph.py` (`to_json` annotates); `export/storage.py` (the single writer and reader); `context/build/communities.py` (derived artifacts). Tests: see `feature.json`.

**Upstream**
- `pipeline/io/detect.py` (`equip`, `source-docs`) supplies `code_files` (`context/build/runner.py:129-130`). `collect_files` imports its private `_is_ignored`/`_load_dummyindexignore` (`dummyindex/pipeline/extract/__init__.py:363`).
- `tree_sitter` >= 0.23 (`extract/__init__.py:53-68`), with grammars imported per config (`generic.py:25`); `networkx`; `ConfidenceLevel`.
- `context/build/communities.py:19-28` imports `SeedRank`, `RankEntry`, `rollup_communities` and both filenames from `context/domains/features/`, which owns the artifact contracts.

**Downstream**
- `index-lifecycle` (`context/build/`): `runner.py:126-131` and `enriched_refresh.py:107-113` run migrate → `cache_dir_override` → `detect` → `extract`.
  - Also there: `graph.py:34-82` (`build_graph`), `upgrade.py:539-546`, `portable_graph.py` (`_make_id`), `incremental.py:26` (`file_hash`), and `pipeline/build/references.py:156-168` (`file_bytes`).
- `read_graph_payload` callers: `runner.py:213`, `features/indexes.py:137`, `dummyindex/context/domains/features/scan/refs.py:65`, `graph_query/load.py:64`, `reality_check/verify.py:376`, `viewer/extras.py:191`.
- Leak: `context/domains/evolve_native_snapshot.py:53-55,80` (`evolution`) uses storage's private `_decode`/`_read_manifest`/`_FORMAT`/`_HASH_RE` and hashes its source (`:37`). Renaming those breaks evolve, and any edit to `storage.py` changes evolve's controller hash.

**Cycles**
- Imports: none. `pipeline/`, `export/` and `analysis/` never import `context/`. Duplication keeps it that way: `cache.py:144-149` mirrors `atomic_io._replace_bytes`, `context/build/communities.py:46-48` mirrors `_CALL_RELATIONS`, and `viewer/extras.py:481` twins `_indexed_root` "(duplicated: import cycle)".
- Data: community ownership reads the taxonomy that is scaffolded from this graph (`communities.py:266-295`). A fresh ingest gets unowned cards until the next refresh.

## Architecture in three sentences

`extract()` runs a cacheable per-file pass (dispatch, extractor, content-hash cache), then the cross-file passes (dispatch idioms, `id_remap`, Python/Java imports, global-label calls), and every read goes through one memoized seam, `read_source_bytes` (`cache.py:38-77`). `build_graph` (`context/build/graph.py:47-66`) normalizes paths, builds an undirected NetworkX graph, clusters it with seeded Louvain, publishes it via `to_json` → `write_graph_payload` (plain, or content-addressed shards then an atomic manifest), and derives seed-rank and graph-communities from the same graph. Writers degrade and the single reader fails closed; housekeeping runs only at migration or publish; no stage calls an LLM.

## Data model

- **Node**: `{id, label, file_type, source_file, source_location: "L<n>"}` (`generic.py:60-71`). The label index strips shape markers (`extract/__init__.py:285-286`).
- **Edge**: `{source, target, relation, confidence, source_file, source_location, weight}` (`generic.py:73-91`), plus `confidence_score` on inferred cross-file edges.
  - `relation` is an open set, and per-language code adds `defines`, `instantiates`, `case_of`, …. `references` comes from the downstream textual pass.
- **Per-file result**: `{nodes, edges, raw_calls}` (`generic.py:773`) or `{nodes: [], edges: [], error}`. `extract()` adds `file_bytes` and `file_status` (`extract/__init__.py:322-329`).
- **Cache dir** (`.context/cache/`, gitignored): `<sha256>.json` entries plus the `extraction-version` stamp. Scoping deletes only names matching `cache.py:29`, so co-tenants such as the drift `manifest.json` survive.
- **`symbol-graph.json`**: plain canonical node-link with one top-level `hyperedges` (`storage.py:140-184`), or a manifest.
  - Manifest: `{format, version, max_file_bytes, graph_sha256, counts, metadata, shards[{kind, path, sha256, bytes, count}]}` (`:377-385`) over `{"kind", "records"}` shards (`:188-189`). `graph_sha256` hashes what a plain write would emit (`:359`), and the reader re-checks it (`:484`).

## Key decisions

- **Determinism lives at named seams**, because committed bytes must match on any machine (`cluster.py:35-38`).
  - Seed 42 (`cluster.py:19,41`) and a content-determined re-index (`:124-125`).
  - Canonical sort and compact `sort_keys` JSON happen in the writer, not in `to_json`, so every payload gets one form (`storage.py:48-61,165-183`).
  - Sorted collection (`extract/__init__.py:379,412`), slug IDs (`extract/common.py:15-19`), and member claims in sorted-feature order (`context/build/communities.py:286-294`).
- **Optional backends never decide committed bytes** (`cluster.py:35-37`, `communities.py:59-61`).
  - `_partition` is Louvain-only (`cluster.py:67-73`), and PageRank is a pure-Python iteration, not scipy `nx.pagerank` (`communities.py:56-73`).
  - Leiden runs off-path, with its ANSI output muted (`cluster.py:57-63`, #19).
- **`_extract_generic` stays one 752-line function** (`generic.py:22-773`), because splitting it would thread too much state (`generic.py:6`). That breaks the >600-line rule (`conventions/coding-practices.md:92-93`), and its "extremis" sanction comes from low-confidence `docs/reference/01-conventions.md`, so it is a standing exception.
- **Content is the cache key; the version is scoped out of band.**
  - Path-free hashing survives a cwd change, a path-form change or `mv` (`cache.py:107-121`).
  - Stamp-and-wipe (`cache.py:195-237`) keeps names content-addressed and reports a count (`upgrade.py:546`). After a failed delete the stamp is withheld, so the step retries (`cache.py:234-236`).
- **Scoping runs before extraction**, because running it after would wipe the entries the build just wrote. The dir is created first so a fresh repo is stamped (`context/build/runner.py:121-126`).
- **Two cache-dir channels.**
  - A trusted override pins build paths to `.context/cache/` (`context/build/common.py:164-178`), while the ambient `DUMMYINDEX_CACHE_DIR` counts only inside the repo (`cache.py:127-131`).
  - The internal target must bypass the confinement applied to user input. That confinement is the containment; the payload guard is only anti-corruption (`cache.py:243-244`).
- **Cached payloads are never mutated.** `id_remap` builds new dicts because the merged lists alias `load_cached` payloads (`extract/__init__.py:228-230`).
- **Precision over recall.**
  - Colliding labels are skipped, never bound last-wins (`extract/__init__.py:279-304`), and ambiguous dispatch keys are dropped (`python_dispatch.py:62-86`).
  - Dispatch runs before `id_remap`, so its file-sourced edges get remapped (`extract/__init__.py:192-216`).
- **Writers degrade; the reader fails closed.**
  - Errored results are never cached, and pass failures warn (`extract/__init__.py:200-207,257-277`). Git helpers never raise (`git.py:6-7`).
  - A derived-artifact failure still lets the graph land (`context/build/graph.py:64-74`), and the reader never returns a partial graph (`storage.py:489-495`).
- **Storage keeps only the current generation.**
  - Content-named shards self-verify: wrong bytes are rewritten, and matching ones are touched and reused (`storage.py:391-398`).
  - The manifest is published last and atomically, so a failed publish keeps the old generation (`:399-402`).
  - Pruning protects `keep | shard_names(live manifest)` plus a 600 s grace, never deletes links, non-regular files or foreign names, and only warns (`:276-329`).
  - The cost: a reader on a superseded manifest fails closed (`:5-6`). Never-delete had leaked every superseded shard (commit `0634bfd`). With a shared parts dir, there is one manifest per directory (`:7`).
- **Storage paths are hostile input.** `_plain_path` (`storage.py:68-102`) and `_read_bytes` (`:105-127`) refuse links, escapes, non-regular files and oversize.
- **PageRank down-weights tests** (0.1, against 3.0 for entry points), because test nodes dominated the degree signal in the bakeoff (`context/build/communities.py:5-6,36-38`).

## Open questions

- `save_cached` uses a fixed `<hash>.tmp` (`cache.py:297`), unlike the stamp writer's unique tmp (`cache.py:153-161`). Concurrent identical saves share it, and stray `*.tmp` files are never swept.
- Scoping targets only `context_dir / "cache"` (`upgrade.py:542`).
  - `runner.py:128` and `enriched_refresh.py:110` pin extraction there.
  - `maps.py:110` and `tree.py:69` extract with no override and no migration, so an in-repo `DUMMYINDEX_CACHE_DIR` on those paths is never scoped. Intended?
  - Enrich skips scoping on purpose, because it does not extract (`dummyindex/cli/enrich.py:37`).
- `collect_files._EXTENSIONS` (`extract/__init__.py:337-362`) has 24 suffixes against `_DISPATCH`'s 34, missing `.jsx .mjs .ex .exs .jl .vue .svelte .dart .v .sv`. Builds use `detect`, so only `__main__` (`:425`) and the lazy export (`dummyindex/__init__.py:19`) are affected. Intended?
- Stale comments (code wins):
  - `extract/__init__.py:5-8`: lists `_`-prefixed siblings and omits `file_status` (citation unverifiable). `:382-383`: old line refs (citation unverifiable).
  - `cache.py:34-37`: says references use the seam, but they read `file_bytes` (citation unverifiable). `dummyindex/context/build/graph.py:60`: says no final newline, but `storage.py:58` adds one.
  - `cluster.py:1,17-18` and `dummyindex/context/build/graph.py:39`: Leiden and cohesion (citation unverifiable). `generic.py:6`: "~600 lines" (citation unverifiable).
