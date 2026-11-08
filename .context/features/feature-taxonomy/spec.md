# Feature taxonomy engine — spec

confidence: INFERRED

## Intent

The `context/domains/features/` domain is the curated **feature taxonomy** layer of `.context/`. It turns the deterministic call/community graph into per-feature folders (`.context/features/<id>/`).

It offers atomic, idempotent CRUD ops for the `/dummyindex` council and reconcile procedure: rename, merge, scaffold, assign, unassign, remove.

The ops never re-cluster. They never clobber LLM-enriched prose. Members are re-derived from `map/symbols.json`.

Artifacts are written tmp-file+`replace`, so readers never see half-written files (`helpers.py:131-140`). Every op validates fully before its first write. A rejected op leaves the tree byte-identical.

The domain also owns the **codebase scan** (`features/graph.json`, schema v2) and its self-contained three-tier viewer (`context/output/viewer/`). The viewer answers "how does this repo work, and how does it use AI?" for humans.

It also owns the tolerant loaders for the graph-consumption artifacts: `seed-rank.json` (`scan/rank.py`), `graph-communities.json` (`communities.py`), and `symbolRef` resolution (`scan/refs.py`).

## User-visible behavior

Ops run as `dummyindex context <cmd>` (CLI layer `dummyindex/cli/features.py`), on `<root>/.context/features/`.

The CLI maps domain `FeatureRenameError` to exit 2. On success, each op prints a one-line summary.

- **features-rename** (`run_rename`, `cli/features.py:33-117`): moves `features/<from>/` to `features/<to>/`. Rewrites `feature_id`, `name`, and `summary` in `feature.json`. Rewrites `feature_id` in every `flows/*.json`. Updates the matching `INDEX.json`, `INDEX.md`, and `graph.json` entries. Idempotent when `from == to` (metadata refresh only). Setting `--name` or `--summary` flips confidence to `INFERRED`.
- **features-merge** (`run_merge`, `cli/features.py:119-167`): absorbs a trivial feature `--from` into `--into` as a section. Default and only section: `supporting`. Appends the source `spec.md` prose into `<into>/supporting.md`, wrapped in sentinels. Re-merge appends, never clobbers. Unions `members`, `files`, and `entry_points` into the target `feature.json`. Deletes the source folder. Drops it from `INDEX.json` and `graph.json`. Auto-logs a stage-0 architect entry to the target council log. Rejects self-merge and unknown sections.
- **scaffold-feature** (`run_scaffold`, `cli/features.py:300-348`): creates a brand-new `features/<id>/` for net-new `--file`s. Writes `feature.json` (members from symbols, `confidence: EXTRACTED`). Writes a deterministic `spec.md` stub, a `.pending-enrichment` marker, and optional `docs.md`. Appends an `INDEX.json` entry. Regenerates `INDEX.md` and `graph.{json,html}`. Rejects an existing id or a reserved `community-*` id. Rejects a call with no files. Rejects a file missing or outside the repo.
- **assign-files** / **unassign-files** (`run_assign_files`/`run_unassign_files`, `cli/features.py:351-439`): adds or removes `--file`s on an existing feature. Recomputes members over the surviving file set. Updates INDEX counts. Re-drops the pending marker. **Preserves** enriched `spec.md`, `plan.md`, and `concerns.md`. Assign is idempotent on already-owned files. Unassign tolerates deleted paths. Unassign refuses to strand an empty feature.
- **features-remove** (`run_remove`, `cli/features.py:442-483`): deletes a dead feature's folder and INDEX entry. Decrements top-level `flow_count`. Refuses while the feature still owns on-disk files or its `feature.json` is corrupt, unless `--force` is set.
- **mark-enriched** (`run_mark_enriched`, `cli/features.py:486-527`): clears a feature's `.pending-enrichment` marker. Idempotent: a no-op when the marker is absent.
- **section-write** (`run_section_write`, `cli/features.py:243-297`): atomically places a markdown file into `features/<id>/<section>.md`. Canonical sections `spec`, `plan`, and `concerns` are always writable. Legacy names are update-only. Other names need `--allow-new-section`.
- **flow-remove** (`run_flow_remove`, `cli/features.py:169-208`): deletes a noise flow's `flows/<id>.{json,md}`. Prunes it from `feature.json`, `INDEX.json`, and `graph.json`.
- **INDEX + scan artifacts**: `INDEX.json` is the canonical agent-readable feature list. `INDEX.md` is the rendered table. `graph.json` is the **curated codebase scan**. `graph.html` is its viewer. It opens over `file://` with data inlined: no server, no network.

The viewer has **three tiers**:

- Tier 1 is the curated map.
- Tier 2 is a community overview: one supernode per `graph-communities.json` card. Cross-community call volume is the edge weight. The `Communities` button and `C` key open it. It is hidden entirely when the artifact is absent.
- Tier 3 is focus and expand. Selecting a curated node whose `symbolRef` resolves reveals its top-k symbol-graph neighbors. They appear as read-only "ghost" annotations with `path:line` citations, from a bounded index precomputed at render time (`viewer/extras.py`).

All three tiers ship in one self-contained file, via a second `graph-extras` data island. When the extras artifacts are absent, the placeholder stays. The viewer then degrades to the plain curated map.

- **scan-check** (`cli/scan.py:25`): validates `graph.json` against the schema-v2 contract. It reports **every** violation in one pass, each with a JSON path.
  - It resolves each node's `symbolRef` against the extraction artifacts on disk (`load_symbol_ref_index`, `scan/refs.py:81`).
  - An unresolvable ref is a `symbol_ref_unresolved` error.
  - Refs with **no** artifact present to check against collapse into one aggregate warning, `symbol_ref_unchecked`.
  - Exit `0` means clean. Warnings print but are never fatal. Exit `1` means error-severity violations. Exit `2` means nothing to check.

### The scan is seeded, then curated

`graph.json` follows the two-stage contract of `spec.md`.

- **Seed** (`scan/seed.py:95`): written at ingest, `confidence: EXTRACTED`. One `service` node per feature and one `entry` per flow. Cross-feature `calls` edges collapse from the symbol graph `calls` and `uses` links, ranked by call volume.
  - When `features/seed-rank.json` exists, the seed consumes it: personalized PageRank over the symbol graph, written by `context/build/communities.py`.
  - `load_seed_rank` (`scan/rank.py:57`) reads it. Features are selected and ordered by summed member rank (`_feature_sort_key`, `seed.py:160`). Entry flows sort by their entry point's rank (`_entry_sort_key`, `seed.py:233`).
  - Every emitted node carries `evidence: EXTRACTED`. Where a member resolves, the node also carries a `symbolRef` (`_top_member_ref`, `seed.py:177`).
  - Without the artifact, the seed falls back to file-count ordering. That output is byte-identical to the pre-rank shape, with no `evidence` or `symbolRef` fields.
  - Output is deterministic and byte-reproducible. `project.date` stays unset on purpose, so a rebuild creates no git noise.
  - The seed knows code shape, not meaning. It cannot see the AI surface.
- **Curated**: the `council/58-codebase-scan.md` stage rewrites it against real source and flips `confidence` to `INFERRED`.
- **Preserved**: `rebuild_features_graph` regenerates an `EXTRACTED` scan. It leaves an `INFERRED` scan verbatim (`_curated_scan`, `indexes.py:146`).
  - The check keys on confidence **alone, not validity**. A curated map cannot be re-derived.
  - A cap violation means run `scan-check`. It never means delete the map.

Caps are the feature. Limits are ≤ 120 nodes and 240 edges (`MAX_SCAN_NODES`/`MAX_SCAN_EDGES`, `constants.py:26-27`). The graph-consumption upgrade doubled them from 60/120. The ranked seed aims at 40-80 nodes. The hard cap leaves the council headroom to promote the AI surface without cutting business logic.

Node kinds: `entry cron agent model tool service store external`. Edge kinds: `calls reads writes triggers`. Node `symbolRef` text is capped at 120 (`MAX_NODE_SYMBOL_REF`, `constants.py:42`).

v1 denormalized the whole extraction into this file: folder, file, class, method, feature, flow. That was about 4k nodes and 8k edges on this repo. Per-symbol navigation did not move. It lives in `map/symbols.json` and `features/symbol-graph.json`, which agents query.

## Contracts

Public surface re-exported from `dummyindex/context/domains/features/__init__.py:67-91`.

- `scaffold_features(context_dir, graph_data, *, root=None, flow_depth=_DEFAULT_FLOW_DEPTH, doc_catalog=None) -> ScaffoldResult`: `builder.py:45`. Build-time scaffolder with two deterministic passes: Leiden communities become features, and in-degree-0 call nodes become BFS flows.
  - Drops parser-artifact `__init__.py`-only communities (`_is_parser_artifact`, `builder.py:200`).
  - Reads the on-disk ranked shortlist (`load_seed_rank`, `builder.py:179`), so scaffold and rebuild cannot drift.
- `rename_feature(features_dir, *, from_id, to_id, new_name=None, new_summary=None) -> RenameResult`: `ops.py:28-157`.
- `merge_feature(features_dir, *, from_id, into_id, as_section, note=None) -> MergeResult`: `ops.py:162-349`.
- `remove_flow(features_dir, *, feature_id, flow_id) -> RenameResult`: `ops.py:352-452`.
- `write_section(features_dir, *, feature_id, section, source_file) -> Path`: `ops.py:454-492`.
- `scaffold_feature(features_dir, *, repo_root, feature_id, name, files, summary=None) -> PlacementResult`: `placement.py:49-125`.
- `assign_files(features_dir, *, repo_root, feature_id, files) -> PlacementResult`: `placement.py:128-190`.
- `unassign_files(features_dir, *, repo_root, feature_id, files) -> PlacementResult`: `placement.py:193-265`.
- `remove_feature(features_dir, *, feature_id, repo_root, force=False) -> RemoveResult`: `placement.py:268-324`.
- `clear_pending_enrichment(features_dir, feature_id) -> Optional[str]`: `placement.py:355-378`.
- `refresh_features_index_md(features_dir) -> Path`: `indexes.py:22`. `rebuild_features_graph(features_dir) -> tuple[Path, Path]`: `indexes.py:38`.
  - Loads the same on-disk `seed-rank.json` the scaffolder consumed (`indexes.py:118`). That keeps both regeneration paths byte-identical.
- `_graph_view(features, flows, *, project_name, slug=None, links=(), rank=None) -> dict`: `render.py:166`. Thin wrapper over `seed_scan`.
- `seed_scan(features, flows, *, project_name, slug, links=(), rank=None, max_nodes, max_edges) -> Scan`: `scan/seed.py:95`. `slugify`: `scan/seed.py:47`.
- `load_seed_rank(features_dir) -> SeedRank | None`: `scan/rank.py:57`. Frozen `SeedRank` and `RankEntry` (`rank.py:41,30`).
  - Reads `features/seed-rank.json` (schema v1, written beside the symbol graph by `context/build/communities.py`).
  - Missing, unreadable, or malformed input loads as `None`, never a failed seed. Malformed rows are skipped, not fatal.
- `load_symbol_ref_index(features_dir) -> SymbolRefIndex | None`: `scan/refs.py:81`. Frozen `SymbolRefIndex(ids, sources)` with `.resolves(ref)` (`refs.py:71`).
  - Walks the `REF_ARTIFACTS` registry (`refs.py:64`): `symbol-graph.json` node ids and `graph-communities.json` community slugs.
  - Adding an artifact takes one registry entry and nothing else.
  - Returns `None` when no registered artifact is readable. The caller then degrades the check to a warning.
- `rollup_communities(node_by_id, communities, scores, *, owner_of_symbol=None, rationale_of=None, root=None, top_k=COMMUNITY_TOP_K) -> GraphCommunities`: `communities.py:94`.
  - Pure roll-up of `analysis.cluster`'s `{int: [node_ids]}` partition into `features/graph-communities.json` cards. Frozen types: `GraphCommunities`, `GraphCommunity`, `CommunityMember` (`communities.py:82,62,46`).
  - Each card has a **stable slug**: `<dominant-feature>-<top-member>` (`_community_slug`, `:159`). The slug never uses the raw partition int, which renumbers between runs.
  - Each card holds size, the top-10 members by PageRank with `path:line` citations, the plurality-owner feature, and a docstring-lifted one-line summary.
  - Colliding slugs get deterministic ordinals (`_dedupe_slugs`, `:205`). Rationale nodes are neither members nor size.
- `validate_scan(payload, *, symbol_refs=None) -> tuple[ScanViolation, ...]`: `scan/validate.py:93`. `ScanViolation(code, path, message, severity=ERROR)`: `scan/validate.py:77`.
  - Pure: returns violations, raises nothing.
  - `severity` is `ScanViolationSeverity` (`context/enums.py:93`). `ERROR` breaks the exit code. `WARNING` marks a check that could not run.
  - With `symbol_refs=None`, present `symbolRef`s become one aggregate warning, `symbol_ref_unchecked`. They are not resolved. A scan without refs emits no warning at all.
- `rename_node` / `drop_nodes` / `drop_feature`: `scan/mutate.py:48,91,109`. Each returns a **new** payload, or `None` when nothing matched, so `ops._rewrite_scan` (`ops.py:34`) can skip the write.
  - The ops edit the scan in place, not by rebuilding it. A rebuild would *preserve* a curated scan, leaving the removed feature on the map forever.
- Frozen scan models `Scan`/`ScanNode`/`ScanEdge`/`ScanChip`/`ScanProject`/`ScanStats`: `scan/models.py`. Optional fields are omitted from the wire shape, not emitted as `null`. `source_ref` maps to `sourceRef`. `from_id` and `to_id` map to `from` and `to`.
  - `ScanNode` has two optional graph-consumption fields (`scan/models.py:83-84`).
  - `symbol_ref` (wire `symbolRef`) pins the box to the extraction layer: a `symbol-graph.json` node id or a `graph-communities.json` community slug.
  - `evidence` is a `ScanEvidence` value (`context/enums.py:74`). `EXTRACTED` means the node survived the seed verbatim. `INFERRED` means the authoring stage added or reshaped it.
  - `evidence` deliberately is not `pipeline.enums.ConfidenceLevel`. That enum grades whole artifacts and has a third member the wire format forbids.
  - Both fields are optional, so pre-extension scans stay valid.
- `render_viewer_html(scan, *, features_dir=None) -> str`: `context/output/viewer/__init__.py:98`. Template `VIEWER_HTML` lives in the same module, split across `viewer/styles.py`, `viewer/script.py`, and `viewer/tiers.py`.
  - With `features_dir`, the tier-2 and tier-3 extras come from the on-disk artifacts and inline as a second `graph-extras` data island.
  - Without it, or when the artifacts are absent, the empty placeholder stays. Tiers 2 and 3 lie dormant.
- `build_viewer_extras(scan, cards_payload, graph_payload, rank_payload, *, root=None, top_k=8, budget_bytes=300*1024) -> ViewerExtras`: `viewer/extras.py:154` (pure). `load_viewer_extras(scan, features_dir) -> ViewerExtras`: `extras.py:188` (file I/O).
  - Tier 3's expansion index maps each resolving `symbolRef` to its top-`EXPANSION_TOP_K` (8) symbol-graph neighbors, ranked by seed PageRank.
  - The serialized index is hard-capped at `EXPANSION_BUDGET_BYTES` (300 KiB, `extras.py:39-40`), measured as embedded. Truncation drops whole entries by rank.
  - The full symbol graph is **never** inlined. Each tier degrades independently on a missing or unreadable artifact.
- `_project_name(context_dir, root=None)`: `helpers.py:138`. The rebuild path reads the root ingest in `meta.json`, not the context dir's parent. Otherwise, indexing with `--root` elsewhere lets a refresh silently rename the project.
- Frozen dataclasses `Feature`/`Flow`/`FlowStep` + result types `ScaffoldResult`/`RenameResult`/`MergeResult`/`RemoveResult`/`PlacementResult`: `models.py:14-133`. Exception `FeatureRenameError(ValueError)`: `errors.py:5-7`.

## Examples

Scaffold a new feature for two net-new files (the reconcile placement path):

```
dummyindex context scaffold-feature --id payments-webhook \
  --name "Payments webhook" \
  --file src/pay/webhook.py --file src/pay/verify.py
# → context scaffold-feature: created payments-webhook (2 file(s), 7 member(s))
# writes feature.json (members from symbols.json, EXTRACTED), spec.md stub,
# .pending-enrichment, optional docs.md, INDEX.json entry; rebuilds INDEX.md + graph.{json,html}
```

Merge a trivial cluster into a real feature, then advance the anchor:

```
dummyindex context features-merge --from community-9 --into payments-webhook
# → appends community-9's spec prose into payments-webhook/supporting.md,
#   unions members/files/entry_points, deletes community-9, logs a stage-0 architect entry
dummyindex context mark-enriched --feature payments-webhook
```

Reconcile a deleted file off its feature without stranding it:

```
dummyindex context unassign-files --feature payments-webhook --file src/pay/verify.py
# → tolerates the now-deleted path, recomputes members over the remainder,
#   refuses if it would leave the feature with zero files
```
