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
