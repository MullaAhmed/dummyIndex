# Index lifecycle and coverage — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/context/build/` holds the lifecycle code:
  - `runner.py` (full build) and `incremental.py` (`--changed` routing,
    bias-to-preserve).
  - `enriched_refresh.py`, the non-destructive refresh.
  - `upgrade.py` (new), with the migration, the retired-path registry and the
    report.
  - `scope.py`, `meta.py`, `navigation_refresh.py`, `coverage.py`,
    `reconcile.py` and `git_delta.py`.
- `dummyindex/export/storage.py` stores the graph shards;
  `dummyindex/pipeline/io/cache.py:225-279` scopes the cache to a version.
- The report is printed by `dummyindex/cli/rebuild.py:139-146` and
  `dummyindex/installer/install/project_init.py:95-100`.
- Tests are in `tests/context/build/`. `tests/fixtures/retired_equipment_evals/`
  holds the nine v0.36 suites.

## Architecture in three sentences

`build_all` and the refresh each run `scan_root` and then
`migrate_context_layout`, followed by one detect → extract → `build_structure`
pass that feeds every writer (`dummyindex/context/build/runner.py:118-160`,
`dummyindex/context/build/enriched_refresh.py:150-175`). The refresh writes the
tree, maps, coverage, naming, meta counts, catalog and graph, then the version
stamp, then the summaries (`dummyindex/context/build/enriched_refresh.py:174-251`).
Reconcile reads the anchor and feature ownership, and only `stamp_reconciled`
writes the anchor.

## Data model

- `meta.json` (schema 2): `dummyindex_version`, `created_at`/`updated_at`,
  `root="."`, counts, `config.scan_scope` and `indexed_commit`
  (`dummyindex/context/build/meta.py:32-50`).
- `cache/extraction-version` records the version of the cache entries.
- `cache/manifest.json` is written by `build_all` and the stamp, never by the
  refresh. `cache/doc-basis.json` is written only by the stamp.
- `_doc_backups/retired/<ver>/` holds the retirement backups, which are
  gitignored.

## Key decisions

- **Migrate before extracting.** The cache scope deletes entries carrying another
  stamp, so running it later would wipe this run's own entries. `cache/` is
  created first so a fresh index gets a stamp
  (`dummyindex/context/build/runner.py:131-141`).
- **Write the stamp last.** The required-artefact set is two named constants;
  seed-rank and communities are best-effort
  (`dummyindex/context/build/enriched_refresh.py:90-93,211-230`). An
  unparseable version never overwrites a parseable one, and
  `dataclasses.replace` keeps `updated_at`
  (`dummyindex/context/build/enriched_refresh.py:362-409`). `build_all` has no
  hold-back: if the graph fails it only warns.
- **Refresh the tree before the maps.** `refresh_tree` diffs against the
  previous `map/files.json` (`dummyindex/context/build/navigation_refresh.py:75-158`).
- **If generation is unproven, back the file up.**
  - Starter suites are re-rendered from a frozen v0.36 Capability vocabulary
    (not imported), across both py3.10 and py3.11 enum renderings.
  - `graph/` is never treated as generated.
  - `_Retirer` uses `lstat` and refuses anything that resolves outside
    `.context/`, or any linked backup ancestor. It never overwrites an existing
    backup; it picks the next free `<stem>.<n>` name, up to 100
    (`dummyindex/context/build/upgrade.py:171-493`).
- **Keep the layering.** `upgrade` imports neither `runner` nor `installer`, and
  `runner` re-exports the helpers that moved
  (`dummyindex/context/build/runner.py:38-52`).
- **Model B.** The refresh never moves `indexed_commit`. A stamp refuses when
  files are unassigned, a feature is awaiting enrichment, or the anchor is
  orphaned and no `--to` is given
  (`dummyindex/context/build/reconcile.py:342-348`).

## Open questions

- When nothing changed, `rebuild --changed` exits before the migration and the
  stamp (`dummyindex/context/build/incremental.py:160-161`), so an old layout
  survives until `install` runs or the source changes. Is that intended?
- If the version lookup fails, `rebuild` falls back to `"unknown"`
  (`dummyindex/cli/rebuild.py:62-67`). That wipes the cache while the stamp
  stays put.
- `rebuild --changed` has no `--force-downgrade`.
