## Data integrity

- **[HIGH]** `context/build/incremental.py:98-122` — the no-change skip never fires on a curated index, because the refresh never rewrites `cache/manifest.json`. Every run re-reports 28 deleted paths (measured: 17 `benchmarks/*` + 11 `tests/benchmarks/*`) and every LF frontmatter `.md` (raw hash at `manifest.py:33-38`, body hash at `pipeline/io/cache.py:91-121`). — Hash the manifest with `file_hash`, overlay doc paths only when `files.json` exists, and ship together with P1.
- **[HIGH]** `context/build/runner.py:152-159,362` — `build_all` writes `meta.json` first and never reads the prior one. A crash, or a graph failure that only warns (`:206-221`), leaves a new stamp over old artefacts; an older CLI, `"0.0.0"` or `"unknown"` overwrites a parseable stamp. — Gate on `read_meta` first, write meta last using `_advance_version_stamp`'s rule, and pass `None`.
- **[HIGH]** `context/build/meta.py:3-6,17` — schema 2 changes no field (`Meta` is identical at `4f3cf0d`, and 0.37.0 already shards), yet 0.37.0 refuses it. This repo's `meta.json` already reads `0.37.0` / schema 2, bumped at an equal version (`enriched_refresh.py:333-338`). — Keep `SCHEMA_VERSION = 1` and read 2 as 1, or add a CHANGELOG warning.
- `context/build/enriched_refresh.py:101-200` — meta is read only after every artefact has been rewritten. A missing, corrupt or newer meta is swallowed silently (`:183-186,288-291,321-324`), and the summaries and `naming.md` run after the stamp, unguarded. — Read meta once before migrating: abort on a newer one, else record a `failed` entry. Stamp last, and give `rebuild` a stamp-only override.
- `context/build/upgrade.py:350-364,413-441` — `is_link` treats any reparse tag (WOF/dedup/cloud) as a link, so a regular file carrying one is unlinked with no backup. The backup itself (`:435`) is not fsynced before `os.unlink`. — Classify from the `lstat` at `:353` (SYMLINK/MOUNT_POINT tags only, locally), and fsync as `export/storage.py:219-220` does.
- `export/storage.py:298-304,409-503` — the prune grace keys on shard mtime, so a reader still holding the prior manifest fails with `graph shard missing`. Reads trust the manifest's own cap (`:414-416`) and its duplicate shards, and the top-level read is uncapped (`:497`). — Re-read the manifest once on a missing shard, clamp the cap, and reject duplicates and oversized totals.

## Security

- **[HIGH]** `context/build/reconcile.py:124,160` → `context/build/git_delta.py:170-178` — off-git, `commit_exists` returns `None` and `:124` tests only `is False`. A committed `indexed_commit` of `--output=<path>` therefore reaches `git diff` as an option, via the drift hook (`context/drift.py:132`). Reproduced: the target was truncated to 0 bytes. — Accept only 40- or 64-hex anchors, use `is not True`, resolve `--to` (`:269,282`) to a SHA, and put `--end-of-options` before every rev.
- **[HIGH]** `context/build/meta.py:108-112` (also `manifest.py:108-112`, `maps.py:289-293`, `tree.py:330-332`, `conventions.py:193-244`, `pipeline/io/cache.py:296-299`) — a fixed `<name>.tmp` + `write_text` follows a committed symlink on POSIX clones, because `scope.py:14-35` checks directories only. `upgrade.py:75-99` also appends into a linked `.gitignore`. — Use `write_text_atomic`, and refuse `is_link` before every read-modify-write.
- **[HIGH]** `pipeline/extract/__init__.py:148-182` + `context/domains/source_docs/keys.py:26-45` — there is no byte cap or recursion guard. Reproduced: a 1,000-deep `.py` aborted `extract()` for the whole repo, and a 100k-deep `.json` aborted `harvest_json_keys`; either breaks every install, rebuild and refresh. — Contain `extractor(path)` (`:173`) as `pending`, catch `RecursionError`, and gate `detect` on `is_safe_read_target`.
- `cli/enrich.py:28-39` — `enrich-plan` migrates without `validate_context_destination`, and `_Retirer` (`upgrade.py:321-348`) uses a linked `.context/`'s target as its containment root. It deletes retired paths and writes managed files there, and the report is dropped. — Validate in `run_plan`, make `migrate_context_layout` refuse a linked `context_dir`, and print the report.

## Product surface

- **[HIGH]** `context/build/incremental.py:121-122` — an unchanged tree returns before the migration and the stamp (`cli/rebuild.py:87-90`). The printed retry (`upgrade.py:559,610-614`) is therefore a no-op once a failed refresh has written `files.json` (`enriched_refresh.py:128` vs `:160-174`), and only DI1 masks this today. — Check the migration and the meta version before skipping, or withhold `files.json` on failure.
- **[HIGH]** `cli/rebuild.py:62-67` (also `cli/init.py:189`, `dummyindex/installer/common.py:18`) — a failed version lookup becomes `"unknown"`, which is a valid cache scope (`upgrade.py:539-546`). `scope_cache_to_version` then wipes every entry, and does so again on the next real version, with no cause shown. — Pass `None` and name the cause.
- `cli/rebuild.py:91-94,138-145` — a held stamp exits 0, prints its failure to stdout and then "no feature drift detected", and `install` still returns True (`installer/install/project_init.py:76-81,111`). `BuildResult` (`runner.py:78-89`) has no `failed` field, so a missing graph is hidden. — Use a distinct exit code, send failures to stderr, and add a `failed` field.
- `context/build/navigation_refresh.py:26-33,79-84` — a merge-conflicted `tree.json` or `map/files.json` raises a bare `JSONDecodeError` that names no file. `rebuild` tracebacks (`cli/rebuild.py:39-46`), and `install` skips wiring (`installer/install/project_init.py:73-75`). — Name the file and the recovery, fall back to the manifest for `files.json`, and keep refusing a bad `tree.json`.
- `context/build/enriched_refresh.py:206-226` — an orphaned anchor drops `.pending-enrichment` markers that are never reported (`RefreshResult` `:64-76`), so `reconcile-stamp --to` still refuses on them (`context/build/reconcile.py:274-280`). — Report the markers, and name `mark-enriched` in the refusal (`cli/reconcile.py:250-260`).
- `context/build/runner.py:148-151` — `config.extra_doc_roots` is saved but never replayed (`scope.py:44-60`). `install` and a bare `rebuild --changed` pass `()`, which drops external docs from `source-docs/INDEX.*`. — Replay the saved roots, or stop recording them.

## Cross-review notes

- **Notation.** Paths are under `dummyindex/`, with lines from the current comment-shortened tree. `DI#`/`S#`/`P#` are the bullets above; `db#`/`sec#`/`prod#` are the raw critique bullets in `council/10-critiques.md`.
- **Refuted.**
  - db#6: "`stamp_reconciled` writes before validating". In fact `scan_root` runs at `context/build/reconcile.py:267`→`:102`, before the write at `:293`.
  - sec#1: "an un-ignored `*.tmp` enables the link". Ignore rules never block a committed file.
  - prod#6: "the message names neither remedy". `cli/reconcile.py:250-260` names `--force`.
- **Qualified.**
  - The frontmatter mismatch occurs on LF checkouts only. This autocrlf checkout has 27 CRLF frontmatter docs and strips none (`pipeline/io/cache.py:25`).
  - S2 is confirmed by code; the Windows probe was blocked (WinError 1314).
- **Merged.**
  - db#1 + prod#3 → DI1
  - db#2 + sec#5 → DI2
  - db#3 + prod#5 → DI3
  - db#4 + sec#5 + prod#5 → DI4
  - sec#7 + db#7 → DI5
  - db#8 + sec#6 → DI6
  - sec#1 + db#7 → S2
  - db#6 + sec#4 → S4
  - prod#7 + db#2 → P2
  - db#5 + prod#4 → P4
- **Fix conflicts.**
  - DI1 unmasks P1, so ship them together.
  - DI1 must keep the fallback when `files.json` is absent (`context/build/incremental.py:99-103`). Model B forbids writing the manifest at refresh time (`context/build/reconcile.py:296-299`).
  - Reverting the schema (DI3) removes the value DI4's gate keys on, so read 2 as 1.
  - Narrow DI5 locally, and keep `is_link` fail-closed for S2/S4.
  - P3's non-zero exit reaches SessionStart through `cli/check.py:117-124`.
  - Treating every path as changed on a bad `files.json` labels all annotated nodes `source-stale` (`context/build/navigation_refresh.py:149-152`).
- **Prior limits.**
  - Corrupt tree data is still preserved (`context/build/navigation_refresh.py:26-33`).
  - The deterministic refresh still writes no semantic summaries.
  - "Graph files are bounded" now holds for writes only.
  - ID collisions and edge aggregation were not re-checked.
