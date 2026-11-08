# Feature taxonomy engine — plan

confidence: INFERRED

## Where it lives

`dummyindex/context/domains/features/` is one self-contained domain. One module per concern:

- `builder.py`: build-time `scaffold_features` (graph to folders, one-shot clustering), `_write_all` (`builder.py:262`), and the parser-artifact filter (`builder.py:200`). Loads the on-disk `seed-rank.json` for the scan seed (`builder.py:179`).
- `ops.py`: taxonomy CRUD on *existing* folders: `rename_feature` (`ops.py:28`), `merge_feature` (`ops.py:162`), `remove_flow` (`ops.py:352`), `write_section` (`ops.py:454`).
- `placement.py`: the reconcile and placement family: `scaffold_feature` (`:49`), `assign_files` (`:128`), `unassign_files` (`:193`), `remove_feature` (`:268`), `clear_pending_enrichment` (`:355`).
- `indexes.py`: `refresh_features_index_md` (`:22`), `rebuild_features_graph` (`:38`), `_load_symbols_map` (`:171`).
- `render.py`: markdown stubs and `_graph_view` (`render.py:166`). `docs.py`: per-feature `docs.md`. `models.py`: frozen dataclasses.
- `communities.py`: the community mid-tier. Frozen `GraphCommunities`, `GraphCommunity`, and `CommunityMember` models. The pure `rollup_communities` roll-up with stable slugs (`communities.py:94,159`).
- `constants.py`, `errors.py`, `helpers.py` (atomic writers, slug and path coercion), `__init__.py` (public re-export surface).

CLI bindings: `dummyindex/cli/features.py` and `dummyindex/cli/scan.py`.

Codebase scan: `dummyindex/context/domains/features/scan/{models,seed,validate,mutate,rank,refs}.py`. `rank.py` loads the `seed-rank.json` shortlist. `refs.py` builds the `symbolRef` resolution index (`REF_ARTIFACTS` registry).

Viewer: `dummyindex/context/output/viewer/{__init__,styles,script,tiers,extras}.py`. `tiers.py` is the tier-2/3 JS, appended into `script.py`'s scope. `extras.py` precomputes the second data island.

Tests: `tests/context/domains/features/{test_features.py,test_placement.py,test_scan.py,test_scan_artifact.py,test_scan_rank.py,test_scan_refs.py,test_communities.py}`, `tests/context/output/test_viewer_extras.py`, `tests/cli/test_scan_check.py`.

## Bounded context

This domain owns **the shape of the feature taxonomy on disk**. That means which folders exist under `.context/features/`, what each `feature.json` claims, and the regenerated INDEX and graph that mirror it.

It does **not** own clustering (see Dependencies).

It does **not** own enriched prose. The council and reconcile procedure author `spec.md`, `plan.md`, and `concerns.md`. This domain only *places* and *preserves* them.

The same split holds for the graph-consumption artifacts. The PageRank computation and the `seed-rank.json` and `graph-communities.json` writes live upstream in `context/build/communities.py`. This domain owns their **models, roll-up logic, and tolerant loaders** (`communities.py`, `scan/rank.py`, `scan/refs.py`).

The boundary is sharp. Every mutation here is a structural edit, never a re-derivation.

## Architecture

- A build-time `scaffold_features` pass clusters the call/community graph into per-feature folders **once**.
- Afterwards, atomic CRUD ops reshape that taxonomy in place.
- The ops derive `members` from `map/symbols.json` and never re-cluster. They preserve LLM-enriched markdown.
- `INDEX.md` and `graph.html` regenerate from disk after every mutation, so navigation and the viewer never lag.
- `graph.json` regenerates only while it is still the deterministic seed. A curated (`INFERRED`) scan is kept verbatim.
- So mutating ops edit the scan in place through `scan/mutate.py`. Otherwise a removed feature would linger on the map forever.

## Two op families (the load-bearing split)

- **`ops.py`: edits existing folders.** `rename`, `merge`, `remove_flow`, and `write_section` assume the feature already exists. They move, rewrite, or append. `merge` is the only op that touches curated prose. It does so only by *appending* under sentinels.
- **`placement.py`: reconciles files and taxonomy.** `scaffold`, `assign`, `unassign`, and `remove` are driven by the set of repo files a feature owns. Members are recomputed from that file set on every call (`_members_for_files`, `placement.py:454`).

Both families share `helpers.py` (atomic writers, slug validation). They raise the same `FeatureRenameError`. The split is *which authority drives the mutation*: a named id (`ops`) or a file set (`placement`).

## Data model

- **`feature.json`** (`Feature.to_dict`, `dummyindex/context/domains/features/models.py:73`):
  - Fields: `schema_version`, `feature_id`, `kind`, `name`, `summary`, `members` (symbol ids), `files`, `entry_points`, `flow_ids`, `confidence`.
  - `kind` is `"community"`, with `"entry_point_group"` reserved.
  - `files` are repo-relative POSIX, sorted and unique.
  - `confidence` is `EXTRACTED` (deterministic) or `INFERRED` (enriched).
- **`flows/<id>.json`** (`Flow.to_dict`, `dummyindex/context/domains/features/models.py:47`): `flow_id`, `feature_id`, `entry_point` plus label and path, ordered `steps` (`FlowStep`: depth/node_id/label/path/range), `files`.
- **`INDEX.json`**: `{schema_version, features: [{feature_id, kind, name, summary, member_count, file_count, entry_point_count, flow_count, confidence, path}], flow_count}`. `builder._write_all` (`builder.py:262`) writes it whole. Placement hand-edits it: `_append_index_entry` (`:489`), `_update_index_counts` (`:512`), and `_drop_index_entry` (`:528`). No disk-rebuild helper exists.
- **`graph.json`**: the curated codebase scan (schema v2), seeded by `_graph_view`, then `seed_scan` (`render.py:166`, `scan/seed.py:95`). Nodes: `entry`, `cron`, `agent`, `model`, `tool`, `service`, `store`, `external`. Edges: `calls`, `reads`, `writes`, `triggers`. Capped at 120 nodes and 240 edges (`constants.py:26-27`).
  - The seed emits one `service` per feature and one `entry` per flow.
  - It collapses cross-feature `calls` from the symbol graph's `calls` and `uses` links, ranked by volume.
  - Flows alone are not enough. Council stage 4 discards most of them. A fully enriched repo can have none left.
  - With a `seed-rank.json` present, selection and ordering are rank-driven. Every seed node carries `evidence: EXTRACTED`, plus a resolving `symbolRef` where one exists.
  - Without it, the seed uses file-count ordering, byte-identical to the pre-rank shape.
- **`seed-rank.json`** (`SeedRank.to_dict`, `scan/rank.py:41`): schema v1, `{schema_version, ranked: [{id, score}]}`. It is the personalized-PageRank shortlist over `symbol-graph.json`, highest score first.
  - Entry order is part of the contract (committed and diffed).
  - Upstream `context/build/communities.py` *writes* it. This domain only *loads* it (`load_seed_rank`, `rank.py:57`), tolerantly.
  - Missing, unreadable, or wrong-shape input loads as `None`. Malformed rows are skipped.
- **`graph-communities.json`** (`GraphCommunities.to_dict`, `communities.py:82`): schema v1, one card per symbol-graph community. Card shape: `{slug, size, feature?, summary?, members: [{id, label, score, path?}]}`.
  - Cards sort by slug. Members sort by rank. Top-10 per card (`COMMUNITY_TOP_K`, `communities.py:34`).
  - The slug is `<dominant-feature>-<top-member>` (`_community_slug`, `:159`). It is never the partition int.
  - Partition ids renumber between runs. The artifact is committed. A renumbered identity would break every `symbolRef` pinned to it.
  - Rationale nodes (`file_type: "rationale"`) are neither members nor size.
  - `context/build/communities.py` writes it, via this domain's `rollup_communities`.
- **Member derivation** (`_members_for_files`, `placement.py:454`): load `<context>/map/symbols.json` (parent of `features/`, plus `map/`). Select symbol ids whose `path` is in the feature's file set, sorted. An absent map gives empty members.
  - This is the load-bearing "never re-cluster" rule.
  - **Members follow files. Files are the council's hand-curated input.**
- **Pending-enrichment marker**: a tracked (not gitignored) `.pending-enrichment` file (`constants.py:81`). Scaffold, assign, and unassign drop it. `mark-enriched` clears it. `reconcile-stamp` refuses to advance while any remain.

## Key decisions

- **Validate-before-write and atomic persistence.** Every op validates fully, then writes each artifact via tmp-file+`replace` (`helpers.py:131-140`). This is the *local* reimplementation of the project-wide `write_text_atomic` shape. Convention `data-access.md` names the canonical helper at `atomic_io.py:11-24`. Paths are repo-relative POSIX only. JSON is sorted and stable, for byte-identical re-runs.
- **Members derived, never re-clustered.** Placement recomputes members from `symbols.json` over the file union or remainder. Clustering happens exactly once, at build time, in `scaffold_features`.
- **`community-*` ids reserved** (`_RESERVED_ID_PREFIX`, checked in `_validate_placement_id`, `placement.py:395`). Hand-scaffolded features cannot collide with a future Leiden re-cluster. `scaffold-feature` rejects them.
- **Enrichment preserved on mutation.** Assign, unassign, and rename touch only `feature.json` and indexes, never curated section markdown. Merge appends prose under sentinels, so re-merge never clobbers.
- **Hand-maintained `INDEX.json`.** Placement edits the index in place, with no rebuild from disk. That keeps counts and `flow_count` authoritative. Only `INDEX.md` and `graph` regenerate from disk.
- **Single typed error, exit 2.** All inconsistent conditions raise `FeatureRenameError` (`errors.py:5`). The CLI (`cli/features.py`) is the only I/O and printing boundary.
- **Section-name gating lives in the CLI, not the domain.** `_CANONICAL_SECTIONS = {"spec","plan","concerns"}` (`cli/features.py:19`) is always writable. Legacy names are update-only. Other names need `--allow-new-section` (`_validate_section_name`, `cli/features.py:210`).
  - The domain `write_section` (`ops.py:454`) accepts any slug-safe section.
  - The guard is CLI-only by design (see Open questions).
  - Merge sections are capped to `{"supporting"}` (`constants.py:91`).
- **Parser-artifact filter** (`_is_parser_artifact`, `builder.py:200`). All-`__init__.py` communities with no entry points are dropped at scaffold time, to avoid noise features.
- **The rank is read from disk, never recomputed.** Both regeneration paths load the same committed `seed-rank.json`: `scaffold_features` (`builder.py:179`) and `rebuild_features_graph` (`indexes.py:118`). Two sources for one fact is how the paths would drift.
  - Degradation is deliberate. No artifact means `None`, and the pre-rank file-count ordering, byte for byte.
- **Stable community slugs, never partition ints.** `rollup_communities` drops `analysis.cluster`'s integer partition ids (`communities.py:94`). Identity comes from what the community contains: dominant feature plus top member. Guarded by `test_communities.py::test_rollup_is_identical_across_partition_renumbering`.
- **Violation severity split** (`ScanViolationSeverity`, `dummyindex/context/enums.py:93`). `ERROR` flips `scan-check`'s exit code.
  - `WARNING` means a check *could not run*: a `symbolRef` has no extraction artifact on disk to resolve against.
  - The scan is unverifiable there, not wrong. Warnings print but never fail (`cli/scan.py:68-70`).
- **Viewer extras are bounded and cycle-free.** `viewer/extras.py` is deliberately stdlib-only, with duplicated tolerant loaders (canonical twins noted in-module).
  - `domains/features` imports `render_viewer_html`. Importing `domains.features.*` back from the viewer would form a cycle.
  - The tier-3 expansion index is hard-capped at 300 KiB serialized (`EXPANSION_BUDGET_BYTES`, `extras.py:40`). It truncates whole rank-ordered entries.
  - The ~11MB symbol graph is never inlined.

## Dependencies

**Upstream (this domain consumes):**

- `map/symbols.json`: the symbol map from the deterministic build (`build/maps.py`). Member derivation reads it two dirs up from `features/` (`_load_symbols_map` call sites, `placement.py:463,587`). It tolerates absence.
- The graph-consumption artifacts under `features/`: `seed-rank.json`, `graph-communities.json`, `symbol-graph.json`.
  - Upstream `context/build/communities.py` and `build/graph.py` write them.
  - This domain reads them tolerantly and read-only: `scan/rank.py:57` (seed ordering), `scan/refs.py:81` (`symbolRef` resolution), `viewer/extras.py:188` (tier-2/3 island).
  - Every loader degrades to "no signal" on a missing or unreadable artifact.
- The call/community **graph** passed into `scaffold_features(graph_data, …)` (`builder.py:45`), the build-time clustering input. After scaffold, this domain never re-reads it.
- Convention `data-access.md`: atomic write, schema version, sorted JSON. `helpers.py` is a downstream reimplementation of `atomic_io.write_text_atomic`.

**Downstream (consumes this domain):**

- `cli/features.py` is the primary caller of the public surface (`__init__.py:67-91`). It maps `FeatureRenameError` to exit 2 and owns all printing and I/O. `cli/scan.py` binds the scan sub-package directly (`validate_scan` and `load_symbol_ref_index`).
- The **reconcile procedure** (skill `65-reconcile.md`) and the **council** drive scaffold, assign, unassign, merge, and rename. They fold reconciled deltas into the taxonomy. `reconcile-stamp` gates on the `.pending-enrichment` markers this domain drops.
- `context/build/communities.py` imports `rollup_communities` and `GRAPH_COMMUNITIES_FILENAME` from this domain (`communities.py`). It also imports `scan/rank.py`'s `SeedRank`, `RankEntry`, and `SEED_RANK_FILENAME`, to *write* the artifacts the domain later loads.
- The **HTML viewer** (`output/viewer/`) consumes `graph.json`. When `render_viewer_html(scan, features_dir=…)` gets the dir, it also reads the on-disk `graph-communities.json`, `symbol-graph.json`, and `seed-rank.json`.
  - `extras.py` reads them at render time. It never imports them.
  - The emitted file stays self-contained, with no server and no network. The extras inline as a second bounded data island.
  - So a scan never leaks more of a private codebase than the 300 KiB expansion budget admits.

**Cycles:** none. Within the domain, the dependency runs `helpers → models → {ops, placement, indexes, render, builder} → __init__`. The two op families are siblings. No `ops ↔ placement` call edge exists. They share only `helpers`, `models`, and `errors`.

All outward reads are read-only. `viewer/extras.py` stays stdlib-only, to keep the `domains/features → output/viewer` import edge one-directional.

## Open questions

- `kind` is documented as `"community"`, with `"entry_point_group"` reserved (`dummyindex/context/domains/features/models.py:64`). No code path emits the latter.
  - `scaffold_feature` hardcodes `kind="community"` even for hand-scaffolded, non-clustered features (`placement.py:90`).
  - So `kind` no longer distinguishes provenance once a feature is hand-created.
  - Is the reserved value still planned, or should hand-scaffolded features carry a distinct kind?
- `write_section`'s docstring claims a warning is "surfaced via the return path's parent existence" for non-canonical names (`ops.py:466-468`).
  - The actual gating lives in the CLI (`_validate_section_name`, `cli/features.py:210`). The domain function accepts any slug-safe section.
  - The docstring overstates the domain-layer guard. **Decision promoted above: the CLI is the real boundary.**
  - The docstring should be corrected to match.
