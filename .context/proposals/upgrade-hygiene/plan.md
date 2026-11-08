# Plan — Upgrade hygiene: prune orphan graph shards, versioned retired-artifact migration on the install refresh path, stamp meta last and never downgrade, graph-format schema marker

> Code + tests only — no task edits `.context/` content directly.
> Revised once after the critique panel (reuse/architecture, risk, testability).

## Tasks

1. **Neutral version comparator** — `dummyindex/versioning.py` (new),
   `dummyindex/installer/common.py`, `tests/test_versioning.py` (new, `unit`).
   Move `_parse_version` / `_compare_stamp` (`installer/common.py:L390-L418`)
   to `parse_version` / `compare_versions` returning `VersionOrder(str, Enum)`;
   keep the old private names as aliases (4 installer callers untouched).

2. **Shard pruning + reader hardening** — `dummyindex/export/storage.py`,
   `dummyindex/context/domains/evolve_native_snapshot.py`,
   `tests/export/test_graph_storage.py`.
   - public `shard_names(manifest_path)` built on `_read_bytes(max_bytes=…)`,
     `_decode`, `_HASH_RE`, `_PARTS_DIR`; `OSError` propagates, decode/format
     failure → empty. Repoint `evolve_native_snapshot.py:L48-L81` at it.
   - local `_is_linked(info)` (S_ISLNK or reparse attribute) reused by
     `_plain_path` and the pruner.
   - `_prune_shards(path, keep)`: skip when the parts dir is linked/missing;
     scandir + lstat; delete only `^[0-9a-f]{64}\.json$`, unlinked-from-`keep`,
     not in `shard_names(path)` re-read now, mtime older than
     `SHARD_GRACE_SECONDS = 600`; rmdir when empty; whole body in
     `except (OSError, GraphStorageError)` → one `warnings.warn`.
   - `write_graph_payload`: `os.utime` existing reused shards; replace the
     corrupt-shard raise (`L277-L280`) with an atomic rewrite; call
     `_prune_shards` after the final `_atomic_write` on both branches
     (plain branch: `keep=∅`).
   - `_read_manifest`: map `FileNotFoundError` on a shard to
     `GraphStorageError(... run dummyindex context rebuild --changed)`.
   - Update module docstring (current-generation retention, one manifest per
     dir). Extend `_write_sharded` with a node-count parameter. Replace
     `test_reader_holding_previous_manifest_can_finish_after_publication`;
     check `test_sharded_generations_are_deterministic_across_record_orders_and_names`
     (L149, two manifests in one dir) still holds or isolates its dirs.

3. **Context-layout migration module** — `dummyindex/context/build/upgrade.py`
   (new), `dummyindex/context/build/runner.py`,
   `dummyindex/context/domains/atomic_io.py`,
   `tests/fixtures/retired_equipment_evals/` (9 files copied from
   `git show v0.37.0:.context/equipment-evals/<f>`),
   `tests/context/build/test_upgrade.py` (new; `unit`).
   - Move `_MANAGED_GITIGNORE_PATTERNS`, `_MANAGED_GITATTRIBUTES_RULES`, both
     headers, `_ensure_managed_lines`, `ensure_context_gitignore`,
     `ensure_context_gitattributes`, `remove_legacy_enrich_plan`
     (`runner.py:L337-L465`) into `upgrade.py`; re-export from `runner`
     (importers: `cli/enrich.py:15`, `tests/context/build/test_output_hygiene.py:29`,
     `tests/context/build/test_no_cache_leak.py:12`, `tests/export/test_graph_storage.py:79`).
   - Add fail-closed `is_link(path)` to `context/domains/atomic_io.py`
     (lstat; S_ISLNK or reparse attribute; `OSError` ⇒ linked), modelled on
     `installer/ownership.py:_is_link` (`L63-L73`).
   - `RetiredPath`, `RETIRED_CONTEXT_PATHS` (`equipment-evals/` 0.37.0,
     `graph/` 0.6.0), vendored v0.36 starter renderer (header pins
     `v0.36.0:dummyindex/cli/equip/seed.py`, style of
     `installer/legacy_fingerprints.py`) with the v0.36 `Capability`
     name→value map for the enum rendering.
   - `retire_paths(context_dir)`: walker modelled on
     `installer/ownership.py:remove_family` (`L263-L299`) — backup unproven
     files to `_doc_backups/retired/<ver>/` via `write_text_atomic`-style bytes
     copy, delete, rmdir bottom-up, links unlinked not followed.
   - `LayoutMigration` + `migrate_context_layout(context_dir, *, package_version)`
     with per-step `try` (step 4's cache check is called from here).

4. **Extraction-cache version scope** — `dummyindex/pipeline/io/cache.py`,
   `tests/pipeline/io/test_cache.py` (`unit`).
   `scope_cache_to_version(cache_dir, version) -> int` (deleted count):
   stamp file `extraction-version`; deletes only top-level
   `^[0-9a-f]{64}\.json$` on mismatch.

5. **Wire migration into build paths** — `dummyindex/context/build/runner.py`
   (`_write_all` L480-L485 → `migrate_context_layout`; `BuildResult.migration`),
   `dummyindex/cli/enrich.py` (L42-L43 → `migrate_context_layout`),
   `tests/context/build/test_runner.py` (`integration`).

6. **Refresh: migration, stamp-last, required failures, downgrade flag,
   schema** — `dummyindex/context/build/enriched_refresh.py`,
   `dummyindex/context/build/meta.py`, `tests/context/build/test_index_repair.py`
   (`integration`).
   - `migrate_context_layout` replaces `ensure_context_gitattributes` (L110);
     `RefreshResult.migration`, `RefreshResult.failed` (`(artifact, error)`).
   - new `allow_downgrade: bool = False` parameter.
   - reorder per spec contract 5; early `_refresh_meta` drops the version;
     `_advance_version_stamp` uses `compare_versions` and `dataclasses.replace`
     (no extra `updated_at` churn) and writes `schema_version=SCHEMA_VERSION`.
   - `meta.py`: `SCHEMA_VERSION = 2`; `read_meta` accepts ≤ 2; the
     newer-schema `ValueError` message says "upgrade dummyindex".

7. **Install / rebuild / reconcile reporting + flag threading** —
   `dummyindex/installer/install/project_init.py` (L60-L140),
   `dummyindex/installer/install/orchestrate.py` (pass `force_downgrade`),
   `dummyindex/cli/rebuild.py` (L137), `dummyindex/cli/reconcile.py`
   (L158-L163), `tests/test_install.py` (`integration`, next to
   `test_install_auto_init_advances_version_on_curated_index` L2408).
   Print removed (cap 5, "… and N more"), backed-up and error lines, and the
   "version stamp not advanced" warning with cause + fix; reconcile-stamp says
   "upgrade dummyindex" when meta is newer-schema.

8. **Update skill** — `dummyindex/skills/update/SKILL.md` step 4: name the
   "version stamp not advanced" warning as a failure to surface, not a reason
   to re-run step 3. Avoid the literal `schema_version 2`
   (`tests/test_skills_doc_hygiene.py:L176-L193`).

9. **Changelog + full verification** — `CHANGELOG.md` `## Unreleased`
   (`### Fixed`: shard pruning, retired-path cleanup, stamp-last, cache scope;
   `### Changed`: schema 2 — 0.36/0.37 cannot read 0.38+ indexes; superseded
   manifests fail closed). Run `python -m pytest tests/ -q --tb=short` and
   `ruff check dummyindex tests`.

Revision note: folded every BLOCK/HIGH (enum-form suites, plain-branch
contradiction, concurrent-prune race → grace period + live re-read, prune
containment, import cycle, stamp ordering vs PROJECT.md, forced downgrade,
permanent-failure messaging, migration error containment, schema-bump message)
and most MEDIUMs. Deliberately left: `build_all` meta ordering, junction handling
in the installer, cache dead-entry pruning between same-version runs.
