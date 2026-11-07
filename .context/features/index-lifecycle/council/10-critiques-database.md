# Index lifecycle — data-integrity critique (deep, reconcile @ 0634bfd)

## Data integrity

Line numbers below are from the current tree. The plan.md cites were written before the comment pass, so they have drifted: `RETIRED_CONTEXT_PATHS` is now `upgrade.py:300-307`, the stamp gate `enriched_refresh.py:176-179`, and the anchor reset `runner.py:157`.

1. `dummyindex/context/build/incremental.py:98-122`: the unchanged-tree skip compares stale and mismatched fingerprints. `cache/manifest.json` stores raw-byte sha256 (`manifest.py:34-38`) and is merged under `map/files.json`, but the refresh rewrites only files.json. As a result:
   - code deleted since the last build/stamp comes back as `removed` on every run (measured now: 28 `benchmarks/*` paths);
   - on an LF checkout, each of this repo's 25 frontmatter `.md` docs reads `modified` forever. `file_hash` strips frontmatter (`pipeline/io/cache.py:116-136`), and `reconcile-stamp` rewrites raw hashes (`reconcile.py:300-307`).

   So `rebuild --changed` on a curated index never skips, and every run rewrites meta `updated_at` and `naming.md`. This answers plan Open Q4: yes, and permanently for frontmatter docs. **Fix:** build manifest entries with `file_hash`, and take only doc paths (never code) from the manifest.

2. `dummyindex/context/build/runner.py:152-159,362`: `build_all` writes `meta.json` (version, schema 2, `indexed_commit=HEAD`) first, with no downgrade or parse check. Maps, graph (whose failure only warns, `:206-221`) and manifest come after it. On every deterministic-only path (`install` at `project_init.py:133-139`, `rebuild`, `rebuild --changed`):
   - a crash or graph failure leaves the new stamp over old artifacts;
   - an older CLI silently downgrades the stamp;
   - a failed version lookup stamps `"unknown"` (`cli/rebuild.py:62-67`) and makes `scope_cache_to_version` wipe the cache (536 entries here).

   `rebuild_changed(dummyindex_version=None)` does the same via `"0.0.0"` (`incremental.py:153`). That contradicts the spec's "`None` neither stamps nor rescopes", which holds only on the refresh branch. **Fix:** write meta last, reuse `_advance_version_stamp`'s rule, and pass `None` through instead of a sentinel.

3. `dummyindex/context/build/meta.py:4-6,17`: schema 2's fields are identical to v1, and 0.37.0 already wrote sharded graphs at schema 1 (`4f3cf0d:dummyindex/export/storage.py` defines `symbol-graph.parts`). So the docstring's "marks the sharded format" is false, and the bump only locks 0.37.0 out of the committed `meta.json`. A 0.37.0 CLI on a schema-2 repo:
   - refresh swallows the `ValueError` and rewrites every other artifact;
   - `build_all` writes schema 1 back, so the value flip-flops in git;
   - `reconcile-stamp` prints "no readable meta.json to stamp. Run `dummyindex ingest` first.", which is advice that re-clusters and discards curation.

   **Fix:** keep `SCHEMA_VERSION = 1` until a field actually changes, or add a CHANGELOG warning that 0.37.0 must not touch schema-2 repos.

4. `dummyindex/context/build/enriched_refresh.py:176-200,285-291,318-324`: the stamp is not the last write, and a missing meta goes unreported.
   - `refresh_summaries` and `write_naming_md` run after `_advance_version_stamp`, outside any `try`. If they fail, the stamp has moved over stale `PROJECT.md`/`overview.md`/`naming.md` while the caller reports "refresh failed".
   - A missing, corrupt or newer-schema meta makes both meta writers return quietly with `failed=()`. No "version stamp not advanced" line prints, and `scan_root`'s raw read (`scope.py:45-60`) falls back to scope `.` for a subdirectory index.

   **Fix:** read meta once before the migration (abort on a newer schema; add a `failed` entry when meta is missing or corrupt), pass `refresh_summaries` the target version, and stamp after the summaries.

5. `dummyindex/context/build/navigation_refresh.py:26-33,81-84`: `refresh_tree` raises on an unparseable `map/files.json`. That file is committed, rewritten by every refresh, and has no merge driver (`upgrade.py:50-59` sets only `linguist-generated`). So an ordinary two-branch merge conflict blocks every curated refresh and `install` (`project_init.py:92-94`). There is no non-destructive way back, because `build_all` is refused on curated indexes. **Fix:** when files.json is unreadable, treat every path as changed (or use the manifest). Keep the hard refusal for `tree.json`, which holds curation (prior concern, still true).

6. `dummyindex/cli/enrich.py:37`: `enrich-plan` runs `migrate_context_layout` without `validate_context_destination` and throws away the returned `LayoutMigration`.
   - On a linked `.context/`, the retirer deletes and backs up files inside the link target (`_Retirer._inside` checks against the resolved target, `upgrade.py:326-348`). This violates the spec's "linked managed destinations fail before any write".
   - Removed suites disappear from `git status` with no explanation.
   - `stamp_reconciled` has the same gap: it writes `indexed_commit` (`reconcile.py:293`) before its first validation via `scan_root` (`:301`).

   **Fix:** validate the destination first in both places, and print `format_migration_report`.

7. `dummyindex/context/build/meta.py:104-112`, `manifest.py:108-112`, `upgrade.py:399-411`: several writers skip the repo's own atomic-write rules.
   - The anchor and manifest writers use a fixed `<name>.tmp`, no retry on Windows `PermissionError`, and no fsync. Yet `atomic_io._replace_bytes` exists because "hooks from two Claude profiles can update the same repo-local cache concurrently" (`atomic_io.py:40-41`).
   - Nothing serialises the read-modify-write of meta across `_refresh_meta`, `_advance_version_stamp` and `stamp_reconciled`. A failed replace leaves a stray `.context/meta.json.tmp` that `.gitignore` does not cover.
   - Retirement writes the backup without fsync, then unlinks the original. For an uncommitted edited suite whose only other copy is the gitignored `_doc_backups/`, a power loss before the OS flushes the backup loses both.

   **Fix:** route meta and the manifest through `write_text_atomic`, and fsync the backup before `os.unlink`, as `storage._atomic_write` does (`storage.py:219-220`).

8. `dummyindex/export/storage.py:276-329`, `runner.py:211-213`: graph reads are still unbounded in total (prior concern, still true). Each shard is capped at 1,000,000 bytes but the number of shards is not, and `read_graph_payload` loads the whole generation into RAM (12 shards / 12 MB here); `build_all` repeats that read right after publishing. The 600 s grace protects writers, not readers: a reader holding a superseded manifest fails closed once a publish prunes its old shards. **Fix:** have readers re-read the manifest once on `graph shard missing` before failing.

### Resolved since last review

- **Stamp advanced over a failed refresh.** 0.37.0's `_refresh_meta` moved `dummyindex_version` before the catalog and graph were written (`4f3cf0d:…/enriched_refresh.py:298-299`). The stamp is now gated on `failed` (`enriched_refresh.py:176-179`). This is fixed on the refresh path only; see 2.
- **Unbounded shard growth.** 0.37.0 "never deletes old shards" (`4f3cf0d:…/storage.py:5`). `_prune_shards` now re-reads the live manifest and `_touch`es reused shards, so a concurrent writer's generation survives (`storage.py:255-329`).
- **Retired `equipment-evals/` left behind.** It is now retired with a byte-exact v0.36 proof (`upgrade.py:250-275`). Here all 9 suites are deleted and no `_doc_backups/` exists, which fits all of them being byte-exact.
- **Cache reused across versions.** The cache is now scoped by `cache/extraction-version`, and the stamp is withheld if any delete fails (`pipeline/io/cache.py:225-279`).
