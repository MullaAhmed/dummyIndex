# Feature taxonomy engine — plan

confidence: INFERRED

## Where it lives

`dummyindex/context/domains/features/` — a single, self-contained domain. One module per concern:

- `builder.py` — build-time `scaffold_features` (graph → folders, one-shot clustering) + `_write_all` (`builder.py:237`) + parser-artifact filter (`builder.py:176`).
- `ops.py` — taxonomy CRUD that touches *existing* folders: `rename_feature` (`ops.py:28`), `merge_feature` (`ops.py:162`), `remove_flow` (`ops.py:352`), `write_section` (`ops.py:454`).
- `placement.py` — the reconcile/placement family: `scaffold_feature` (`:49`), `assign_files` (`:128`), `unassign_files` (`:193`), `remove_feature` (`:268`), `clear_pending_enrichment` (`:355`), plus member derivation + INDEX.json hand-edits (see Data model).
- `indexes.py` — `refresh_features_index_md` (`:19`), `rebuild_features_graph` (`:34`), `_load_symbols_map` (`:109`).
- `render.py` — markdown stubs + `_graph_view` (`render.py:157`). `docs.py` — per-feature `docs.md`. `models.py` — frozen dataclasses. `constants.py`, `errors.py`, `helpers.py` (atomic writers, slug/path coercion), `__init__.py` (public re-export surface).

CLI bindings: `dummyindex/cli/features.py`, `dummyindex/cli/scan.py`. Codebase scan: `dummyindex/context/domains/features/scan/{models,seed,validate,mutate}.py`. Viewer: `dummyindex/context/output/viewer/{__init__,styles,script}.py`. Tests: `tests/context/domains/features/{test_features.py,test_placement.py,test_scan.py,test_scan_artifact.py}`, `tests/cli/test_scan_check.py`.

## Bounded context

This domain owns **the shape of the feature taxonomy on disk** — what folders exist under `.context/features/`, what each `feature.json` claims, and the regenerated INDEX/graph that mirror it. It does **not** own clustering (that is the upstream graph build — see Dependencies), and it does **not** own enriched prose (the council/reconcile procedure authors `spec.md`/`plan.md`/`concerns.md`; this domain only *places* and *preserves* them). The boundary is sharp: every mutation here is a structural edit to the taxonomy, never a re-derivation of it.

## Architecture in three sentences

A build-time `scaffold_features` pass clusters the call/community graph into per-feature folders **once**; thereafter a family of atomic CRUD ops lets the council and reconcile procedure reshape that taxonomy in place — deriving `members` from `map/symbols.json` rather than ever re-clustering, and preserving any LLM-enriched markdown. Every op validates fully before its first write (so a rejected op is a no-op) and persists each artifact tmp-file+`replace` for crash/concurrency safety (`helpers.py:131-140`), raising the single typed `FeatureRenameError` (`errors.py:5`) that the CLI maps to exit 2. `INDEX.json` is hand-maintained as the canonical machine map; `INDEX.md` + `graph.html` are regenerated from disk after every mutation so navigation and the viewer never lag. `graph.json` is the exception with teeth: it is regenerated only while it is still the deterministic seed, and a curated (`INFERRED`) scan is preserved verbatim — so the mutating ops edit it in place through `scan/mutate.py` instead, or a removed feature would linger on the map forever.

## Two op families (the load-bearing split)

- **`ops.py` — edits existing folders.** `rename`/`merge`/`remove_flow`/`write_section` assume the feature already exists; they move/rewrite/append. `merge` is the only op that touches curated prose, and only by *appending* under sentinels.
- **`placement.py` — reconciles files ↔ taxonomy.** `scaffold`/`assign`/`unassign`/`remove` are driven by the set of repo files a feature owns; members are recomputed from that file set on every call (`_members_for_files`, `placement.py:457`). This family owns the INDEX.json hand-edits.

Both families share `helpers.py` (atomic writers, slug validation) and raise the same `FeatureRenameError`. The split is *which authority drives the mutation* — a named id (`ops`) vs. a file set (`placement`).

## Data model

- **`feature.json`** (`Feature.to_dict`, `dummyindex/context/domains/features/models.py:73`): `schema_version`, `feature_id`, `kind` (`"community"`; `"entry_point_group"` reserved), `name`, `summary`, `members` (symbol ids), `files` (repo-relative POSIX, sorted/unique), `entry_points`, `flow_ids`, `confidence` (`EXTRACTED` deterministic / `INFERRED` enriched).
- **`flows/<id>.json`** (`Flow.to_dict`, `dummyindex/context/domains/features/models.py:47`): `flow_id`, `feature_id`, `entry_point`+label+path, ordered `steps` (`FlowStep`: depth/node_id/label/path/range), `files`.
- **`INDEX.json`**: `{schema_version, features: [{feature_id, kind, name, summary, member_count, file_count, entry_point_count, flow_count, confidence, path}], flow_count}` — written whole by `builder._write_all` (`builder.py:237`) and hand-edited by placement (`_append_index_entry` `:489` / `_update_index_counts` `:512` / `_drop_index_entry` `:528`) with no disk-rebuild helper.
- **`graph.json`**: the curated codebase scan (schema v2), seeded by `_graph_view` → `seed_scan` (`render.py:166`, `scan/seed.py:93`) — `entry`/`cron`/`agent`/`model`/`tool`/`service`/`store`/`external` nodes with `calls`/`reads`/`writes`/`triggers` edges, capped at 60/120. The seed emits one `service` per feature, one `entry` per flow, and cross-feature `calls` collapsed from the symbol graph's `calls`/`uses` links ranked by volume — flows alone are not enough, since council stage 4 discards most of them and a fully enriched repo can have none left.
- **Member derivation** (`_members_for_files`, `placement.py:457`): load `<context>/map/symbols.json` (parent-of-`features/` + `map/`), select symbol ids whose `path` is in the feature's file set, sorted; tolerates an absent map → empty members. This is the load-bearing "never re-cluster" rule — **members follow files; files are the council's hand-curated input.**
- **Pending-enrichment marker**: tracked (not gitignored) `.pending-enrichment` file (`constants.py:38`) dropped by scaffold/assign/unassign; `mark-enriched` clears it; `reconcile-stamp` refuses to advance while any remain.

## Key decisions

- **Validate-before-write + atomic persistence.** Every op validates fully, then writes each artifact tmp-file+`replace` (`helpers.py:131-140`). This is the *local* reimplementation of the project-wide `write_text_atomic` shape (convention `data-access.md`: canonical helper at `atomic_io.py:11-24`) — repo-relative POSIX paths only, sorted/stable JSON for byte-identical re-runs.
- **Members derived, never re-clustered.** Placement recomputes members from `symbols.json` over the file union/remainder; clustering happens exactly once at build time in `scaffold_features`.
- **`community-*` ids reserved** (`_RESERVED_ID_PREFIX`, checked in `_validate_placement_id`, `placement.py:395`) so hand-scaffolded features can't collide with a future Leiden re-cluster; `scaffold-feature` rejects them.
- **Enrichment preserved on mutation.** Assign/unassign/rename touch only `feature.json` + indexes, never the curated section markdown; merge appends prose under sentinels so re-merge never clobbers.
- **Hand-maintained `INDEX.json`.** Placement edits the index in place (no rebuild-from-disk) to keep counts/`flow_count` authoritative; only `INDEX.md` + `graph` are regenerated from disk.
- **Single typed error → exit 2.** All inconsistent conditions raise `FeatureRenameError` (`errors.py:5`); the CLI (`cli/features.py`) is the only I/O/printing boundary.
- **Section-name gating lives in the CLI, not the domain.** `_CANONICAL_SECTIONS = {"spec","plan","concerns"}` (`cli/features.py:19`) always writable; legacy names update-only; others need `--allow-new-section` (`_validate_section_name`, `cli/features.py:210`). The domain `write_section` (`ops.py:454`) accepts any slug-safe section — the guard is CLI-only by design (see Open questions). Merge sections capped to `{"supporting"}` (`constants.py:48`).
- **Parser-artifact filter** (`_is_parser_artifact`, `builder.py:176`): all-`__init__.py` communities with no entry points are dropped at scaffold time to avoid noise features.

## Dependencies

**Upstream (this domain consumes):**
- `map/symbols.json` — the symbol map produced by the deterministic build (`build/maps.py`). Member derivation (`placement.py:457`) and graph class/method nodes (`indexes.py:100`) both read it two dirs up from `features/`; both tolerate its absence. **This is the only cross-domain read** and it is read-only.
- The call/community **graph** passed into `scaffold_features(graph_data, …)` (`builder.py:35`) — the build-time clustering input. After scaffold, this domain never re-reads it.
- Convention `data-access.md` — the atomic-write + schema-version + sorted-JSON discipline; `helpers.py` is a downstream reimplementation of `atomic_io.write_text_atomic`.

**Downstream (consumes this domain):**
- `cli/features.py` — the sole caller of the public surface (`__init__.py:66-90`); maps `FeatureRenameError` → exit 2 and owns all printing/I/O.
- The **reconcile procedure** (skill `65-reconcile.md`) and the **council** — drive scaffold/assign/unassign/merge/rename to fold reconciled deltas into the taxonomy; `reconcile-stamp` gates on the `.pending-enrichment` markers this domain drops.
- The **HTML viewer** (`output/viewer/`) — consumes `graph.json` only; no code coupling, pure data contract. `render_viewer_html(scan)` inlines the payload so the emitted file is self-contained (no server, no network), which also means a scan never leaks what a private codebase is built from.

**Cycles:** none. Within the domain the dependency runs `helpers → models → {ops, placement, indexes, render, builder} → __init__`; the two op families are siblings (no `ops ↔ placement` call edge) sharing only `helpers`/`models`/`errors`. The single outward edge (`symbols.json`) is read-only, so there is no cross-domain cycle.

## Open questions

- `kind` is documented as `"community"` with `"entry_point_group"` reserved (`dummyindex/context/domains/features/models.py:64`) but no code path emits the latter, and `scaffold_feature` hardcodes `kind="community"` even for hand-scaffolded, non-clustered features (`placement.py:90`). So `kind` no longer distinguishes provenance once a feature is hand-created — is the reserved value still planned, or should hand-scaffolded features carry a distinct kind?
- `write_section`'s docstring claims a warning is "surfaced via the return path's parent existence" for non-canonical names (`ops.py:466-468`), but the actual gating lives in the CLI (`_validate_section_name`, `cli/features.py:210`); the domain function accepts any slug-safe section. The docstring overstates the domain-layer guard — **decision promoted above: the CLI is the real boundary** — but the docstring should be corrected to match.
