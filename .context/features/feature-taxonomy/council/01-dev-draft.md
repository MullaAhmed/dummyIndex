# Feature taxonomy engine — plan

confidence: INFERRED

## Where it lives

`dummyindex/context/domains/features/` — `builder.py` (graph → scaffolding), `ops.py` (rename/merge/remove_flow/write_section), `placement.py` (scaffold/assign/unassign/remove/clear-pending), `indexes.py` (INDEX.md + graph rebuilders, symbols loader), `render.py` (markdown stubs + `_graph_view`), `docs.py` (per-feature `docs.md`), `models.py` (frozen dataclasses), `constants.py`, `errors.py`, `helpers.py` (atomic writers, slug validation, path/range coercion), `__init__.py` (public re-export surface). CLI bindings in `dummyindex/cli/features.py`; the bundled viewer string in `dummyindex/context/output/viewer.py`. Tests: `tests/context/domains/features/test_features.py`, `tests/context/domains/features/test_placement.py`.

## Architecture in three sentences

A build-time `scaffold_features` pass clusters the call/community graph into per-feature folders once, then a family of atomic CRUD ops lets the council and reconcile procedure reshape that taxonomy in place — deriving `members` from `map/symbols.json` rather than ever re-clustering, and preserving any LLM-enriched `spec.md`/`plan.md`/`concerns.md`. Every op validates fully before its first write (so a rejected op is a no-op) and persists each artifact tmp-file+`replace` for crash/concurrency safety (`helpers.py:131-140`), raising the single typed `FeatureRenameError` that the CLI maps to exit 2. `INDEX.json` is hand-maintained as the canonical machine map; `INDEX.md` + `graph.{json,html}` are regenerated from it/from disk after every mutation so navigation and the HTML viewer never lag.

## Data model

- **`feature.json`** (`Feature.to_dict`, `models.py:69-81`): `schema_version`, `feature_id`, `kind` (`"community"`; `"entry_point_group"` reserved), `name`, `summary`, `members` (symbol ids), `files` (repo-relative POSIX, sorted/unique), `entry_points`, `flow_ids`, `confidence` (`EXTRACTED` deterministic / `INFERRED` enriched).
- **`flows/<id>.json`** (`Flow.to_dict`, `models.py:43-54`): `flow_id`, `feature_id`, `entry_point`+label+path, ordered `steps` (`FlowStep`: depth/node_id/label/path/range), `files`.
- **`INDEX.json`**: `{schema_version, features: [{feature_id, kind, name, summary, member_count, file_count, entry_point_count, flow_count, confidence, path}], flow_count}` — written whole by `builder._write_all` (`builder.py:280-302`) and hand-edited by placement (`_append_index_entry`/`_update_index_counts`/`_drop_index_entry`, `placement.py:489-548`) with no disk-rebuild helper.
- **`graph.json`**: denormalized viewer payload from `_graph_view` (`render.py:157-357`) — folder/file/class/function/method/feature/flow nodes with `parent`/`contains`/`touches` edges.
- **Member derivation** (`_members_for_files`, `placement.py:457-475`): load `<context>/map/symbols.json` (two dirs up from `features/`), select symbol ids whose `path` is in the feature's file set, sorted; tolerates an absent map → empty members. This is the load-bearing "never re-cluster" rule — members follow files, files are the council's hand-curated input.
- **Pending-enrichment marker**: tracked (not gitignored) `.pending-enrichment` file (`constants.py:38`) dropped by scaffold/assign/unassign; `mark-enriched` clears it; `reconcile-stamp` refuses to advance while any remain.

## Key decisions

- **Validate-before-write + atomic persistence.** Mirrors `merge_feature`; combined with tmp-file+`replace` this is the project's "no DB, filesystem store" atomicity discipline (convention `data-access.md`). Repo-relative POSIX paths only, sorted/stable JSON for byte-identical re-runs.
- **Members derived, never re-clustered.** Placement ops recompute members from `symbols.json` over the file union/remainder — clustering happens exactly once at build time.
- **`community-*` ids reserved** (`_RESERVED_ID_PREFIX`, `placement.py:46`) so hand-scaffolded features can't collide with a future Leiden re-cluster; `scaffold-feature` rejects them.
- **Enrichment preserved on mutation.** Assign/unassign/rename touch only `feature.json` + indexes, never the curated section markdown; merge appends prose under sentinels so re-merge never clobbers.
- **Hand-maintained `INDEX.json`.** Placement edits the index in place (no rebuild-from-disk) to keep counts/flow_count authoritative; only `INDEX.md` + `graph` are regenerated.
- **Single typed error → exit 2.** All inconsistent conditions raise `FeatureRenameError`; the CLI is the only I/O/printing boundary.
- **Section-name gating** (`cli/features.py:210-240`): canonical `spec`/`plan`/`concerns` always writable, legacy update-only, others need `--allow-new-section` — prevents stray audit files; merge sections capped to `{"supporting"}` (`constants.py:48`).
- **Parser-artifact filter** (`builder.py:176-198`): all-`__init__.py` communities with no entry points are dropped at scaffold time to avoid noise features.

## Open questions

- `kind` is documented as `"community"` with `"entry_point_group"` reserved (`models.py:60`) but no code path emits the latter — is it still planned?
- `scaffold_feature` hardcodes `kind="community"` even for hand-scaffolded, non-clustered features (`placement.py:90`); the `kind` field no longer distinguishes provenance once a feature is hand-created.
- `write_section`'s docstring claims a warning is "surfaced via the return path's parent existence" for non-canonical names (`ops.py:466-468`), but the actual gating lives in the CLI (`_validate_section_name`); the domain function itself accepts any slug-safe section. The docstring overstates the domain-layer guard — CLI is the real boundary.
