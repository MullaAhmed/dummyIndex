# Spec — Upgrade hygiene: prune orphan graph shards, versioned retired-artifact migration on the install refresh path, stamp meta last and never downgrade, graph-format schema marker

> Code-only change. `.context/` is never hand-edited by this work: every effect
> on an existing repo lands when the updated CLI runs its normal install /
> `/dummyindex-update` refresh. Source of findings:
> `.context/audits/upgrade-path-for-existing-repos-on-older-dummyindex-versions/report.md`
> (findings 1, 4, 6, 7, 12, 13). User direction: "as the new version comes up we
> need to clean up all" — an upgrade removes everything the new version
> retired or orphaned, not only what it can prove it generated.

## Intent

A repo indexed by an older dummyindex accumulates state the current version
neither reads nor removes, and the update flow can report success on a partial
refresh. In this repo after 0.36 → 0.37:

- `features/symbol-graph.parts/` holds 91 shards; the manifest references 12;
  79 orphans (73,171,940 B) are committed (`export/storage.py:L285` "Never
  remove old shards"; the plain-JSON branch `L239-L241` orphans every shard).
- `.context/equipment-evals/` (9 generated starter suites) has no writer or
  reader since 0.37 removed `equipment-eval`; nothing retires it.
- The curated install refresh (`refresh_deterministic_artifacts`, used by
  `/dummyindex-update` and `rebuild --changed`) skips `ensure_context_gitignore`
  and `remove_legacy_enrich_plan`; the legacy `graph/` migration runs only from
  `refresh-indexes`.
- `meta.dummyindex_version` advances *before* the catalog and graph writes,
  whose failures are swallowed (`enriched_refresh.py:L154-L195`), and is
  overwritten on any difference, so a stale CLI downgrades it (`L298`).
- 0.37's sharded graph manifest shipped without a version marker
  (`meta.SCHEMA_VERSION` still 1).
- `.context/cache/` extraction entries carry no version; 466 of 537 entries
  reused by today's 0.37 refresh were written by 0.36 code (latent staleness).

Who: everyone who upgrades dummyindex on an existing repo, and teams sharing a
committed `.context/`.

## Contracts

1. **Shard pruning — current generation only (`dummyindex/export/storage.py`).**
   After a successful publish, `write_graph_payload` deletes every entry in
   `<dir>/symbol-graph.parts/` that (a) is named `^[0-9a-f]{64}\.json$`,
   (b) is not referenced by the just-published file (plain branch ⇒ nothing is
   referenced), (c) is not referenced by the manifest re-read from disk
   immediately before pruning, and (d) has an mtime older than
   `SHARD_GRACE_SECONDS = 600`. Reused shards are `os.utime`-touched before the
   manifest publish. An emptied `symbol-graph.parts/` is removed.
   - Prune runs only after the publish replace succeeded; a failed publish
     deletes nothing.
   - Symlinks / reparse points (lstat `S_ISLNK` or
     `FILE_ATTRIBUTE_REPARSE_POINT`, py3.10-safe) and non-matching names are
     never deleted; a linked `symbol-graph.parts/` skips pruning entirely.
   - Prune is contained: any `OSError` / `GraphStorageError` becomes one
     `warnings.warn`, never a publish failure.
   - Breaking change (user-approved): a reader holding a superseded manifest no
     longer finishes; it fails closed. A missing shard now raises
     `GraphStorageError("graph shard missing: <path>; run `dummyindex context
     rebuild --changed`")` instead of `FileNotFoundError`.
   - A pre-existing shard whose bytes do not match its hash name is atomically
     rewritten with the correct content instead of raising "corrupt".
   - One manifest per directory is the supported layout (documented in the
     module docstring).
   - Existing repos are swept by the next graph write (every install refresh
     and build calls `build_graph`); no separate one-shot sweep exists. A shard
     freshly checked out by git is young, so it is swept on a later refresh.
   - `shard_names(manifest_path) -> frozenset[str]` becomes the one public
     helper for "which shards does this manifest reference";
     `context/domains/evolve_native_snapshot.py:L48-L81` uses it instead of
     reaching into `_HASH_RE`.

2. **One context-layout migration (`dummyindex/context/build/upgrade.py`, new).**
   `migrate_context_layout(context_dir, *, package_version) -> LayoutMigration`
   runs each step in its own `try`, recording failures instead of raising:
   `ensure_context_gitignore`, `ensure_context_gitattributes`,
   `remove_legacy_enrich_plan` (moved here from `runner.py` together with
   `_ensure_managed_lines` and the `_MANAGED_*` constants / headers, and
   re-exported from `runner` for existing importers), retired paths, and the
   extraction-cache version check. `LayoutMigration` is a frozen dataclass:
   `removed: tuple[str, ...]`, `backed_up: tuple[str, ...]`,
   `errors: tuple[str, ...]`. Callers: `runner._write_all` (fresh / full
   build), `refresh_deterministic_artifacts` (install refresh and
   `rebuild --changed`), `cli/enrich.py` (replacing its two direct helper
   calls). The result travels in `BuildResult.migration` and
   `RefreshResult.migration` and is printed by `installer/install/project_init.py`
   and `cli/rebuild.py`.

3. **Retired paths are removed wholesale.** `RETIRED_CONTEXT_PATHS` is a tuple
   of frozen `RetiredPath(rel_path, retired_in, is_generated)` records.
   For every regular file under a registered path:
   - `is_generated(file)` true → deleted;
   - otherwise → copied to `.context/_doc_backups/retired/<retired_in>/<rel>`
     (already gitignored via `_doc_backups/`), then deleted;
   - the registered directory is removed bottom-up once empty;
   - links / reparse points are unlinked as entries, never followed; a linked
     registered root is unlinked without touching its target; nothing outside
     `.context/` is ever opened;
   - a missing path is a silent no-op; a second run is a no-op.

   Entries:
   - `equipment-evals/`, retired `0.37.0`. `is_generated` re-renders the v0.36
     starter suite (vendored from `cli/equip/seed.py` at `v0.36.0`, key order
     `case_id, prompt, expects_trigger`, `json.dumps(indent=2) + "\n"`) for the
     tool in the filename and the capabilities in its `<cap>-positive` case
     ids, accepting both capability renderings — plain (`'test'`) and enum
     (`Capability.TEST` / `<Capability.TEST: 'test'>`) — and compares bytes after
     `\r\n` → `\n`. `*.result.json` / `*.benchmark.json` and edited suites are
     backed up.
   - `graph/`, retired `0.6.0` (legacy pre-v0.6 layout). On the build paths the
     symbol graph is rewritten right after, so the directory is backed up and
     removed rather than promoted. `cli/migrate.py:migrate_legacy_layout`
     (`refresh-indexes`, which writes no graph) keeps its existing promotion
     behaviour unchanged.

4. **Extraction-cache version scope (`dummyindex/pipeline/io/cache.py`).**
   `.context/cache/extraction-version` records the package version that wrote
   the content-hash entries. On mismatch (or absence with entries present),
   every `^[0-9a-f]{64}\.json$` entry directly under `cache/` is deleted and the
   stamp rewritten; other cache files (`manifest.json`, `skill-feedback.json`,
   plans) are untouched. Entries are rebuilt by the following extraction.

5. **Version stamp written last; downgrade only when forced
   (`dummyindex/context/build/enriched_refresh.py`).** Order: maps → tree →
   coverage → naming.json → catalog → graph → `_advance_version_stamp` →
   `refresh_summaries` → naming.md → EOF normalisation. The early meta refresh
   updates counts / root / languages only. `_advance_version_stamp(context_dir,
   version, *, allow_downgrade)`:
   - no-op when `version is None` or any **required** artifact failed. Required:
     `source-docs/INDEX.json` and `features/symbol-graph.json`. Derived graph
     roll-ups (seed-rank, communities) stay best-effort.
   - advances `dummyindex_version` when `compare_versions(stored, version)` is
     `older`, or stored is unparseable and version parses, or `allow_downgrade`
     is true; never writes an unparseable version over a parseable one.
   - also writes `schema_version = SCHEMA_VERSION` (2).
   - unreadable meta is skipped silently, as `_refresh_meta` does today.

   `RefreshResult.failed: tuple[tuple[str, str], ...]` carries
   `(artifact, error)`. `project_init` and `cli/rebuild.py` print
   `.context/ -> warning: <artifact> failed (<error>); version stamp not
   advanced — fix the cause, then run dummyindex context rebuild --changed`.
   `--force-downgrade` is threaded from `installer/install/orchestrate.py`
   through `project_init` into `allow_downgrade`. `skills/update/SKILL.md`
   step 4 treats that warning as a named failure instead of re-looping.
   Out of scope: `build_all` writes a fresh `new_meta` first (a full rebuild
   owns its stamp).

6. **Schema marker (user-approved bump).** `meta.SCHEMA_VERSION` = 2; `read_meta`
   still accepts 1. `new_meta` writes 2; the refresh writes 2 only via
   `_advance_version_stamp`. When `read_meta` rejects a newer schema, the
   `reconcile-stamp` error (`cli/reconcile.py:L158-L163`) and `status` / `check`
   paths print "meta.json was written by a newer dummyindex — upgrade
   dummyindex" instead of "Run `dummyindex ingest` first". Accepted trade-off:
   0.36 / 0.37 CLIs cannot read a 0.38+ index. The literal `schema_version 2`
   must not appear in skill markdown (`tests/test_skills_doc_hygiene.py:L176-L193`).

7. **Shared version comparator (`dummyindex/versioning.py`, new).**
   `parse_version` and `compare_versions` returning `VersionOrder(str, Enum)`
   (`OLDER/EQUAL/NEWER/UNKNOWN`, values `"older"`…), moved from
   `installer/common.py:L390-L418`; `_parse_version` / `_compare_stamp` stay as
   aliases so the four installer callers are untouched. `context/` never
   imports `installer/`.

Out of scope (audit report): cache-key path collision, junction handling in
the installer, legacy ownership catalogue, `build_all` meta ordering, and bloat
cuts other than shard pruning and cache scoping.

## Acceptance

- [ ] Shards: after three sharded publishes (60/80/100 nodes, `max_file_bytes=4096`, shard mtimes aged past the grace period), `set(listdir(parts)) == shard_names(manifest)`.
- [ ] Shards: 5 seeded orphans named `f"{i:064x}.json"` with old mtimes are deleted by one publish; a seeded orphan younger than 600 s survives.
- [ ] Shards: a plain publish after a sharded one leaves no `symbol-graph.parts/` directory.
- [ ] Shards: `notes.txt`, a `.x.tmp` file and a symlink named `<64hex>.json` pointing outside survive, and the link target's bytes are unchanged.
- [ ] Shards: an `unlink` failure on one seeded name gives a `UserWarning`; the publish succeeds and the graph reads back equal.
- [ ] Shards: a failed manifest publish (existing `test_failed_manifest_publish_keeps_previous_graph_readable`) also leaves seeded orphans in place.
- [ ] Shards: reading a manifest whose shard was deleted raises `GraphStorageError` matching `rebuild --changed`.
- [ ] Shards: a pre-existing shard with wrong bytes is rewritten and the publish succeeds.
- [ ] Shards: `test_reader_holding_previous_manifest_can_finish_after_publication` is replaced by a test asserting the superseded manifest now raises `GraphStorageError`.
- [ ] Retire: each of the 9 committed v0.36 fixture suites (`tests/fixtures/retired_equipment_evals/`, copied from `git show v0.37.0:.context/equipment-evals/<f>`), in both LF and CRLF, is deleted with no backup.
- [ ] Retire: an edited suite (one-char prompt edit, extra case, extra key, flipped `expects_trigger`, BOM, non-JSON) and a `*.result.json` are backed up under `_doc_backups/retired/0.37.0/` byte-identical, then deleted.
- [ ] Retire: `equipment-evals/` and its nested emptied subdirs are gone afterwards; a second run reports `removed == backed_up == ()`.
- [ ] Retire: `equipment-evals` as a symlink (and on Windows a junction via `_winapi.CreateJunction`) pointing outside `.context/` is removed as a link and the outside file is untouched.
- [ ] Retire: legacy `graph/graph.json` + `GRAPH_REPORT.md` are backed up and removed on `refresh_deterministic_artifacts`; `tests/cli/test_migrate.py` still passes unchanged.
- [ ] Migration: `refresh_deterministic_artifacts` on a fixture with a legacy `graph/`, a root `_enrich_plan.json`, a deleted `_council-log.json` gitignore line and old orphan shards ends with all four fixed, and `result.migration` names each.
- [ ] Migration: an `OSError` raised by one step is in `result.migration.errors` and the refresh still returns.
- [ ] Migration: `build_all` on the same seeded state migrates it (`tests/context/build/test_runner.py`) and exposes `BuildResult.migration`.
- [ ] Cache: entries plus `extraction-version` = `0.36.0`, refreshed as `9.9.9` → hash entries gone, `manifest.json` kept, stamp = `9.9.9`; same version → entries kept.
- [ ] Stamp: with `enriched_refresh.build_graph` raising (`pytest.warns(UserWarning)`), stored `0.36.0` + version `9.9.9` → stays `0.36.0`, and `failed == (("features/symbol-graph.json", <msg>),)`; same for `write_catalog` raising → `source-docs/INDEX.json`.
- [ ] Stamp: parametrized (stored, new, allow_downgrade) → expected: (0.37.0, 0.36.0, F) → 0.37.0; (0.37.0, unknown, F) → 0.37.0; (0.37.0, None, F) → 0.37.0; (0.37.0, 0.37.0, F) → 0.37.0; (0.37.0, 9.9.9, F) → 9.9.9; (unknown, 0.37.0, F) → 0.37.0; (unknown, unknown, F) → unknown; (0.37.0, 0.36.0, T) → 0.36.0. No test uses `PACKAGE_VERSION`.
- [ ] Stamp: after an advancing refresh, `PROJECT.md`'s version line equals the new meta stamp.
- [ ] Schema: `new_meta().schema_version == 2`; a v1 meta loads; an advancing refresh rewrites 1 → 2; a failed refresh leaves 1; a schema-3 meta makes `reconcile-stamp` print "upgrade dummyindex" and not "dummyindex ingest".
- [ ] Versioning: `_compare_stamp`/`_parse_version` agree with `compare_versions`/`parse_version` on `None`, `""`, `v0.37.0`, `0.38.0.dev1`, and `compare_versions("0.36.0", "0.37.0") == "older"`.
- [ ] Install: in `tests/test_install.py` (reusing `_make_repo_with_source`, `_curate_index`), 7 starter + 1 edited suite → stdout of the 2nd `install(scope="project")` has exactly 5 removed lines, `… and 3 more`, one backed-up line; with `enriched_refresh.build_graph` raising, stdout contains `version stamp not advanced`.
- [ ] `python -m pytest tests/ -q --tb=short` and `ruff check dummyindex tests` pass.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `install-surface`
- `index-lifecycle`
- `graph-query`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
