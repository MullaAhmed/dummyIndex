# index-lifecycle — raw critiques (deep mode)

The three critic outputs are concatenated verbatim (database, security, product), followed by the cross-review.

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

## Security

- `dummyindex/context/build/meta.py:104-112` (`write_meta`), `dummyindex/context/build/maps.py:289-293` (`_atomic_write_json`), `dummyindex/context/build/manifest.py:108-112` (`write_manifest`), `dummyindex/context/build/conventions.py:193-195,222-224,240-244`, `dummyindex/context/build/tree.py:324-332` (`write_tree`, build route), `dummyindex/pipeline/io/cache.py:343-348` (`save_cached`), `dummyindex/context/build/upgrade.py:75-99` (`_ensure_managed_lines`), `dummyindex/context/build/enriched_refresh.py:220-226`, `dummyindex/pipeline/io/detect.py:271-280` (`convert_office_file`) — **Missing:** a link check on file entries inside `.context/`.
  - Each writer opens either a fixed sibling (`<name>.tmp`) or the target itself with `write_text`, and `write_text` follows a symlink.
  - `*.tmp` is not in the managed `.gitignore`, so a repo can commit `.context/meta.json.tmp` as a link to any file the user can write.
  - On clone + `dummyindex install`, that file outside the repo is truncated and overwritten with build output carrying repo-controlled names. Auto-init runs on any git repo (`installer/install/orchestrate.py:320-332`); `rebuild --changed` does the same.
  - `replace` then installs the link as the live artefact.
  - The `.gitignore`/`.gitattributes` merge reads the link target and appends the managed lines into it.
  - `cache/<sha256>.tmp` has a predictable name.
  - `.pending-enrichment` follows a linked `features/<x>/`.
  - `.context/converted/` is not validated at all.
  - Two concurrent hook runs share one temp file and tear the JSON.

  — **Mitigation:** none for these writers.
  - `validate_context_destination` (`context/build/scope.py:14-35`) checks 8 directories, never files.
  - Other writers already use unique temps or per-component link checks: `context/build/coverage.py:32,83`, `context/build/navigation_refresh.py:154-189`, `context/build/reconcile.py:359`, `export/storage.py:68-102,209-225`.

  — **Fix:**
  - Route every writer through `atomic_io.write_text_atomic`/`_replace_bytes` (`context/domains/atomic_io.py:37-81`). Inside `pipeline`, use `cache._write_bytes_atomic` (`pipeline/io/cache.py:174-204`).
  - Before each read-modify-write (`.gitignore`, `.gitattributes`, `meta.json`), refuse when `is_link(path)`. An atomic replace alone would copy the link target's bytes into a committed in-repo file.
  - Skip linked feature directories.
  - This is the same class as the equip review's fixed-temp bullet.
- `dummyindex/pipeline/extract/__init__.py:178-213` (`extract`), `dummyindex/pipeline/extract/generic.py:50-56,102-425` (`_extract_generic`, `walk`), `dummyindex/context/domains/source_docs/keys.py:26-45` (`harvest_json_keys`), `dummyindex/pipeline/io/cache.py:68-84,116-136` (`read_source_bytes`, `file_hash`), `dummyindex/context/build/incremental.py:293-307` (`_hash_files`) — **Missing:** a per-file byte cap and a recursion guard on untrusted source.
  - Every file is read whole and passed to `parser.parse` with no size check. The build read cache holds every file's bytes for the whole build.
  - `walk(root)` recurses once per AST level, outside both `try` blocks, and `extract` has no per-file `try`.
  - A single committed file nested about 1,000 levels deep raises `RecursionError` and aborts extraction for the whole repo. This happens on every `install`, `rebuild` and refresh, after the migration has already rescoped the cache.
  - `harvest_json_keys` catches only `OSError` and `JSONDecodeError`. A deeply nested `.json` raises `RecursionError` in `json.loads` or `_walk`, and the callers do not guard it (`context/build/enriched_refresh.py:144`, `context/build/runner.py:180`).

  — **Mitigation:** partial.
  - `pipeline/build/references.py:174,185-191` caps files at 2 MB for the textual-reference pass only, and only after the bytes are already in memory.
  - `pipeline/io/detect.py:534-579` (`safe_path`) excludes links, non-regular files and cycles, but not large files.

  — **Fix:**
  - Gate `detect` with `is_safe_read_target(path, max_bytes=…)` (`pipeline/io/paths.py:59-79`). Record oversize files in `coverage.json` as excluded, with a reason.
  - Wrap `extractor(path)` so that `RecursionError`/`MemoryError` marks the file `pending`, or make `walk` iterative.
  - In `harvest_json_keys`, catch `RecursionError` and cap the read size.
- `dummyindex/context/build/reconcile.py:112-160` (`compute_reconcile_report`), `dummyindex/context/build/reconcile.py:383-397` (`_read_indexed_commit`), `dummyindex/context/build/git_delta.py:157-178` (`changed_paths`), `dummyindex/context/build/meta.py:94-101` (`_opt_str`), `dummyindex/context/build/reconcile.py:269,282,293` (`stamp_reconciled`) — **Missing:** shape validation of the reconcile anchor, and an end-of-options marker before revision arguments.
  - `indexed_commit` comes from the committed `meta.json`.
  - `commit_exists` returns `None` when `rev-parse --git-dir` fails (`git_delta.py:79-80`), for example in a source archive without `.git`. `:124` branches only on `is False`, so the raw value reaches `git diff --name-status --no-renames <since>` as a positional argument.
  - There, a value starting with `-` is parsed as a diff option, and git opens a named output file for writing at parse time, even outside a repo. So a crafted anchor can truncate a file outside the tree.
  - This is reachable from the SessionStart drift hook (`context/drift.py:132`), from `context/reconcile_gate.py:251` and from `rebuild --changed` (`context/build/incremental.py:131`).
  - Inside a repo, any rev expression (`HEAD`, a branch name) passes `cat-file -e X^{commit}` and becomes a moving anchor, so every later reconcile reads clean and drift stays hidden.
  - `--to` stores the unresolved string.

  — **Mitigation:** partial. Inside a repo, the `cat-file` probe happens to reject option-shaped values (`git_delta.py:81`), and `stamp_reconciled:269` correctly uses `is not True`. Off-git there is none.

  — **Fix:**
  - Accept only `^[0-9a-f]{40}([0-9a-f]{24})?$` in `_read_indexed_commit` and `_opt_str`, and treat anything else as a broken anchor.
  - Use `is not True` at `reconcile.py:124`.
  - Resolve `--to` with `rev-parse --verify --end-of-options <x>^{commit}` and store the SHA.
  - Put `--end-of-options` before every revision argument (`git_delta.py:81,114,145,177`).
- `dummyindex/cli/enrich.py:20-39` (`run_plan`), `dummyindex/context/build/upgrade.py:321-348` (`_Retirer.__init__`, `_inside`) — **Missing:** a destination check before the `enrich-plan` migration.
  - `run_plan` calls `migrate_context_layout` without first calling `scan_root` or `validate_context_destination`.
  - `_Retirer` sets `_context_real = context_dir.resolve()`, so with a symlinked or junctioned `.context/`, the link target becomes the containment root.
  - As a result, `retire_paths` deletes or backs up `equipment-evals/` and `graph/` in the target, the managed `.gitignore` and `.gitattributes` are written there, and `write_plan` writes `cache/_enrich_plan.json` there.
  - The skill runs this verb unattended.

  — **Mitigation:** none on this caller. The build and refresh routes validate first (`context/build/runner.py:113`, `context/build/enriched_refresh.py:101`). The only incidental barrier is that `build_plan` needs a `tree.json` in the target.

  — **Fix:** call `validate_context_destination(out_root)` in `run_plan`. Also make `migrate_context_layout` refuse when `is_link(context_dir)`, which covers every future caller.
- `dummyindex/context/build/enriched_refresh.py:95-200,270-339` (`refresh_deterministic_artifacts`, `_refresh_meta`, `_advance_version_stamp`), `dummyindex/context/build/runner.py:152-159` (`build_all`), `dummyindex/context/build/incremental.py:148-155`, `dummyindex/cli/rebuild.py:62-67`, `dummyindex/installer/install/orchestrate.py:195,222,331` — **Missing:** a version gate before the first write.
  - The refresh rewrites tree, maps, coverage, naming, catalog and graph before anything calls `read_meta`. `_refresh_meta` and `_advance_version_stamp` then swallow the "upgrade dummyindex" `ValueError` (`context/build/meta.py:72-76`).
  - As a result, an older dummyindex rewrites a schema-3 or newer-version index in its own format, while the stamp still names the newer writer.
  - `build_all` never reads the prior meta, and `new_meta` overwrites both version and schema. So `rebuild --full`, `install`, or `rebuild --changed` on a deterministic-only index lowers the stamp without `--force-downgrade`.
  - On that route, a `None` version becomes `"0.0.0"` (`incremental.py:153`), and a failed version lookup becomes the literal `"unknown"`. Each wipes the extraction cache and is written as the stamp.
  - One `--force-downgrade` both rewrites the skill family and lowers the repo stamp.

  — **Mitigation:** partial, and only on the refresh route.
  - The stamp is held when a required artefact fails.
  - An unparseable version never replaces a parseable one (`:326-331`).
  - `None` skips the scope and stamp.

  — **Fix:**
  - Probe `read_meta` at the top of `refresh_deterministic_artifacts` and `build_all`. Abort before any write if the stored schema is above `SCHEMA_VERSION`, or the stored version is `NEWER` and `allow_downgrade` is not set.
  - Pass `None` instead of `"unknown"` (`cli/rebuild.py:67`).
  - Give the stamp downgrade its own flag.
- `dummyindex/export/storage.py:489-503` (`read_graph_payload`), `dummyindex/export/storage.py:409-484` (`_read_manifest`), `dummyindex/context/build/upgrade.py:50-59` — **Missing:** a byte ceiling on the read side.
  - `read_graph_payload` reads `features/symbol-graph.json` with no `max_bytes`, and accepts legacy JSON of any size.
  - `_read_manifest` takes `cap` from the manifest itself and reads each shard up to that size.
  - Descriptors may repeat the same shard.
  - Together, one committed manifest can make every graph consumer decode and accumulate far more than the 1,000,000-byte write cap before the final hash check runs.
  - The managed `.gitattributes` marks the manifest and its shards `linguist-generated -text`, so GitHub folds that diff out of PR review.

  — **Mitigation:** writes are capped (`:386-390`); only `shard_names` (`:238`) reads with `DEFAULT_MAX_FILE_BYTES`.

  — **Fix:**
  - In `_read_manifest`, reject `cap > DEFAULT_MAX_FILE_BYTES` and duplicate shard paths.
  - Reject a manifest whose summed shard `bytes` exceeds a fixed total before reading any shard.
  - Give the top-level and legacy reads in `read_graph_payload` a hard ceiling.
- `dummyindex/context/build/upgrade.py:350-376,399-411` (`_retire_entry`, `_remove_link`, `_retire_file`), `dummyindex/context/domains/atomic_io.py:16-34,37-67` (`is_link`, `_replace_bytes`) — **Missing:** a check that separates links from other reparse points on the branch that deletes without a backup.
  - `is_link` treats any `FILE_ATTRIBUTE_REPARSE_POINT` as a link. That is fail-closed for following a path, but `_retire_entry` tests it before `S_ISREG`.
  - So a regular file under `equipment-evals/` or `graph/` that carries a file-level reparse tag (WOF/`compact` compression, Data Deduplication) is unlinked with no backup, contradicting `spec.md:30-32`. Sync roots that also tag the parent directory are not affected, because the directory itself takes the link branch and its `rmdir` fails.
  - An lstat error inside `is_link` after the successful `os.lstat` at `:353` takes the same branch.
  - The backup is not `fsync`ed before the source is unlinked.

  — **Mitigation:** none, and `_inside` is skipped for links.

  — **Fix:**
  - Decide from the `info` already read at `:353`.
  - Treat an entry as a link only if it is `S_ISLNK`, or if its `st_reparse_tag` is `IO_REPARSE_TAG_SYMLINK` or `IO_REPARSE_TAG_MOUNT_POINT`.
  - Send other reparse-point files down the backup branch.
  - `fsync` the backup before the unlink, as `export/storage.py:219-220` does.

### Resolved since last review

- None. `concerns.md` has a limits section only and no prior `## Security` section.

**Audit trail**

- **Evidence:**
  - No catalogued prose doc is quoted.
  - `plan.md` and `spec.md` are `confidence: INFERRED`, so they serve only as pointers.
  - 14 cited identifiers were spot-checked in `map/symbols.json`, and all are present.
  - Every claim rests on code read at HEAD `0634bfd`.
  - Function names are given with every range because a concurrent comment-shortening pass shifts line numbers.
- **Prior bullets:**
  - `concerns.md:14-15` ("missing or corrupt curated tree data is preserved") still holds. `navigation_refresh._read` (`dummyindex/context/build/navigation_refresh.py:26-33`) raises before any tree write.
  - `concerns.md:8` ("graph files are bounded") holds only for writes; see the graph-reader bullet.
- **Docs that disagree with the code (the code wins):**
  - `spec.md:14-15`, "linked managed destinations fail before any write": false for `enrich-plan` and for links at file level.
  - `spec.md:30-32`, "every other file is first backed up": false for regular files that carry a reparse tag.
  - `spec.md:35-39`, "never downgrades" and the newer-schema refusal: true only for the refresh's stamp. `build_all` lowers the stamp, and the refresh rewrites artefacts before the refusal.
  - `plan.md:51-52`, "`None` skips cache scope and stamp": true only on the refresh route.
  - Several `plan.md` cites have shifted:
    - `RETIRED_CONTEXT_PATHS` is now `upgrade.py:300-307`.
    - `_retire_file` is now `upgrade.py:399-411`.
    - `migrate_context_layout` is now `upgrade.py:501-552`.
    - `format_migration_report` is now `upgrade.py:577-615`.
    - `_advance_version_stamp` is now `enriched_refresh.py:305-339`.
- **Checked and clean:**
  - Backup-name collisions (`_back_up`, `upgrade.py:413-441`):
    - Each candidate name is lstat-checked.
    - An existing backup is reused only if it is a byte-identical regular file.
    - Links are refused, and nothing is overwritten.
    - It fails closed after 100 names.
    - `_refuse_linked_parents` (`:443-449`) blocks linked ancestors before `mkdir`.
  - Retirement:
    - Links and junctions are unlinked as entries, with an `rmdir` fallback.
    - `_inside` re-checks the resolved path of every real directory and file.
    - `_is_starter_suite` never raises.
  - Cache deletion scope:
    - Only direct children matching `_ENTRY_NAME_RE.fullmatch` that lstat as plain files are deleted (`pipeline/io/cache.py:256-271`).
    - The stamp is not written if anything failed.
    - The cache directory is never created.
    - `.context/cache` is link-checked on the build and refresh routes.
    - `enrich-plan` passes `None`.
  - Scope: `scan_root` (`scope.py:61-73`) rejects absolute and `..` stored scopes and re-checks containment after resolving.
  - `.gitignore` and `.gitattributes` merges: append-only, by stripped-line equality, and never drop a user line. The only defect is the write through a link in bullet 1.
- **Not filed (low):**
  - Force-committed `cache/` entries are honoured; `cache.py:282-291` declares the policy as anti-corruption, not anti-poisoning. They carry the same trust as committed source.
  - `format_migration_report` prints repo-controlled filenames without escaping control characters (`upgrade.py:592-614`).

## Product surface

Paths drop the leading `dummyindex/` except `tests/`. Reconciled at HEAD `0634bfd`. Line numbers come from a working tree whose comments are being shortened, so they can drift by a few lines. `skills/update/SKILL.md` is catalogued `low`, so nothing below relies on it.

- **On an unchanged tree, `rebuild --changed` skips both the upgrade migration and the stamp retry it tells users to run.** Observed: `rebuild_changed` returns `skipped=True` on an empty `ChangeSet` before `migrate_context_layout` or any stamp runs (`context/build/incremental.py:121-122`). The CLI then prints `context rebuild: no source files changed; .context/ unchanged.` and exits 0 (`cli/rebuild.py:87-90`). So after a CLI upgrade with no source edit, all of these stay in place: retired `equipment-evals/` and `graph/`, the root `_enrich_plan.json`, cache entries from other versions, and the old `dummyindex_version` and schema stamp. Nothing on this path reads the meta version, so the output gives no hint of skew. The same skip also catches the retry that the failure line prescribes. `format_migration_report` says "fix the cause, then run `dummyindex context rebuild --changed`" (`context/build/upgrade.py:559`, `:610-614`). But the failed refresh had already written fresh `map/files.json` fingerprints (`context/build/enriched_refresh.py:128`) before the catalog or graph write failed (`:160-174`). The retry therefore sees no change, and the stamp stays where it was. **Gap:** only `install`, or an unrelated source edit, migrates or re-stamps. The printed fix does nothing unless the false positives in bullet 3 happen to force a run. `plan.md:75-76` lists the first half as an open question. The second half is not listed.

- **A held stamp or a missing graph still exits 0, and the failure lines go to stdout.** Observed: the curated branch returns 0 whatever `refresh.failed` holds (`cli/rebuild.py:91-94`). Its last line, `  no feature drift detected.`, prints right after the `version stamp not advanced` line (`cli/rebuild.py:156-183`). `install` returns `True` on the same result (`installer/install/project_init.py:95-130`), and `check --auto-refresh` passes rebuild's 0 through (`cli/check.py:117-124`). The `warning: migration …` and `warning: <artifact> failed …` lines go to stdout via `print` (`cli/rebuild.py:138-145`, `installer/install/project_init.py:99-100`). The same failure also reaches stderr as a Python `UserWarning` (`context/build/enriched_refresh.py:165`, `:173`), and rebuild's other warnings use stderr too (`cli/rebuild.py:36`, `:70-76`). The `build_all` branch (a deterministic-only index, `rebuild --full`, or a first install) behaves differently on a graph failure:
  - it only warns (`context/build/runner.py:214-221`) and skips feature scaffolding (`:225`);
  - `meta.json` already carries the new version stamp (`:152-159`, `:362`);
  - `BuildResult` has no `failed` field (`:78-89`), so `cli/rebuild.py:102-103` prints no failure line.

  **Gap:** a script or agent can detect a held stamp only by grepping stdout. On the `build_all` branch it cannot detect a missing graph at all.

- **The no-change skip never fires on fresh clones or on Markdown docs with frontmatter, so a no-op run dirties tracked files.** Observed: docs have no prior fingerprint except `cache/manifest.json` (`context/build/incremental.py:98-110`). That file is gitignored (`context/build/upgrade.py:30`) and only `build_all` and `reconcile-stamp` write it (`context/build/runner.py:286-298`, `context/build/reconcile.py:300-307`); the refresh never does. On a fresh clone of a curated repo, every in-repo doc counts as `added` until the first `reconcile-stamp`. A `.md` doc with YAML frontmatter never matches at all: the manifest stores a hash of the raw bytes (`context/build/manifest.py:34-38`), while the current side hashes only the body (`pipeline/io/cache.py:116-136`). Such a doc reads `modified` on every run, whether or not the stamp has run since. This repo's `skills/*/SKILL.md` files have frontmatter. Each such run repeats the whole refresh and rewrites two committed timestamps:
  - `meta.json` `updated_at` (`context/build/enriched_refresh.py:150-158`, `context/build/meta.py:42-47`);
  - `conventions/naming.md` `generated_at` (`enriched_refresh.py:197-199`).

  **Gap:** `spec.md:16-17` promises that a run with no fingerprint change touches nothing; the code wins. This also answers `plan.md:80-82`: a doc edit keeps re-triggering until the stamp, and a frontmatter doc keeps re-triggering after it as well. The suite marks this mismatch as deferred (`tests/context/build/test_incremental.py:695-696`). Its fixture holds three code files and no docs (`tests/fixtures/sample_repo/`).

- **A merge-conflicted `tree.json` or `map/files.json` crashes `rebuild` with a traceback and makes `install` skip the rest of the repo wiring.** Observed: `refresh_tree` reads both files through `_read` (`context/build/navigation_refresh.py:26-33`, `:79-84`). `_read` lets `json.JSONDecodeError` propagate, and raises `Invalid navigation data; preserved: <path>` on JSON that is not an object. Change detection tolerates the same corrupt `files.json` (`context/build/incremental.py:310-316`), so the run reaches the refresh. By then the refresh has already run the migration and re-scoped the cache (`enriched_refresh.py:106-107` before `:125`). Neither `cli/rebuild.py:39-46` (which catches only `BuildScopeError`) nor `dispatch` (`cli/__init__.py:139-156`) catches the error. The caller gets a Python traceback, and the `JSONDecodeError` text names no file. `install` does catch it: it prints `auto-init skipped: refresh failed (…)` and returns before CLAUDE.md, hooks, default plugins and the equipment refresh (`installer/install/project_init.py:92-94`, `:107-129`). **Gap:** the data limit in the prior `concerns.md` ("preserved through a failed refresh") still holds, but no output names the bad file or a way to recover. Both files are committed `linguist-generated` artefacts with no merge driver (`context/build/upgrade.py:50-59`).

- **An older CLI refreshes a newer index silently under the newer stamp, and `rebuild` offers no override.** Observed: when the stored stamp is newer, `_advance_version_stamp` keeps it and returns `False` (`context/build/enriched_refresh.py:325-339`). The same run has already rewritten the tree, maps, coverage, naming, catalog and graph with this older extractor (`:125-174`). No output line reports the refused downgrade. `rebuild --changed --force-downgrade` exits 2 with ``error: unknown argument(s) for `rebuild` `` (`cli/rebuild.py:52-57`). `allow_downgrade` is reachable only through `install --force-downgrade` (`installer/install/project_init.py:86-91`). Yet `rebuild --full` and the deterministic branch downgrade without any flag, because `new_meta` writes whatever version it receives (`context/build/runner.py:152`). A newer schema is handled even more quietly:
  - the refresh's three `read_meta` calls swallow the `ValueError` that tells the user to upgrade dummyindex (`context/build/enriched_refresh.py:183-186`, `:288-291`, `:321-324`; raised at `context/build/meta.py:72-76`);
  - counts, `PROJECT.md` and `architecture/overview.md` are skipped without a message, and the run exits 0;
  - only `reconcile-stamp` prints the upgrade advice (`cli/reconcile.py:154-162`).

  The refresh also bumps schema 1 to 2 even when the versions are equal (`enriched_refresh.py:333-338`). For any CLI whose `SCHEMA_VERSION` is lower, that is the newer-schema case just described. **Gap:** the stamp no longer says which version produced the artefacts, and the caller sees neither the refused downgrade nor the schema mismatch.

- **An orphaned anchor takes two refusals to clear, and the markers behind the second refusal are never reported.** Observed: when `indexed_commit` is gone (after a rebase or squash), the refresh writes `.pending-enrichment` into every feature dir (`context/build/enriched_refresh.py:206-226`). `rebuild --changed` prints the reconcile report computed before that write (`context/build/incremental.py:129-137`), and `RefreshResult` has no field for markers (`enriched_refresh.py:64-76`). The output therefore never names them. `reconcile-stamp` then refuses with "Re-baseline with `dummyindex context reconcile-stamp --to <commit>` … or pass --force" (`cli/reconcile.py:250-261`). `--to <sha>` gets past the anchor check but is then `blocked` by every awaiting feature plus any file no feature owns (`context/build/reconcile.py:274-280`, `:124-158`). `--heal-orphaned` stops at the same block (`cli/reconcile.py:108-131`, `:142-143`). **Gap:** the first refusal names a remedy that cannot succeed by itself. Clearing it takes a `mark-enriched` for each feature, or `--force`, and the anchor-broken message mentions neither.

- **A failed version lookup, or two installed CLIs at different versions, keeps wiping the extraction cache.** Observed: `rebuild`, `init` and `install` silently fall back to the string `"unknown"` when `importlib.metadata` fails (`cli/rebuild.py:62-67`, `cli/init.py:184-189`, `installer/common.py:13-18`). `migrate_context_layout` accepts any non-empty string as a cache scope (`context/build/upgrade.py:539-546`). So `scope_cache_to_version` deletes every entry not stamped `unknown` and then stamps `unknown` (`pipeline/io/cache.py:225-279`). The next run with a real version deletes them all again. The same wipe happens on every switch between two installs at different versions, such as the shadowing venv that `check --versions` already detects (`cli/check.py:151-153`). On the `build_all` branch, `"unknown"` also overwrites a parseable stamp (`context/build/runner.py:152`, `context/build/meta.py:54-62`). Only the refresh's `_advance_version_stamp` refuses it (`context/build/enriched_refresh.py:325-331`). **Gap:** each wipe costs a full re-extraction. The output shows only `removed cache: N stale extraction entries` (`upgrade.py:545-546`) and gives no cause. The stamp code treats `unknown` as unresolvable, while the cache scope treats it as a real version.

- **Saved `--docs` roots are recorded but never replayed, so an upgrade drops external docs from the catalog.** Observed: `build_all` saves `config.extra_doc_roots` next to `config.scan_scope` (`context/build/runner.py:148-151`). `scan_root` replays only `scan_scope` (`context/build/scope.py:44-60`), and nothing reads `meta.config.extra_doc_roots` back; `context/domains/source_docs/models.py:107` reads the catalog's own field, not meta's. `install`'s refresh passes `extra_doc_roots=()` (`installer/install/project_init.py:86-91`), and so does `rebuild --changed` run without `--docs` (`cli/rebuild.py:60`, `:81-86`). Either way, `source-docs/INDEX.*` is rebuilt without the external roots (`context/build/enriched_refresh.py:144-146`, `:236-267`). External roots are never diffed either (`context/build/incremental.py:84-93`), so editing one reports "no source files changed". **Gap:** `meta.json` suggests these roots persist the way the scan scope does, and they do not.

### Resolved since last review

- None of the earlier limits in `concerns.md` is resolved at `0634bfd`. Two were re-checked:
  - deterministic refresh still cannot write semantic summaries: it only carries forward or flags authored abstracts (`context/build/navigation_refresh.py:133-148`);
  - corrupt curated tree data is still preserved (`navigation_refresh.py:26-33`); bullet 4 covers how that failure reaches the user.

  The graph-internal limits (ID collisions, edge aggregation, rebuilding the graph in memory) are outside the product surface and were not re-checked.

## Cross-review

### Notation and method

- `db#N`, `sec#N` and `prod#N` are the N-th top-level finding of each raw critique above, in order. The security and product critiques are unnumbered, so they are counted:
  - sec#: 1 fixed-temp writers, 2 parse caps, 3 reconcile anchor, 4 `enrich-plan`, 5 version gate, 6 graph read caps, 7 reparse retirement.
  - prod#: 1 skip bypasses migration, 2 exit 0, 3 skip never fires, 4 merge conflict, 5 older CLI, 6 orphaned anchor, 7 `"unknown"`, 8 `--docs`.
- `DI#`, `S#` and `P#` are the bullets of the merged `concerns.md`.
- Paths are under `dummyindex/`. Lines are from the current comment-shortened tree, and the code is unchanged since `0634bfd`.
- Each critic's perspective was taken in turn against the other two critiques. Every HIGH was re-read at its cited range.
- Where possible, a HIGH was also reproduced with read-only probes. These ran in the scratchpad with `python -I`; nothing under the repo was written.

### Confirmed HIGHs (8)

1. **DI1** — `rebuild --changed` never skips on a curated index (`context/build/incremental.py:98-122`).
   - **Measured.** Replaying the diff gives 28 `removed` paths, all present only in the manifest: 17 `benchmarks/*` and 11 `tests/benchmarks/*`.
   - **Cause.** `cache/manifest.json` is written only by `build_all` (`runner.py:286-298`) and by `reconcile-stamp` (`reconcile.py:300-307`). Its stale entries are merged under `files.json` (`:104-110`).
   - **Frontmatter mismatch, by code.** The manifest stores raw bytes (`manifest.py:33-38`), but `file_hash` strips frontmatter (`pipeline/io/cache.py:91-121`). On an LF checkout, a frontmatter doc therefore never matches.
2. **P1** — on an unchanged tree, the migration and the stamp retry are skipped.
   - `incremental.py:121-122` returns before `migrate_context_layout` (`enriched_refresh.py:106-107` and `runner.py:125-126`).
   - The retry is a no-op for a code-triggered failure: `files.json` is written (`enriched_refresh.py:128`) before the catalog and graph (`:160-174`).
   - Today this is masked by DI1.
3. **DI2** — `build_all` writes meta first, unguarded.
   - `runner.py:152-159` builds `new_meta`, and `_write_all` writes it first (`:362`). No `read_meta` call exists in `build_all`.
   - A graph failure only warns (`:206-221`).
4. **P2** — `"unknown"` wipes the cache.
   - The fallbacks are `cli/rebuild.py:62-67`, `cli/init.py:189` and `installer/common.py:18`.
   - `upgrade.py:539` accepts any non-empty string, which reaches `scope_cache_to_version` (`pipeline/io/cache.py:195-237`).
   - On `build_all`, `runner.py:152` also stamps it.
5. **DI3** — schema 2 locks out 0.37.0.
   - `4f3cf0d:dummyindex/context/build/meta.py` has `SCHEMA_VERSION = 1` and refuses `version > 1`.
   - A diff of the `Meta` dataclass between `4f3cf0d` and now is empty.
   - 0.37.0 already had `symbol-graph.parts` (`4f3cf0d:dummyindex/export/storage.py:23`).
   - `.context/meta.json` in the working tree is `0.37.0` / schema 2, while HEAD has `0.36.0` / schema 1. The bump happened at an equal version (`enriched_refresh.py:333-338`).
   - 0.37.0's `reconcile-stamp` prints "Run `dummyindex ingest` first" (`4f3cf0d:dummyindex/cli/reconcile.py:158-163`).
6. **S2** — fixed-name `.tmp` writers follow a committed symlink.
   - The writers are `meta.py:108-112`, `manifest.py:108-112`, `maps.py:289-293`, `tree.py:330-332`, `conventions.py:193-195,222-224,242-244` and `pipeline/io/cache.py:296-299`.
   - All of them use `write_text` on a fixed sibling.
   - `validate_context_destination` (`scope.py:14-35`) checks only 8 directories.
   - **Probe blocked.** The symlink probe could not run on this host (WinError 1314), so this is confirmed by Python's `open` semantics.
   - **Exposure.** POSIX clones are exposed. Git for Windows defaults to `core.symlinks=false`.
7. **S3** — parsing has no size or recursion cap.
   - **Reproduced.** `extract([ok.py, deep.py])` with a 1,000-deep and a 3,000-deep parenthesised expression raised `RecursionError` out of the whole batch. There is no per-file guard at `pipeline/extract/__init__.py:173`.
   - **Reproduced.** `harvest_json_keys` on a 100,000-deep JSON array raised `RecursionError`, because `keys.py:42-43` catches only `OSError`/`JSONDecodeError`.
8. **S1** — an unchecked `indexed_commit` reaches git as an option.
   - **Reproduced.** Outside any repo, `git -C <dir> -c core.quotePath=false diff --name-status --no-renames --output=<victim>` exited 129 and truncated the victim to 0 bytes (git 2.54.0.windows.1).
   - **Path.** `reconcile.py:112` → `:124` (`is False` only, while `commit_exists` returns `None` off-git, `git_delta.py:79-80`) → `:160` → `git_delta.py:170-178`.
   - **Callers.** `context/drift.py:132`, whose comment says it works off-git, plus `reconcile_gate.py:251`, `incremental.py:131` and `cli/maintain.py:73,144`.

### Refuted or corrected

- **db#6, second half — refuted.** It says `stamp_reconciled` writes `indexed_commit` before its first validation. In fact `reconcile.py:267` calls `compute_reconcile_report`, which runs `scan_root` (and so `validate_context_destination`) at `:102`, before `write_meta` at `:293`. The `enrich-plan` half stands, since `cli/enrich.py:12-51` has no `scan_root`.
- **sec#1 — refuted.** It says "`*.tmp` is not in the managed `.gitignore`, so a repo can commit the link". Ignore rules never stop a committed or force-added file from checking out, so they are no mitigation. The missing pattern matters only for db#7's stray `meta.json.tmp` hygiene.
- **prod#6 — partly refuted.** It says the anchor-broken message "mentions neither" `mark-enriched` nor `--force`. In fact `cli/reconcile.py:250-260` says "or pass --force to anchor at HEAD anyway". What is missing is only `mark-enriched` and any report of the markers.
- **db#1 — count corrected.** "28 `benchmarks/*` paths" is really 17 `benchmarks/*` + 11 `tests/benchmarks/*`.
- **db#1 / prod#3 — frontmatter claim qualified.** The claim is "25 frontmatter docs read modified forever". It holds on LF checkouts only:
  - This autocrlf checkout has 27 tracked frontmatter `.md` files, all CRLF, and 25 of them are in the manifest.
  - `_FRONTMATTER_FENCE_RE` (`pipeline/io/cache.py:25`) does not match `---\r`, so nothing is stripped here.
  - Only 2 docs mismatch, and both are real edits. The 3 manifest-only `modified` paths include `CHANGELOG.md`.
  - The 316 `modified` code paths are the live comment pass, not a finding.
- **Cite drift corrected in `concerns.md`.**
  - `pipeline/io/cache.py`: `file_hash` is at `107-121`, not 116-136; `scope_cache_to_version` at `195-237`; `save_cached` at `285-311`.
  - `installer/install/project_init.py`: the refresh is at `67-75`, and `build_all` at `113-123`.
  - `installer/install/orchestrate.py`: the auto-init gate is at `301-310`.
  - `pipeline/extract/generic.py`: `walk` is at `96-419`.

### Merged (deduplicated)

- **DI1** ← db#1 + prod#3. Both are the rebuild-skip false positive.
- **P1** ← prod#1. This rebuild-skip finding is kept separate because it has the opposite failure (a skip that bypasses work), and it is cross-linked to DI1.
- **DI2** ← db#2 + sec#5 (the `build_all` half).
- **DI3** ← db#3 + prod#5 (the schema-bump tail).
- **DI4** ← db#4 + sec#5 (the refresh half) + prod#5. All three describe a newer meta that is swallowed with no gate before the first write, and `rebuild` having no override.
- **DI5** ← sec#7 + db#7 (backup not fsynced before unlink).
- **DI6** ← db#8 (prune race) + sec#6 (read-side byte ceiling).
- **S1** ← sec#3.
- **S2** ← sec#1 + db#7 (fixed tmp, no lock, concurrency tear).
- **S3** ← sec#2.
- **S4** ← db#6 (first half) + sec#4.
- **P2** ← prod#7 + db#2 (the `"unknown"` tail).
- **P3** ← prod#2.
- **P4** ← db#5 + prod#4.
- **P5** ← prod#6.
- **P6** ← prod#8.
- Not filed, low: force-committed `cache/` entries, and unescaped control characters in `format_migration_report` (`upgrade.py:592-614`).

### Flagged fix conflicts

1. **DI1 vs P1.** A reliable skip turns P1's bypass (no migration, no stamp retry) into the steady state; on this repo, the 28 phantom removals currently force a run every time. They must land together:
   - either run the migration and a meta version/schema check before `incremental.py:121`,
   - or don't write `files.json` (`enriched_refresh.py:128`) when the catalog or graph fails.
2. **db#1's "doc paths only from the manifest" vs the fallback and Model B.**
   - It must keep the full-manifest fallback when `files.json` is absent (`incremental.py:99-103`), which db#5 also relies on.
   - Fresh clones read every doc as `added` because the manifest is gitignored. The obvious fix, writing the manifest at refresh time, is forbidden by Model B (`reconcile.py:296-299`).
   - So a refresh-owned doc fingerprint is needed.
3. **db#3 "keep `SCHEMA_VERSION = 1`" vs sec#5/DI4's newer-schema gate.** Reverting removes the value the gate keys on. Current builds would also refuse metas already stamped 2, this repo's included. The revert must read 2 as 1.
4. **sec#7 vs sec#1/sec#4.** sec#7 narrows link detection; sec#1 and sec#4 rely on `is_link` failing closed. Scope the narrowing to the `lstat` already read at `upgrade.py:353`, and leave `is_link` (`domains/atomic_io.py:16-34`) unchanged.
5. **prod#2's non-zero exit for a held stamp vs hooks.** `check --auto-refresh` passes rebuild's code straight through (`cli/check.py:117-124`) into SessionStart, so it needs a distinct code and a tolerant hook.
6. **db#5's "treat every path as changed" vs curation noise.** When `files.json` is unreadable, that would mark every annotated node `source-stale` (`navigation_refresh.py:149-152`). Prefer its other option: manifest hashes.
7. **sec#5 "a separate flag for the stamp downgrade" vs prod#5 "rebuild has no `--force-downgrade`".** These are compatible if `rebuild` gains a stamp-only flag. Do not reuse install's skill-family flag.

### Prior `concerns.md` limits

- "Missing or corrupt curated tree data is preserved" (`concerns.md:14-15`) still holds: `navigation_refresh.py:26-33` raises before any tree write.
- "Deterministic refresh cannot write semantic summaries" still holds.
- "Graph files are bounded" (`:8`) now holds for writes only (`export/storage.py:386-390`); reads are covered by DI6.
- The ID-collision, edge-aggregation and in-RAM graph limits were not re-checked.
