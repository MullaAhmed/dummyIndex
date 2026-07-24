# Feature taxonomy engine — spec

confidence: INFERRED

## Intent

The `context/domains/features/` domain is the curated **feature taxonomy** layer of `.context/`: it turns the deterministic call/community graph into per-feature folders (`.context/features/<id>/`) and then offers atomic, idempotent CRUD ops so the `/dummyindex` council and reconcile procedure can reshape that taxonomy — rename, merge, scaffold, assign/unassign, remove — *without ever re-clustering* and without clobbering LLM-enriched prose. Members are always re-derived from `map/symbols.json` (never re-clustered); every artifact is written tmp-file+`replace` so a concurrent reader never sees a half-written file (`helpers.py:131-140`), and every op validates fully before its first write so a rejected op leaves the tree byte-identical. The domain also owns the **codebase scan** (`features/graph.json`, schema v2) and the self-contained three-tier viewer that renders it (`context/output/viewer/`) — the human-facing answer to "how does this repo work, and how does it use AI?" — plus the models and tolerant loaders for the graph-consumption artifacts (`seed-rank.json` via `scan/rank.py`, `graph-communities.json` via `communities.py`, `symbolRef` resolution via `scan/refs.py`); the PageRank computation and artifact writes live upstream in `context/build/communities.py`.

## User-visible behavior

All ops are reached as `dummyindex context <cmd>` (CLI layer `dummyindex/cli/features.py`), operate on `<root>/.context/features/`, map domain `FeatureRenameError` to **exit 2**, and print a one-line summary on success.

- **features-rename** (`run_rename`, `cli/features.py:33-117`) — move `features/<from>/` → `features/<to>/`, rewrite `feature_id`/`name`/`summary` in `feature.json`, the `feature_id` in every `flows/*.json`, and the matching `INDEX.json` + `INDEX.md` + `graph.json` entries. Idempotent when `from == to` (metadata refresh only); setting `--name`/`--summary` flips confidence to `INFERRED`.
- **features-merge** (`run_merge`, `cli/features.py:119-167`) — absorb a trivial feature `--from` into `--into` as a section (default/only `supporting`). Appends the source's `spec.md` prose into `<into>/supporting.md` wrapped in sentinels (re-merge appends, never clobbers), unions `members`/`files`/`entry_points` into the target's `feature.json`, deletes the source folder, drops it from `INDEX.json`/`graph.json`, and auto-logs a stage-0 architect entry to the target's council log. Rejects self-merge and unknown sections.
- **scaffold-feature** (`run_scaffold`, `cli/features.py:300-348`) — create a brand-new `features/<id>/` for net-new `--file`s: `feature.json` (members derived from symbols; `EXTRACTED`), a deterministic `spec.md` stub, a `.pending-enrichment` marker, optional `docs.md`, and an appended `INDEX.json` entry; regenerates `INDEX.md` + `graph.{json,html}`. Rejects an existing id, a reserved `community-*` id, no files, or a file missing/outside the repo.
- **assign-files** / **unassign-files** (`run_assign_files`/`run_unassign_files`, `cli/features.py:351-439`) — add/remove `--file`s on an existing feature, recompute members over the surviving file set, update INDEX counts, re-drop the pending marker; **preserve** enriched `spec.md`/`plan.md`/`concerns.md`. Assign is idempotent on already-owned files; unassign tolerates deleted paths but refuses to strand an empty feature.
- **features-remove** (`run_remove`, `cli/features.py:442-483`) — delete a dead feature's folder + INDEX entry (decrementing top-level `flow_count`); refuses while it still owns on-disk files or its `feature.json` is corrupt unless `--force`.
- **mark-enriched** (`run_mark_enriched`, `cli/features.py:486-527`) — clear a feature's `.pending-enrichment` marker (idempotent no-op when absent).
- **section-write** (`run_section_write`, `cli/features.py:243-297`) — atomically place a markdown file into `features/<id>/<section>.md`; canonical sections `spec`/`plan`/`concerns` always writable, legacy names update-only, others gated by `--allow-new-section`.
- **flow-remove** (`run_flow_remove`, `cli/features.py:169-208`) — delete a noise flow's `flows/<id>.{json,md}` and prune it from `feature.json`/`INDEX.json`/`graph.json`.
- **INDEX + scan artifacts** — `INDEX.json` is the canonical agent-readable feature list; `INDEX.md` is the rendered table; `graph.json` is the **curated codebase scan** and `graph.html` its viewer, which opens directly over `file://` (data inlined, no server, no network). The viewer is now **three tiers**: tier 1 is the curated map; tier 2 is a community overview (one supernode per `graph-communities.json` card, cross-community call volume as edge weight — the `Communities` button / `C` key, hidden entirely when the artifact is absent); tier 3 is focus+expand — selecting a curated node whose `symbolRef` resolves reveals its top-k symbol-graph neighbors as read-only "ghost" annotations with `path:line` citations, from a bounded expansion index precomputed at render time (`viewer/extras.py`). All three tiers ship in the same single self-contained file via a second `graph-extras` data island; when the extras artifacts are absent the placeholder stays and the viewer degrades to the plain curated map.
- **scan-check** (`cli/scan.py:25`) — validates `graph.json` against the schema-v2 contract and reports **every** violation in one pass with a JSON path. Also resolves each node's `symbolRef` against the extraction artifacts on disk (`load_symbol_ref_index`, `scan/refs.py:81`): an unresolvable ref is a `symbol_ref_unresolved` error; refs with **no** artifact present to check against collapse into one aggregate warning-severity `symbol_ref_unchecked` violation. Exit `0` clean (warnings printed, never fatal) / `1` error-severity violations / `2` nothing to check.

### The scan is seeded, then curated

`graph.json` follows the same two-stage contract as `spec.md`, and the split is the whole design:

- **Seed** (`scan/seed.py:95`) — written at ingest, `confidence: EXTRACTED`. One `service` node per feature, one `entry` per flow, cross-feature `calls` edges collapsed from the symbol graph's `calls`/`uses` links and ranked by call volume. When `features/seed-rank.json` exists (personalized PageRank over the symbol graph, written by `context/build/communities.py`), the seed consumes it via `load_seed_rank` (`scan/rank.py:57`): features are selected/ordered by summed member rank (`_feature_sort_key`, `seed.py:160`), entry flows by their entry point's rank (`_entry_sort_key`, `seed.py:233`), and every emitted node carries `evidence: EXTRACTED` plus, where a member resolves, a `symbolRef` into the symbol graph (`_top_member_ref`, `seed.py:177`). Without the artifact the seed falls back to file-count ordering — byte-identical to the pre-rank shape, no `evidence`/`symbolRef` fields at all. Deterministic and byte-reproducible either way; `project.date` is deliberately unset so a rebuild is not git noise. It knows the *shape* of the code and nothing about its meaning, and cannot see the AI surface at all.
- **Curated** — the `council/58-codebase-scan.md` stage rewrites it against real source and flips `confidence` to `INFERRED`.
- **Preserved** — `rebuild_features_graph` regenerates an `EXTRACTED` scan and leaves an `INFERRED` one verbatim (`_curated_scan`, `indexes.py:146`), keyed on confidence **alone, not validity**: a curated map cannot be re-derived, so a cap violation is a reason to run `scan-check`, never a reason to delete it.

Caps are the feature, not a limitation: ≤ 120 nodes / 240 edges (`MAX_SCAN_NODES`/`MAX_SCAN_EDGES`, `constants.py:26-27` — doubled from 60/120 by the graph-consumption upgrade: the ranked seed aims at 40-80 nodes and the hard cap leaves the council headroom to promote the AI surface without cutting business logic), node kinds `entry cron agent model tool service store external`, edge kinds `calls reads writes triggers`. Node `symbolRef` text is capped at 120 (`MAX_NODE_SYMBOL_REF`, `constants.py:42`). (v1 denormalized the whole extraction into this file — folder → file → class → method → feature → flow, ~4k nodes / ~8k edges on this repo. Per-symbol navigation did not move: it lives in `map/symbols.json` and `features/symbol-graph.json`, which is what agents actually query.)

## Contracts

Public surface re-exported from `dummyindex/context/domains/features/__init__.py:67-91`.

- `scaffold_features(context_dir, graph_data, *, root=None, flow_depth=_DEFAULT_FLOW_DEPTH, doc_catalog=None) -> ScaffoldResult` — `builder.py:45`. Build-time scaffolder; two deterministic passes (Leiden communities → features, in-degree-0 call nodes → BFS flows). Drops parser-artifact `__init__.py`-only communities (`_is_parser_artifact`, `builder.py:200`). Feeds the seed the on-disk ranked shortlist (`load_seed_rank`, `builder.py:179`) — read from disk, not recomputed, so scaffold and rebuild can't drift.
- `rename_feature(features_dir, *, from_id, to_id, new_name=None, new_summary=None) -> RenameResult` — `ops.py:28-157`.
- `merge_feature(features_dir, *, from_id, into_id, as_section, note=None) -> MergeResult` — `ops.py:162-349`.
- `remove_flow(features_dir, *, feature_id, flow_id) -> RenameResult` — `ops.py:352-452`.
- `write_section(features_dir, *, feature_id, section, source_file) -> Path` — `ops.py:454-492`.
- `scaffold_feature(features_dir, *, repo_root, feature_id, name, files, summary=None) -> PlacementResult` — `placement.py:49-125`.
- `assign_files(features_dir, *, repo_root, feature_id, files) -> PlacementResult` — `placement.py:128-190`.
- `unassign_files(features_dir, *, repo_root, feature_id, files) -> PlacementResult` — `placement.py:193-265`.
- `remove_feature(features_dir, *, feature_id, repo_root, force=False) -> RemoveResult` — `placement.py:268-324`.
- `clear_pending_enrichment(features_dir, feature_id) -> Optional[str]` — `placement.py:355-378`.
- `refresh_features_index_md(features_dir) -> Path` — `indexes.py:22`; `rebuild_features_graph(features_dir) -> tuple[Path, Path]` — `indexes.py:38`. The rebuild path loads the same on-disk `seed-rank.json` the scaffolder consumed (`indexes.py:118`) so the two regeneration paths stay byte-identical.
- `_graph_view(features, flows, *, project_name, slug=None, links=(), rank=None) -> dict` — `render.py:166`; thin wrapper over `seed_scan`.
- `seed_scan(features, flows, *, project_name, slug, links=(), rank=None, max_nodes, max_edges) -> Scan` — `scan/seed.py:95`; `slugify` — `scan/seed.py:45`.
- `load_seed_rank(features_dir) -> SeedRank | None` — `scan/rank.py:57`; frozen `SeedRank`/`RankEntry` (`rank.py:41,30`). Reads `features/seed-rank.json` (schema v1, written beside the symbol graph by `context/build/communities.py`). Missing/unreadable/malformed loads as `None` — never a failed seed; malformed rows are skipped, not fatal.
- `load_symbol_ref_index(features_dir) -> SymbolRefIndex | None` — `scan/refs.py:81`; frozen `SymbolRefIndex(ids, sources)` with `.resolves(ref)` (`refs.py:71`). Walks the `REF_ARTIFACTS` registry (`refs.py:64`: `symbol-graph.json` node ids + `graph-communities.json` community slugs — adding an artifact is one registry entry and nothing else). Returns `None` when no registered artifact could be read, so the caller degrades the check to a warning.
- `rollup_communities(node_by_id, communities, scores, *, owner_of_symbol=None, rationale_of=None, root=None, top_k=COMMUNITY_TOP_K) -> GraphCommunities` — `communities.py:94`. Pure roll-up of `analysis.cluster`'s `{int: [node_ids]}` partition into `features/graph-communities.json` cards (frozen `GraphCommunities`/`GraphCommunity`/`CommunityMember`, `communities.py:82,62,46`): **stable slug** `<dominant-feature>-<top-member>` (`_community_slug`, `:159` — never the raw partition int, which renumbers between runs), size, top-10 members by PageRank with `path:line` citations, plurality-owner feature, docstring-lifted one-line summary. Colliding slugs get deterministic ordinals (`_dedupe_slugs`, `:205`); rationale nodes are neither members nor size. The writer lives upstream in `context/build/communities.py`.
- `validate_scan(payload, *, symbol_refs=None) -> tuple[ScanViolation, ...]` — `scan/validate.py:93`; `ScanViolation(code, path, message, severity=ERROR)` — `scan/validate.py:77`. Pure: returns violations, raises nothing. `severity` is `ScanViolationSeverity` (`context/enums.py:93`): `ERROR` breaks the exit code, `WARNING` marks a check that could not run. With `symbol_refs=None` any `symbolRef`s present are reported once as an aggregate warning (`symbol_ref_unchecked`) instead of resolved; a scan without refs emits no warning at all.
- `rename_node` / `drop_nodes` / `drop_feature` — `scan/mutate.py:48,91,109`. Each returns a **new** payload or `None` when nothing matched, so `ops._rewrite_scan` (`ops.py:34`) can skip the write. The ops edit the scan in place rather than rebuilding it, because a rebuild would *preserve* a curated scan and the removed feature would linger on the map forever.
- Frozen scan models `Scan`/`ScanNode`/`ScanEdge`/`ScanChip`/`ScanProject`/`ScanStats` — `scan/models.py`. Optional fields are omitted from the wire shape, not emitted as `null`; `source_ref` → `sourceRef`, `from_id`/`to_id` → `from`/`to`. `ScanNode` carries two optional graph-consumption fields (`scan/models.py:83-84`): `symbol_ref` (wire `symbolRef`) pins the box to the extraction layer — a `symbol-graph.json` node id or a `graph-communities.json` community slug — and `evidence` is a `ScanEvidence` value (`context/enums.py:74`: `EXTRACTED` = survived the seed verbatim, `INFERRED` = added/reshaped by the authoring stage; deliberately *not* `pipeline.enums.ConfidenceLevel`, which grades whole artifacts and carries a third member the wire format forbids). Both optional so pre-extension scans stay valid.
- `render_viewer_html(scan, *, features_dir=None) -> str` — `context/output/viewer/__init__.py:98`; template constant `VIEWER_HTML` in the same module, split across `viewer/styles.py` + `viewer/script.py` + `viewer/tiers.py` (one shared script scope). With `features_dir`, the tier-2/tier-3 extras are derived from the on-disk artifacts and inlined as a second `graph-extras` data island; without it — or when the artifacts are absent — the empty placeholder stays and tiers 2+3 lie dormant.
- `build_viewer_extras(scan, cards_payload, graph_payload, rank_payload, *, root=None, top_k=8, budget_bytes=300*1024) -> ViewerExtras` — `viewer/extras.py:154` (pure); `load_viewer_extras(scan, features_dir) -> ViewerExtras` — `extras.py:188` (the file I/O). Tier 3's expansion index maps each resolving `symbolRef` to its top-`EXPANSION_TOP_K` (8) symbol-graph neighbors ranked by seed PageRank; the serialized index is hard-capped at `EXPANSION_BUDGET_BYTES` (300 KiB, `extras.py:39-40`) measured exactly as embedded, truncating whole entries by rank — the full symbol graph is **never** inlined. Each tier degrades independently on a missing/unreadable artifact.
- `_project_name(context_dir, root=None)` — `helpers.py:138`. The rebuild path reads the root ingest recorded in `meta.json` rather than assuming the context dir's parent — otherwise indexing with `--root` elsewhere lets a refresh silently rename the project.
- Frozen dataclasses `Feature`/`Flow`/`FlowStep` + result types `ScaffoldResult`/`RenameResult`/`MergeResult`/`RemoveResult`/`PlacementResult` — `models.py:14-133`. Exception `FeatureRenameError(ValueError)` — `errors.py:5-7`.

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
