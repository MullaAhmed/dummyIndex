# Checklist — Upgrade hygiene: prune orphan graph shards, versioned retired-artifact migration on the install refresh path, stamp meta last and never downgrade, graph-format schema marker

> Derived from the revised plan + spec Acceptance. Code + tests only; no
> direct `.context/` edits. Tick `- [x]` only after the named test passes.

## Wave 1 — independent foundations

- [x] T1 Neutral comparator: `dummyindex/versioning.py` (`parse_version`, `compare_versions` → `VersionOrder`), aliases in `dummyindex/installer/common.py`, `tests/test_versioning.py` (alias parity on `None`/`""`/`v0.37.0`/`0.38.0.dev1`; `compare_versions("0.36.0","0.37.0") == "older"`)
- [x] T2 Shard pruning + reader hardening in `dummyindex/export/storage.py` (`shard_names`, `_is_linked`, `_prune_shards`, grace 600 s, utime reuse, corrupt-shard rewrite, missing-shard `GraphStorageError`), repoint `dummyindex/context/domains/evolve_native_snapshot.py`, tests in `tests/export/test_graph_storage.py` covering every "Shards:" acceptance item
- [x] T4 Extraction-cache version scope: `scope_cache_to_version` in `dummyindex/pipeline/io/cache.py`, tests in `tests/pipeline/io/test_cache.py` (mismatch wipes only hash entries, keeps `manifest.json`; same version keeps entries)

## Wave 2 — migration module

- [x] T3 `dummyindex/context/build/upgrade.py`: move managed gitignore/gitattributes/legacy-plan helpers from `dummyindex/context/build/runner.py` (re-exported), `is_link` in `dummyindex/context/domains/atomic_io.py`, `RETIRED_CONTEXT_PATHS` (`equipment-evals/`, `graph/`), vendored v0.36 starter renderer (plain + enum forms), `retire_paths`, `LayoutMigration`, `migrate_context_layout`; fixtures `tests/fixtures/retired_equipment_evals/` (9 files from `git show v0.37.0:.context/equipment-evals/<f>`); tests `tests/context/build/test_upgrade.py` covering every "Retire:" acceptance item and the per-step error containment

## Wave 3 — wire into build paths

- [x] T5 `dummyindex/context/build/runner.py` `_write_all` → `migrate_context_layout`, `BuildResult.migration`; `dummyindex/cli/enrich.py` → `migrate_context_layout`; test in `tests/context/build/test_runner.py` (seeded legacy state migrated by `build_all`)
- [x] T6 `dummyindex/context/build/enriched_refresh.py` (migration, `failed` as `(artifact, error)`, `allow_downgrade`, reorder, `_advance_version_stamp` with `dataclasses.replace` + schema 2) and `dummyindex/context/build/meta.py` (`SCHEMA_VERSION = 2`, accepts ≤ 2, "upgrade dummyindex" message); tests in `tests/context/build/test_index_repair.py` covering every "Stamp:", "Schema:" (meta part) and "Migration:" refresh item

## Wave 4 — surfaces

- [x] T7 Reporting + flag threading: `dummyindex/installer/install/project_init.py`, `dummyindex/installer/install/orchestrate.py` (`force_downgrade` → `allow_downgrade`), `dummyindex/cli/rebuild.py`, `dummyindex/cli/reconcile.py` (newer-schema → "upgrade dummyindex"); test in `tests/test_install.py` per the "Install:" acceptance item plus the reconcile-stamp schema-3 message
- [x] T8 `dummyindex/skills/update/SKILL.md` step 4 names "version stamp not advanced" as a surfaced failure (no literal `schema_version 2`); `tests/test_skills_doc_hygiene.py` passes

## Wave 5 — changelog + acceptance

- [x] T9 `CHANGELOG.md` `## Unreleased` entries (Fixed: shard pruning, retired-path cleanup, stamp-last, cache scope; Changed: schema 2 lock-out of 0.36/0.37, superseded manifests fail closed)
- [x] Acceptance: `python -m pytest tests/ -q --tb=short` passes (3.10 + 3.12 behaviour; enum-form suite fixtures included)
- [x] Acceptance: `ruff check dummyindex tests` passes
- [x] Acceptance: `git diff --stat -- .context/` shows no hand edits from this build outside `.context/proposals/upgrade-hygiene/`
