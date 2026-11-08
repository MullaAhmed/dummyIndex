# Tree abstract enrichment — spec

`confidence: INFERRED`

## Intent

Fill the `abstract` field of every `.context/tree.json` node with real prose.
A PageIndex-style tree walk then reads summaries, not deterministic stubs.
The deterministic ingest seeds each node with an `EXTRACTED` stub abstract.
This domain plans those stubs and any `source-stale` nodes, whatever their prior confidence.
The host authoring session writes the abstracts. The domain merges them into `tree.json`.
A changed abstract or non-`INFERRED` confidence enters the update block.
That block assigns `INFERRED` and clears `source-stale`.
This is not a monotonic-confidence promotion guarantee.
An identical abstract on an already-`INFERRED` node changes no labels (`dummyindex/context/domains/enrich.py:116-120`, `:273-282`).
Planning and application perform filesystem I/O. Prose authoring stays outside the Python process.

## User-visible behavior

Two `dummyindex context` subcommands bracket the out-of-process LLM step.

1. **`enrich-plan [path] [--root DIR]`** walks `tree.json` top-down: project, dir, file, in-file symbol.
   It selects `EXTRACTED` nodes and `source-stale` nodes, whatever their prior confidence.
   It groups them into one `structure` batch plus one `file_subtree` batch per file.
   It writes the work-list to `.context/cache/_enrich_plan.json`, a gitignored scratch artefact (`dummyindex/cli/enrich.py:12-57`).
   It prints total and stub counts, a by-kind tally, and the batch count.
   Before writing, it upgrades the managed `.context/.gitignore` and deletes the pre-0.21 root-level plan copy (`dummyindex/cli/enrich.py:42-43`).
2. **The `/dummyindex` session authors batches** out of band.
   It reads the plan and writes one real abstract per node, one file batch at a time.
   Partial progress survives an interrupted session (`dummyindex/context/domains/enrich.py:6-9`).
3. **`enrich-apply [path] [--root DIR] --from-json FILE`** reads a `{node_id: abstract}` JSON object and merges it into `tree.json`.
   It reports the count of updated abstracts.
   On stderr, it warns about each `node_id` not present in the tree.
   It exits `1` when unknown ids exist, `0` otherwise (`dummyindex/cli/enrich.py:60-129`).

Both verbs refuse early with exit `2` when `.context/` or `tree.json` is absent (`dummyindex/cli/enrich.py:25-30`, `:99-104`).
Both reject unknown trailing arguments with exit `2` (`:20-22`, `:80-85`).
`enrich-apply` also requires `--from-json` (`:87-92`).
It checks that the file exists (`:93-95`).
It checks that the file decodes to a JSON object of `str -> str` (`:106-114`).
Any failure exits `2`.

**Mode gating is a skill-orchestration concern, not a CLI flag.**
The verbs are mode-agnostic. Planning selects the whole stub and stale set.
The `/dummyindex` skill scopes which batches it authors, by run mode (Phase 4.5, `dummyindex/skills/skill.md:327-347`).
`light` skips. `standard` authors the `structure` batch (project, dirs, files) through one architect subagent.
`deep` also fans a dev out per `file_subtree` batch for symbol-level abstracts.
Since the 2026-08 train, Phase 4.5 runs in every mode, including `light`.
It is skipped only when the run passes `--no-tree-enrich` (`skill.md:103`, `:346-347`).
The older "Scope by mode" paragraph (`skill.md:341-344`) still says light skips.
`concerns.md` flags this as an orchestrator-level contradiction.
The skill dispatches the authors and calls `enrich-apply`. The domain never sees a mode.

## Contracts

CLI entry points come from the `context` dispatcher.
It maps `ContextSubcommand.ENRICH_PLAN` to `enrich.run_plan` and `ENRICH_APPLY` to `enrich.run_apply` (`dummyindex/cli/__init__.py:100-101`):

- `run_plan(args: list[str]) -> int` (`dummyindex/cli/enrich.py:12-51`).
- `run_apply(args: list[str]) -> int` (`dummyindex/cli/enrich.py:54-123`).

Public domain functions (`dummyindex/context/domains/enrich.py`):

- `build_plan(context_dir: Path, *, now: datetime | None = None) -> EnrichPlan`.
  It walks `<context_dir>/tree.json`. It raises `FileNotFoundError` when the file is missing (`:93-183`).
- `write_plan(path: Path, plan: EnrichPlan) -> None`.
  It writes the plan JSON atomically, through a temp file and `replace`. It creates the parent dir (`:185-190`).
- `apply_updates(context_dir: Path, updates: dict[str, str]) -> ApplyResult`.
  It merges known abstracts and returns touched and unknown ids.
  Changed entries receive `INFERRED` and lose `source-stale`.
  Identical existing `INFERRED` entries keep their labels (`:207-227`, `:268-285`).

Frozen dataclasses (`dummyindex/context/domains/enrich.py`):

- `EnrichNode(node_id, kind, title, path, range, stub_abstract, evidence_files)` (`:31-41`).
- `EnrichBatch(name, kind, node_ids)` (`:44-50`).
- `EnrichPlan(schema_version, generated_at, context_dir, tree_path, stats, batches, nodes)` with `to_dict() -> dict` (`:53-90`).
- `ApplyResult(updated: tuple[str, ...], unknown: tuple[str, ...])` (`:193-204`).

JSON shapes:

- **Plan** (`_enrich_plan.json`, `SCHEMA_VERSION = 1` at `:28`).
  `to_dict` emits `{schema_version, generated_at, context_dir, tree_path, stats, batches, nodes}`.
  `stats = {total_nodes, stub_nodes, by_kind}`.
  Each batch is `{name, kind, node_ids}`.
  Each node is `{node_id, kind, title, path, range, stub_abstract, evidence_files}` (`:63-90`).
- **Apply input**: a JSON object mapping string `node_id` to string `abstract` (`dummyindex/cli/enrich.py:106-114`).

## Examples

Plan, then apply. The `/dummyindex` session authors the JSON between the two steps:

```
$ dummyindex context enrich-plan
context enrich-plan: wrote .context/cache/_enrich_plan.json
  total nodes: 612  stubs: 488  by_kind: {'project': 1, 'dir': 3, 'file': 41, 'function': 380, 'class': 24, 'method': 39}
  batches: 42

$ dummyindex context enrich-apply --from-json /tmp/abstracts.json
context enrich-apply: updated 488 abstract(s) in .context/tree.json
```

A typo'd `node_id` is reported, not silently dropped.
`apply_updates` checks it against the tree's id set (`dummyindex/context/domains/enrich.py:218-220`).
`run_apply` then exits `1` and lists the unknown ids on stderr (`dummyindex/cli/enrich.py:121-128`).
Reapplying an identical abstract to an already-`INFERRED` node adds no updated ID.
`_apply` skips that node's update block, label cleanup included.
An existing `source-stale` label therefore remains, and later planning selects the node.
Even with no changed node, `apply_updates` still rewrites the tree file (`dummyindex/context/domains/enrich.py:207-227`, `:268-285`).

## Reconcile 2026-08-23

The enrich seam is unchanged at HEAD. No commit has touched `cli/enrich.py` or `domains/enrich.py` since the last council.
This pass refreshed drifted line anchors only.
The surrounding train changed the *orchestrator*.
Phase 4.5 now runs in every mode, including `light`, unless `--no-tree-enrich` is passed (`skills/skill.md:103`, `:346-347`).
The drift and stamp engine this feature feeds (`context/drift.py`, `build/reconcile.py:stamp_reconciled`) gained a doc-basis snapshot and an ack store.
`session-memory` owns both.

## Release reconciliation 2026-11-06

The integration changes shared `tests/context/domains/test_query.py` membership. It does not change the tree-enrichment domain.
The file-fallback, IDF/size-normalization, exact-stem, synonym, directory and top-five symbol regressions exercise `context-query` (`tests/context/domains/test_query.py:339-483`).
They do not change tree planning or abstract application.
`build_plan` still prepares the enrichment worklist.
`apply_updates` still merges authored abstracts into the canonical tree (`dummyindex/context/domains/enrich.py:93-119`, `:207-227`).
No new enrichment behavior or measurement is claimed from this shared-test delta.
