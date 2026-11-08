# Index lifecycle and coverage — spec

`confidence: INFERRED`

- The saved scan scope is distinct from the output root. Refresh and reconciliation honor it; disjoint roots and linked managed destinations fail before writes.
- Maps and tree topology reflect current source. Authored annotations survive, with `source-stale` labels when source hashes change. Mechanical PROJECT/architecture sections refresh; other notes survive.
- Naming Markdown summarizes rules and exception counts. The linked `naming.json` retains complete exception evidence instead of repeating it in the reading path.
- `coverage.json` lists each detected source file, symbol count, owners, file-only reasons and excluded paths. Pending/unowned work remains visible.
- Graph paths and filename-derived IDs are repository-relative. Large symbol graphs use a validated manifest and content-addressed shards, each at most 1,000,000 bytes. The shared reader also accepts legacy JSON.
- Reconciliation retains the old anchor until ownership and review are complete. An absent anchor requires a full scoped inventory and an explicit reviewed replacement commit.

Build portable navigation from source, refresh it without discarding authored
context, bring an index written by an older dummyindex forward, and move the
reconcile anchor only after explicit review.

## User-visible behavior

- **Scope.** The saved scan scope is distinct from the output root; refresh and
  reconcile honor it. Disjoint roots and linked managed destinations fail before
  any write.
- **Rebuild routing.** `rebuild --changed` with no fingerprint change touches
  nothing. On a curated index it runs a deterministic refresh with no
  re-cluster; on a deterministic-only index it runs a full build.
- **Refresh.** Maps, tree topology, coverage, naming, catalog and graph reflect
  current source. Authored annotations survive and gain `source-stale` when
  source hashes change. Mechanical PROJECT/overview sections refresh and other
  notes survive. `indexed_commit` never moves.
- **Layout migration.** Every build, refresh and `enrich-plan` runs it:
  - merges the managed `.gitignore`/`.gitattributes`;
  - removes the legacy root `_enrich_plan.json`;
  - retires `equipment-evals/` (0.37.0) and `graph/` (0.6.0);
  - drops extraction-cache entries from another version (builds and refreshes
    only).

  Retirement deletes byte-exact v0.36 starter suites. Every other file is first
  backed up to `_doc_backups/retired/<ver>/`. Links are unlinked, never
  followed. A failing step becomes a warning.
- **Version stamp.** The refresh advances `dummyindex_version` and
  `schema_version` (now 2) last, and only after the catalog and symbol graph
  were written. It never downgrades without `install --force-downgrade`. On
  failure it prints `version stamp not advanced — fix the cause, then run
  dummyindex context rebuild --changed`. Removed, backed-up and warning lists
  are capped at 5 lines each. v1 meta still loads; a newer schema is refused
  with "upgrade dummyindex".
- **Coverage and naming.** `coverage.json` lists each file's symbols, owners,
  state (`indexed`, `file-only`, `pending` or `unsupported`) and reason, plus
  excluded and unassigned paths. `naming.md` gives exception counts;
  `naming.json` keeps the evidence.
- **Graph.** Paths and IDs are repository-relative. A large graph is stored as a
  validated manifest plus content-addressed shards of at most 1,000,000 bytes
  each. A publish prunes unreferenced shards older than 600 s. The reader
  accepts legacy JSON and never returns a partial graph.
- **Reconcile.** The anchor holds until ownership and review are complete. An
  orphaned anchor reports a full scoped inventory and needs `--to <sha>`, and
  the refresh marks every feature `.pending-enrichment`.

## Contracts

- `build_all(scope, *, out_root, cache_root, bootstrap, dummyindex_version="0.0.0", extra_doc_roots) -> BuildResult` (now carries `.migration`) — `dummyindex/context/build/runner.py:78-321`
- `rebuild_changed(root, *, …, dummyindex_version=None, full=False)`: `None` neither stamps nor rescopes the cache — `dummyindex/context/build/incremental.py:57-156`
- `refresh_deterministic_artifacts(root, *, …, dummyindex_version=None, allow_downgrade=False) -> RefreshResult(context_dir, written, migration, failed)` — `dummyindex/context/build/enriched_refresh.py:64-233`
- `migrate_context_layout(context_dir, *, package_version) -> LayoutMigration(removed, backed_up, errors)`, which never raises; `RETIRED_CONTEXT_PATHS`; `format_migration_report(migration, failed=(), *, prefix, cap=5)` — `dummyindex/context/build/upgrade.py:286-307`, `:483-552`, `:577-615`
- `scan_root(root, explicit=None)` — `dummyindex/context/build/scope.py:14-74`; `SCHEMA_VERSION = 2`, `read_meta` — `dummyindex/context/build/meta.py:17-91`
- `compute_reconcile_report` / `stamp_reconciled(…, force=False, to_commit=None)` — `dummyindex/context/build/reconcile.py:93-212`, `:251-320`

## Examples

Running `dummyindex install` on a curated 0.36 repo triggers the refresh with
`PACKAGE_VERSION` (`dummyindex/installer/install/project_init.py:65-81`). The
migration:

- deletes the untouched `equipment-evals/*.suite.json`;
- backs up an edited suite to `_doc_backups/retired/0.37.0/equipment-evals/`;
- drops the cache entries stamped 0.36.

Extraction, catalog and graph follow, then the stamp moves to the current
version with schema 2. Install prints one
`  .context/        ->  removed equipment-evals/<name>` line per file.
