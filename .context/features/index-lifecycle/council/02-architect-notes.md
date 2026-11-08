# Architect notes — Index lifecycle and coverage

## What I changed

- Line count: 83 → 82 (`wc -l`, `council/01-dev-draft.md` vs `plan.md`).
- "Where it lives": I dropped the per-file tour and replaced it with boundary, upstream, downstream and cycle bullets. Bare filenames now mean `dummyindex/context/build/`.
- Architecture: sentence 1 is now the router (it was missing). The tree→maps ordering moved here from Key decisions.
- Data model: added the change-detection split (`map/files.json` vs `cache/manifest.json`) and the `scan_scope` persist/replay loop.
- Key decisions: each now reads "X because Y". I dropped the `_Retirer` link-safety detail because spec "Layout migration" already states it; `upgrade.py:347-493` still holds it.
- Corrected a draft inaccuracy: "only `stamp_reconciled` writes the anchor" is false, because `build_all` sets `indexed_commit=head_commit(...)` (`runner.py:172`). The plan now says reconcile is read-only except the stamp, and `build_all` resets the anchor.
- Corrected a draft inaccuracy: "`build_all` has no hold-back" understated the case. `build_all` writes `meta.json` first, via `new_meta` in `_write_all` (`runner.py:167-174,386`), before the graph runs. So "stamp last" is refresh-only.
- Corrected a draft inaccuracy in open question 2: "the stamp stays put" holds only on the refresh. `build_all` writes `"unknown"` into `meta.json` through `new_meta` (`runner.py:167`, `meta.py:57-65`). The refresh holds the stamp because `parse_version("unknown")` is `None` (`versioning.py:35-49`).
- Added open question 4 (doc-only edit loop). It is inferred, not verified: `incremental.py:146-149` sources doc hashes only from the manifest, and `enriched_refresh.py` has no `write_manifest` call. The steady-state test covers code only (`tests/context/build/test_incremental.py:718-738`).
- Removed `project_init.py:95-100` as the report site. `:99` and `:148` are both covered by the `project_init.py:83-149` upstream cite.
- Audit trail: `RETIRED_CONTEXT_PATHS`, `_CATALOG_ARTIFACT`, `_GRAPH_ARTIFACT` and `SCHEMA_VERSION` have no entry in `map/symbols.json`, which indexes defs only. I verified them in source instead: `upgrade.py:334`, `enriched_refresh.py:92-93`, `meta.py:20`.
- Audit trail: every other named symbol matched `map/symbols.json`. I spot-checked every kept `path:range` against HEAD `0634bfd` source.
- Audit trail: no catalogued prose doc is quoted, so there is no doc/code conflict to flag. `.context/conventions/coding-practices.md:89-90` (layering) traces to the low-confidence `docs/reference/01-conventions.md`, so I cite layering from code (`upgrade.py:20-22`, `project_init.py:57-62`).
- Not edited: `spec.md`, source.

## Patterns named

- Router (bias-to-preserve): `enriched_index_status` picks refresh vs `build_all`. Sites: `incremental.py:168-198`, `installer/install/project_init.py:83-142`. A refusal guard sits on the same predicate at `cli/rebuild.py:112-122`.
- Single-pass pipeline: one detect → extract → `build_structure` pass feeds every writer (`runner.py:1-5,143-160`; `enriched_refresh.py:159-170`).
- Registry with per-entry predicate: `RetiredPath(rel_path, retired_in, is_generated)` in `RETIRED_CONTEXT_PATHS` (`upgrade.py:320-341`). This is the house "DI by Callable seam, not Protocol" style (`.context/conventions/coding-practices.md:64-71,84-85`), so I did not call it port/adapter.
- Contained steps / error accumulation: `_attempt` collects `"<step>: <error>"` and never raises (`upgrade.py:533-593`).
- Commit marker: the refresh advances the version stamp only when `failed` is empty (`enriched_refresh.py:227-230`).
- Shared pure presenter: `format_migration_report` (`upgrade.py:618-665`). Callers: `cli/rebuild.py:139-146`, `installer/install/project_init.py:99,148`.
- Compatibility re-export: `runner.py:38-52`, plus the package facade `__init__.py:8-47`.

## Dependencies surfaced

- Upstream writers: `cli/rebuild.py:78-136`, `installer/install/project_init.py:83-149`, `cli/enrich.py:40` (migration only, `package_version=None`), `cli/reconcile.py:75,112,135`.
- Upstream report-only readers of `compute_reconcile_report`: `context/drift.py:174`, `context/reconcile_gate.py:277`, `cli/status.py:219`, `cli/maintain.py:102,173`, `context/domains/evolve.py:392`. `evolve` was left out of the plan to save a line.
- Downstream: `pipeline.io.detect`, `pipeline.extract`, `pipeline.build.build_structure`, `pipeline/io/cache.py:225-279` (`scope_cache_to_version`), `export/storage.py:340,497` via `build_graph` (`graph.py:47`), `context/domains` (`source_docs`, `atomic_io`, `features.scaffold_features`, `memory`), `context/output`, and `versioning`.
- The `build_all`-only downstreams are `scaffold_features`, the memory seed and `reconcile_claude_md` (`runner.py:247-289,325-332`). The refresh never touches them, which is the curation boundary.
- Cycles: none. `upgrade` imports neither `runner` nor `installer` (`upgrade.py:20-22`), and `test_upgrade_imports_neither_runner_nor_installer` guards this. `format_migration_report` takes `RefreshResult.failed` as a plain tuple, so `upgrade` does not import `enriched_refresh`.
- Hidden data coupling: `scan_scope` is persisted by `build_all` (`runner.py:163-166`) and replayed by `scan_root` (`scope.py:45-60`) for the refresh, `rebuild_changed`, reconcile and the stamp.
- Ordering coupling: `refresh_tree` reads the previous `map/files.json` (`navigation_refresh.py:81-84`), so it must run before `write_files_map`.
- Ordering coupling: the migration must run after `cache/` exists, because `scope_cache_to_version` returns 0 without creating the directory (`pipeline/io/cache.py:239,248-249`).

## Decisions promoted

- Curated index → refresh, never re-cluster, because `build_all` re-runs community detection and overwrites council taxonomy (`incremental.py:89-99`, `enriched_refresh.py:4-9`).
- Bare `rebuild` refuses rather than auto-routes, because scripts and hooks may call it expecting a cheap refresh (`cli/rebuild.py:107-111`).
- `cache/` is created before the migration, because `scope_cache_to_version` never creates a missing dir. The entries would otherwise go unstamped and be discarded next run (`runner.py:131-140`, `pipeline/io/cache.py:239`).
- `None` version is the "leave cache scope and stamp alone" sentinel (`upgrade.py:580`, `enriched_refresh.py:386`). `enrich-plan` passes it because it does not extract (`cli/enrich.py:33-40`). It is also `rebuild_changed`'s default, but the full-build branch substitutes `"0.0.0"` (`incremental.py:78-82,196`).
- An unparseable version never replaces a parseable one, because `VersionOrder.UNKNOWN` is never treated as `OLDER` (`versioning.py:17-18`).
- `graph/` is backed up, not promoted, because the build paths rewrite the symbol graph right after. Promotion stays in `cli/migrate.py` refresh-indexes (`upgrade.py:337-340`).
- The v0.36 `Capability` vocabulary is frozen and not imported, so a later enum change cannot alter what counts as generated (`upgrade.py:181-183`).
- The stamp does not block on drift, because re-enriching does not clear drift and only the stamp does (`reconcile.py:319-321`).
- `cache/manifest.json` advances with the stamp, never the refresh, because it means "bytes the docs describe". Stamping it on refresh would erase the edit that triggered the rebuild (`reconcile.py:364-367`).
- The refresh never moves `indexed_commit`, because it would silently forget every change since the last reconcile (`enriched_refresh.py:128-134`).
