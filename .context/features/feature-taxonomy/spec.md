# Feature taxonomy engine — spec

confidence: INFERRED

## Intent

The `context/domains/features/` domain is the curated **feature taxonomy** layer of `.context/`: it turns the deterministic call/community graph into per-feature folders (`.context/features/<id>/`) and then offers atomic, idempotent CRUD ops so the `/dummyindex` council and reconcile procedure can reshape that taxonomy — rename, merge, scaffold, assign/unassign, remove — *without ever re-clustering* and without clobbering LLM-enriched prose. Members are always re-derived from `map/symbols.json` (never re-clustered); every artifact is written tmp-file+`replace` so a concurrent reader never sees a half-written file (`helpers.py:131-140`), and every op validates fully before its first write so a rejected op leaves the tree byte-identical. The bundled HTML graph viewer (`context/output/viewer.py`) ships beside `features/graph.json` as the human-facing visualization.

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
- **INDEX + graph artifacts** — `INDEX.json` is the canonical agent-readable feature list; `INDEX.md` is the rendered table; `graph.{json,html}` is the denormalized viewer payload (six node kinds: folder/file/class/function/method/feature/flow) opened with a local `http.server`.

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
- `_graph_view(features, flows, symbols=None) -> dict` — `render.py:157-357`; viewer string `VIEWER_HTML` — `context/output/viewer.py:25`.
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
