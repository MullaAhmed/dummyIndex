# Index lifecycle and coverage — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/context/build/` (bare filenames below; surface `__init__.py:8-47`);
  other source paths are under `dummyindex/`. Tests: `tests/context/build/`,
  v0.36 suites in `tests/fixtures/retired_equipment_evals/`.
- Upstream: `cli/rebuild.py:78-135`, `installer/install/project_init.py:64-130`,
  `dummyindex/cli/enrich.py:37`, `cli/reconcile.py:69,106,129`. Report-only:
  `context/drift.py:132`, `dummyindex/context/reconcile_gate.py:251`, `dummyindex/cli/status.py:207`,
  `cli/maintain.py:73,144`.
- Downstream: `pipeline` (detect, extract, `build_structure`, cache scope),
  `export/storage.py` via `build_graph`, `context/domains` + `context/output`
  (features, memory, CLAUDE.md from `build_all` only), `versioning`.
- No cycle: `upgrade` imports neither `runner` nor `installer`
  (`upgrade.py:6-7`); `runner` re-exports its moved helpers (`runner.py:38-52`).

## Architecture in three sentences

A router on `enriched_index_status` sends a curated index to the refresh and
anything else to `build_all`, after `rebuild_changed` skips an unchanged tree
(`incremental.py:121-155`, `project_init.py:64-123`). Both writers run
`scan_root`, the contained-step migration, then one detect → extract →
`build_structure` pass (`runner.py:109-145`, `enriched_refresh.py:101-117`);
the refresh writes the tree before the maps, since `refresh_tree` diffs the
previous `map/files.json` (`navigation_refresh.py:79-90`), and the version
stamp after catalog and graph, as commit marker (`enriched_refresh.py:160-179`).
Reconcile is read-only except `stamp_reconciled`, which moves `indexed_commit`
and rewrites `cache/manifest.json` and `cache/doc-basis.json`
(`reconcile.py:286-307`); `build_all` resets the anchor to HEAD (`runner.py:157`).

## Data model

- `meta.json` (schema 2, `meta.py:17-47`): version, timestamps, `root="."`,
  counts, `config.scan_scope`, `indexed_commit`. `build_all` writes the scope
  (`runner.py:148-151`); `scan_root` replays it elsewhere (`scope.py:38-74`).
- `map/files.json` (tracked, code) wins change detection; `cache/manifest.json`
  backstops it and alone carries doc hashes (`incremental.py:98-110`); only
  `build_all` and the stamp write it (`runner.py:286-298`, `reconcile.py:300-307`).
- `cache/extraction-version` stamps the cache; backups: `_doc_backups/retired/<ver>/`.

## Key decisions

- **Preserve curation.** A curated index is refreshed, never re-clustered, as
  `build_all` would overwrite council taxonomy (`incremental.py:68-70`); bare
  `rebuild` refuses, since scripts expect a cheap one (`cli/rebuild.py:107-121`).
- **Migrate before extracting.** The cache scope deletes other-stamp entries, so
  later would wipe this run's own; `cache/` comes first as `scope_cache_to_version`
  never creates it (`runner.py:121-126`, `pipeline/io/cache.py:199`). `None` skips
  cache scope and stamp (`upgrade.py:539`, `enriched_refresh.py:316`); `enrich-plan`
  passes it as it does not extract (`cli/enrich.py:33-37`).
- **Stamp as commit marker, refresh only.** Version and schema move only when
  `_CATALOG_ARTIFACT` and `_GRAPH_ARTIFACT` landed (`enriched_refresh.py:58-61`,
  `:160-179`); an unparseable version never replaces a parseable one because
  `UNKNOWN` is never `OLDER` (`:305-339`, `versioning.py:16-17`). `build_all`
  writes `new_meta` first and only warns on a graph failure (`runner.py:152-221`).
- **Retired-path registry.** `RETIRED_CONTEXT_PATHS` pairs each path with an
  `is_generated` Callable seam (`upgrade.py:286-307`); unproven or raising means
  backed up, and a failed backup keeps the file (`:399-411`). `equipment-evals`
  re-renders v0.36 suites from a frozen `Capability` vocabulary, not imported,
  so enum changes can't move the verdict (`:146-275`); `graph/` is backed up, not
  promoted, as the build rewrites the symbol graph next (`:278-280,303-306`).
- **Contained steps.** `_attempt` turns a step's failure into a warning so it
  never blocks the build (`upgrade.py:492-552`); install and `rebuild` share the
  pure `format_migration_report` (`:577-615`).
- **Model B.** The refresh never moves `indexed_commit`, which would forget every
  change since the last reconcile (`enriched_refresh.py:280-282`). The stamp
  ignores drift because only it clears drift; the refresh skips the manifest
  lest it erase the triggering edit (`reconcile.py:260-280,296-298`).

## Open questions

- An unchanged `rebuild --changed` returns before migration and stamp
  (`incremental.py:121-122`): an old layout waits for `install` or an edit. Intended?
- A failed version lookup yields `"unknown"` (`cli/rebuild.py:62-67`): it wipes
  the cache; the refresh holds the stamp, `build_all` writes it (`runner.py:152`).
- `rebuild --changed` has no `--force-downgrade` (`incremental.py:132-137`).
- The refresh never writes the manifest, the only doc-hash source: does a
  doc-only edit re-trigger it until `reconcile-stamp`? The steady-state test
  covers code only (`tests/context/build/test_incremental.py:710-730`).
