# Feature taxonomy engine — spec

confidence: INFERRED

## Intent

The `context/domains/features/` domain is the curated **feature taxonomy** layer of `.context/`: it turns the deterministic call/community graph into per-feature folders (`.context/features/<id>/`) and then offers atomic, idempotent CRUD ops so the `/dummyindex` council and reconcile procedure can reshape that taxonomy — rename, merge, scaffold, assign/unassign, remove — *without ever re-clustering* and without clobbering LLM-enriched prose. Members are always re-derived from `map/symbols.json` (never re-clustered); every artifact is written tmp-file+`replace` so a concurrent reader never sees a half-written file (`helpers.py:131-140`), and every op validates fully before its first write so a rejected op leaves the tree byte-identical. The domain also owns the **codebase scan** (`features/graph.json`, schema v2) and the self-contained viewer that renders it (`context/output/viewer/`) — the human-facing answer to "how does this repo work, and how does it use AI?".

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
- **INDEX + scan artifacts** — `INDEX.json` is the canonical agent-readable feature list; `INDEX.md` is the rendered table; `graph.json` is the **curated codebase scan** and `graph.html` its viewer, which opens directly over `file://` (data inlined, no server, no network).
- **scan-check** (`cli/scan.py:23`) — validates `graph.json` against the schema-v2 contract and reports **every** violation in one pass with a JSON path. Exit `0` clean / `1` violations / `2` nothing to check.

### The scan is seeded, then curated

`graph.json` follows the same two-stage contract as `spec.md`, and the split is the whole design:

- **Seed** (`scan/seed.py:93`) — written at ingest, `confidence: EXTRACTED`. One `service` node per feature, one `entry` per flow, cross-feature `calls` edges collapsed from the symbol graph's `calls`/`uses` links and ranked by call volume. Deterministic and byte-reproducible; `project.date` is deliberately unset so a rebuild is not git noise. It knows the *shape* of the code and nothing about its meaning, and cannot see the AI surface at all.
- **Curated** — the `council/58-codebase-scan.md` stage rewrites it against real source and flips `confidence` to `INFERRED`.
- **Preserved** — `rebuild_features_graph` regenerates an `EXTRACTED` scan and leaves an `INFERRED` one verbatim (`indexes.py:142`), keyed on confidence **alone, not validity**: a curated map cannot be re-derived, so a cap violation is a reason to run `scan-check`, never a reason to delete it.

Caps are the feature, not a limitation: ≤ 60 nodes / 120 edges, node kinds `entry cron agent model tool service store external`, edge kinds `calls reads writes triggers`. (v1 denormalized the whole extraction into this file — folder → file → class → method → feature → flow, ~4k nodes / ~8k edges on this repo. Per-symbol navigation did not move: it lives in `map/symbols.json` and `features/symbol-graph.json`, which is what agents actually query.)

## Contracts

Public surface re-exported from `dummyindex/context/domains/features/__init__.py:66-90`.

- `scaffold_features(context_dir, graph_data, *, root=None, flow_depth=_DEFAULT_FLOW_DEPTH, doc_catalog=None) -> ScaffoldResult` — `builder.py:35-172`. Build-time scaffolder; two deterministic passes (Leiden communities → features, in-degree-0 call nodes → BFS flows). Drops parser-artifact `__init__.py`-only communities (`builder.py:176-198`).
- `rename_feature(features_dir, *, from_id, to_id, new_name=None, new_summary=None) -> RenameResult` — `ops.py:28-157`.
- `merge_feature(features_dir, *, from_id, into_id, as_section, note=None) -> MergeResult` — `ops.py:162-349`.
- `remove_flow(features_dir, *, feature_id, flow_id) -> RenameResult` — `ops.py:352-452`.
- `write_section(features_dir, *, feature_id, section, source_file) -> Path` — `ops.py:454-492`.
- `scaffold_feature(features_dir, *, repo_root, feature_id, name, files, summary=None) -> PlacementResult` — `placement.py:49-125`.
- `assign_files(features_dir, *, repo_root, feature_id, files) -> PlacementResult` — `placement.py:128-190`.
- `unassign_files(features_dir, *, repo_root, feature_id, files) -> PlacementResult` — `placement.py:193-265`.
- `remove_feature(features_dir, *, feature_id, repo_root, force=False) -> RemoveResult` — `placement.py:268-324`.
- `clear_pending_enrichment(features_dir, feature_id) -> Optional[str]` — `placement.py:355-378`.
- `refresh_features_index_md(features_dir) -> Path` — `indexes.py:19-32`; `rebuild_features_graph(features_dir) -> tuple[Path, Path]` — `indexes.py:34-106`.
- `_graph_view(features, flows, *, project_name, slug=None, links=()) -> dict` — `render.py:166`; thin wrapper over `seed_scan`.
- `seed_scan(features, flows, *, project_name, slug, links=(), max_nodes, max_edges) -> Scan` — `scan/seed.py:93`; `slugify` — `scan/seed.py:45`.
- `validate_scan(payload) -> tuple[ScanViolation, ...]` — `scan/validate.py:81`; `ScanViolation(code, path, message)` — `scan/validate.py:68`. Pure: returns violations, raises nothing.
- `rename_node` / `drop_nodes` / `drop_feature` — `scan/mutate.py:48,91,109`. Each returns a **new** payload or `None` when nothing matched, so `ops._rewrite_scan` (`ops.py:34`) can skip the write. The ops edit the scan in place rather than rebuilding it, because a rebuild would *preserve* a curated scan and the removed feature would linger on the map forever.
- Frozen scan models `Scan`/`ScanNode`/`ScanEdge`/`ScanChip`/`ScanProject`/`ScanStats` — `scan/models.py`. Optional fields are omitted from the wire shape, not emitted as `null`; `source_ref` → `sourceRef`, `from_id`/`to_id` → `from`/`to`.
- `render_viewer_html(scan) -> str` — `context/output/viewer/__init__.py:77`; template constant `VIEWER_HTML` in the same module, split across `viewer/styles.py` + `viewer/script.py`.
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
