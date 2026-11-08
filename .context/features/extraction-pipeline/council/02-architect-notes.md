# Architect notes — Extraction & graph backbone

## What I changed
- The plan went from 102 lines and 10,774 bytes to 89 lines and 10,599 bytes. I kept all five sections and the `confidence: INFERRED` line.
- I opened "Where it lives" with a one-line boundary statement (paths in; dict, communities and graph artifacts out; no CLI verb, no taxonomy). Upstream, Downstream and Cycles are now sub-lists inside that section, not new sections.
- I fixed a wrong ownership claim: the draft called `context/build/{graph,runner,enriched_refresh,upgrade}.py` "outside every feature", but `index-lifecycle/feature.json` owns them, along with `pipeline/build/{__init__,references}.py`.
- I fixed a wrong extractor claim: Blade and Dart are regex extractors with no tree-sitter (`languages/blade.py`, `languages/dart.py`), not "custom walks". `docs/guide/03-architecture.md:12` (confidence medium) agrees, and I spot-checked it against the code.
- I fixed a wrong consumer claim: "every consumer reads only through `read_graph_payload`" is false. `context/domains/evolve_native_snapshot.py:53-55,80` uses storage privates, so the plan now lists it as a leak.
- I took the textual-reference `_build_matcher` decision out of Key decisions. `references.py` belongs to `index-lifecycle`, so the plan keeps only the `file_bytes` dependency (`references.py:177-191`). The draft's `references.py:74-78` was off by one; the comment is at `:75-79`.
- I replaced the incomplete edge-relation list with "open set". The extractors also emit `defines`, `instantiates`, `case_of`, `rationale_for`, `includes`, `binds_method` and `uses_component`. `references` is not emitted by this feature.
- I cut the 7-line test inventory to a pointer to `feature.json`. The stale-comment list is now `path:line` tags, with two additions: `extract/__init__.py:16-25` lists `_`-prefixed siblings, and `cache.py:35-37` misdescribes the reference read.
- I added an open question: `collect_files._EXTENSIONS` has 24 suffixes against the 34 in `_DISPATCH` (`extract/__init__.py:370-395` vs `:90-125`). It only affects `__main__` and the lazy export, because builds use `detect`.
- I sharpened the scoping open question with what the code shows. `cli/enrich.py:39` says the skip is deliberate ("enrich-plan does not extract"). `maps.py:113` and `tree.py:69` run `extract` with no `cache_dir_override`, so they are the remaining gap.
- Symbol check:
  - Every function or class named in the plan is in `map/symbols.json` at the cited start line.
  - Six names are absent from the map but present in source: `_DISPATCH`, `_CALL_RELATIONS`, `_FORMAT` and `_HASH_RE` are module constants, and `import_handler` and `resolve_function_name_fn` are dataclass fields. The code wins.
- `_indexed_root` has three copies: `context/build/communities.py:327`, `context/domains/features/helpers.py:157` and `context/output/viewer/extras.py:498`. The plan cites only the one the code calls a twin.
- Doc conflicts, where the code wins and I edited nothing:
  - `docs/reference/01-conventions.md` (confidence low, 38 broken refs) is the only authority behind the "extremis" file-size exception cited at `generic.py:10-12`. I treated it as history, not as a sanction.
  - "Leiden" is stale in `conventions/folder-organization.md:19`, `HOW_TO_USE.md:18` and the `feature.json` summary; the committed path is Louvain-only (`cluster.py:77-84`).
  - The spec Intent says every file is parsed with tree-sitter, which is not true for Blade and Dart.

## Patterns named
- **Dispatch table (registry)**: `_DISPATCH`, extension to extractor (`pipeline/extract/__init__.py:90-125`). It has one name-based override (`:185-188`), and an unknown suffix becomes `unsupported` (`:189-195`).
- **Parametric driver + data-configured strategy**:
  - `LanguageConfig` records (`config.py:14-48`) drive `_extract_generic` (`generic.py:28-779`), with injected hooks `import_handler` and `resolve_function_name_fn` (`config.py:45,48`).
  - The wrappers are the adapters (`languages/wrappers.py:30-91`).
- **Scoped memoization seam**: `build_read_cache` plus `read_source_bytes`, a re-entrant module global for one build (`pipeline/io/cache.py:43-84`).
- **Content-addressed storage**: cache entries `<sha256>.json` (`cache.py:116-136,343`) and graph shards `symbol-graph.parts/<sha256>.json` (`export/storage.py:373-374`). Both are self-verifying by name.
- **Write-ahead parts + atomic manifest swap**: shards first, then the manifest (`storage.py:399-410`), through tmp, `fsync` and replace (`_atomic_write`, `storage.py:217-233`).
- **Pipes and filters**: extract, then normalize, `build_from_json`, `cluster`, `to_json`/`write_graph_payload` and `write_graph_artifacts`, wired in `context/build/graph.py:60-79` and `runner.py:141-146`.
- **Fail-soft writers, fail-closed reader**: warns at `extract/__init__.py:231-238,288-308` and `context/build/graph.py:77-87`; raises at `storage.py:417-494`.

## Dependencies surfaced
- Upstream:
  - `pipeline/io/detect.py` (owned by `equip` and `source-docs`): `detect` supplies `code_files` (`runner.py:144-145`), and `collect_files` imports the privates `_is_ignored` and `_load_dummyindexignore` (`extract/__init__.py:396`).
  - Libraries and enums: `tree_sitter` >= 0.23 (`:72-87`), grammar modules through `importlib` (`generic.py:31`), `networkx`, and `ConfidenceLevel`.
- Upstream (contract): `context/build/communities.py:29-38` imports `SeedRank`, `RankEntry`, `rollup_communities` and both artifact filenames from `context/domains/features/`. This feature writes those artifacts, but their schemas are owned elsewhere.
- Downstream (`index-lifecycle`):
  - `runner.py:141-146` and `enriched_refresh.py:156-162` (migrate, then override, detect and extract).
  - `graph.py:47-95`, `upgrade.py:580-587`, `portable_graph.py` (`_make_id`), `incremental.py:33` and `maps.py:16` (`file_hash`), and `references.py:177-191` (`file_bytes`).
- Downstream (readers): the six `read_graph_payload` callers listed in the plan. `seed-rank.json` goes to `scan/rank.py`, and `graph-communities.json` to `scan/refs.py:73`.
- Downstream leak (`evolution`): `evolve_native_snapshot.py:53-55,80` calls `storage._decode`/`_read_manifest` and reads `_FORMAT`/`_HASH_RE`. It also hashes the `storage.py` source as a controller input (`:37`), so these privates are a de-facto API.
- Also downstream: `context/domains/debt/harvest.py:25` imports `DEBT_PREFIXES` from `python_rationale`. I left this out of the plan because it is not boundary-critical.
- Cycles, imports:
  - None. `pipeline/`, `export/` and `analysis/` import nothing from `context/`; grep found only a string at `storage.py:475`.
  - The one-way layering is held by duplication at `cache.py:174-179`, `context/build/communities.py:56-58` and `viewer/extras.py:498-499`.
- Cycles, data: `_load_feature_ownership` (`communities.py:279-308`) reads the taxonomy that the scaffolder derives from this graph. The cycle is broken by tolerating an absent taxonomy, which leaves cards unowned on the first ingest.

## Decisions promoted
- Scoping runs before extraction because running it later would wipe the entries the build just wrote, and the cache dir is created first so a fresh repo is stamped (`context/build/runner.py:131-141`). The draft left this implicit.
- `id_remap` builds new dicts because the merged lists alias `load_cached` payloads that later passes re-read (`extract/__init__.py:259-261`). The draft did not mention it.
- There are two cache-dir channels because the internal override must bypass the env-var confinement applied to user input (`cache.py:144-161`, `context/build/common.py:174-190`). The payload guard is anti-corruption only (`cache.py:285-286`).
- Enrich skips cache scoping because enrich-plan does not extract (`cli/enrich.py:39-40`). This resolves half of the draft's open question.
- `_extract_generic` stays whole because splitting it would thread too much state (`generic.py:10-12`). I reframed this as a standing exception to `conventions/coding-practices.md:92-93`, because the sanction it cites is low-confidence.
- PageRank down-weights tests because test nodes dominated the degree signal in the bakeoff (`context/build/communities.py:8-11`).
- Determinism and backend independence are now stated as one rationale: committed bytes must match on any machine (`cluster.py:31-41`, `communities.py:69-73`). Before, they were two parallel lists.
- Writers degrade while the reader fails closed: the reader never returns a partial graph (`storage.py:497-503`). The draft had the "errors are never fatal" half but not this contrast.
