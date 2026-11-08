## Data integrity

- **[HIGH]** `context/build/incremental.py:98-122` — the no-change skip never fires on a curated index, because the refresh never rewrites `cache/manifest.json`. Every run re-reports 28 deleted paths (measured: 17 `benchmarks/*` + 11 `tests/benchmarks/*`) and every LF frontmatter `.md` (raw hash at `manifest.py:33-38`, body hash at `pipeline/io/cache.py:91-121`). — Hash the manifest with `file_hash`, overlay doc paths only when `files.json` exists, and ship together with P1.
- **[HIGH]** `context/build/runner.py:152-159,362` — `build_all` writes `meta.json` first and never reads the prior one. A crash, or a graph failure that only warns (`:206-221`), leaves a new stamp over old artefacts; an older CLI, `"0.0.0"` or `"unknown"` overwrites a parseable stamp. — Gate on `read_meta` first, write meta last using `_advance_version_stamp`'s rule, and pass `None`.
- **[HIGH]** `context/build/meta.py:3-6,17` — schema 2 changes no field (`Meta` is identical at `4f3cf0d`, and 0.37.0 already shards), yet 0.37.0 refuses it. This repo's `meta.json` already reads `0.37.0` / schema 2, bumped at an equal version (`enriched_refresh.py:333-338`). — Keep `SCHEMA_VERSION = 1` and read 2 as 1, or add a CHANGELOG warning.
- `context/build/enriched_refresh.py:101-200` — meta is read only after every artefact has been rewritten. A missing, corrupt or newer meta is swallowed silently (`:183-186,288-291,321-324`), and the summaries and `naming.md` run after the stamp, unguarded. — Read meta once before migrating: abort on a newer one, else record a `failed` entry. Stamp last, and give `rebuild` a stamp-only override.
- `context/build/upgrade.py:350-364,413-441` — `is_link` treats any reparse tag (WOF/dedup/cloud) as a link, so a regular file carrying one is unlinked with no backup. The backup itself (`:435`) is not fsynced before `os.unlink`. — Classify from the `lstat` at `:353` (SYMLINK/MOUNT_POINT tags only, locally), and fsync as `export/storage.py:219-220` does.
- `export/storage.py:298-304,409-503` — the prune grace keys on shard mtime, so a reader still holding the prior manifest fails with `graph shard missing`. Reads trust the manifest's own cap (`:414-416`) and its duplicate shards, and the top-level read is uncapped (`:497`). — Re-read the manifest once on a missing shard, clamp the cap, and reject duplicates and oversized totals.

Graph files are bounded; graph consumers currently reconstruct the graph in RAM.
Distinct emitted definitions survive source-ID collisions. Affected IDs receive
suffixes when another collision enters the scan; unique legacy IDs stay compatible.
Unknown call targets remain explicit candidate sets. The existing undirected graph
still aggregates repeated edge observations. Parser coverage is not a proof
that every possible AST construct was extracted.
Missing or corrupt curated tree data is preserved through a failed refresh,
rather than silently replaced with an empty tree.
