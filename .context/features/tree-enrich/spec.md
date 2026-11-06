# Tree abstract enrichment — spec

`confidence: INFERRED`

## Intent

Fill the `abstract` field of every `.context/tree.json` node with real prose so a
future PageIndex-style tree walk reads meaningful summaries instead of
deterministic stubs. The deterministic ingest seeds each node with an
`EXTRACTED`-confidence stub abstract; this domain plans those stubs and any
`source-stale` nodes regardless of prior confidence, hands the work-list to the
host authoring session, and merges authored abstracts back into `tree.json`.
A changed abstract or non-`INFERRED` confidence enters the update block, which
assigns `INFERRED` and clears `source-stale`; this is not a monotonic-confidence
promotion guarantee. An identical abstract on an already-`INFERRED` node leaves
its labels unchanged (`dummyindex/context/domains/enrich.py:116-123`,
`dummyindex/context/domains/enrich.py:268-285`). Planning and application perform
filesystem I/O; the prose-authoring step remains outside the Python process.

## User-visible behavior

Two `dummyindex context` subcommands bracket the out-of-process LLM step.

1. **`enrich-plan [path] [--root DIR]`** walks `tree.json`, selects `EXTRACTED`
   nodes or nodes labeled `source-stale` regardless of their prior confidence,
   top-down (project → dir → file → in-file symbol), and groups
   them into a `structure` batch plus one `file_subtree` batch per file, and
   writes the work-list to `.context/cache/_enrich_plan.json` — a gitignored
   scratch artefact. It prints total/stub node counts, a by-kind tally, and the
   batch count (`dummyindex/cli/enrich.py:12-57`). Before writing it upgrades the
   managed `.context/.gitignore` and deletes the pre-0.21 root-level plan copy
   (`dummyindex/cli/enrich.py:42-43`).
2. **The `/dummyindex` session authors batches** out of band — reads the plan,
   writes one real abstract per node, one file-batch at a time so partial
   progress survives an interrupted session
   (`dummyindex/context/domains/enrich.py:6-9`).
3. **`enrich-apply [path] [--root DIR] --from-json FILE`** reads a
   `{node_id: abstract}` JSON object and merges it into `tree.json`. It reports
   the count of updated abstracts and, on stderr, warns about any `node_id` not
   present in the tree, exiting `1` when unknown ids exist and `0` otherwise
   (`dummyindex/cli/enrich.py:60-129`).

Both verbs refuse early with exit `2` when `.context/` or `tree.json` is absent
(`dummyindex/cli/enrich.py:25-30`, `:99-104`), and reject unknown trailing
arguments with exit `2` (`:20-22`, `:80-85`). `enrich-apply` further validates
that `--from-json` is supplied (`:87-92`), exists (`:93-95`), and decodes to a
JSON object of `str -> str` (`:106-114`); any failure is exit `2`.

**Mode gating is a skill-orchestration concern, not a CLI flag.** The verbs
themselves are mode-agnostic — planning selects the whole stub/stale set. The
`/dummyindex` skill scopes *which* batches it authors by run mode (Phase 4.5,
`dummyindex/skills/skill.md:320-340`): **light** skips; **standard** authors the
`structure` batch (project + dirs + files) via one architect subagent; **deep**
additionally fans a dev out per `file_subtree` batch for symbol-level abstracts.
Since the 2026-08 train, Phase 4.5 is **on by default in every mode — including
light — and is skipped only when the run passes `--no-tree-enrich`**
(`skill.md:96`, `:339-340`). Note `skill.md` still carries an older
"Scope by mode" paragraph (`:334-337`) saying light skips — flagged as an
orchestrator-level contradiction in `concerns.md`. The skill dispatches the
authors and calls `enrich-apply`; the domain never sees a mode.

## Contracts

CLI entry points — routed from the `context` dispatcher, which maps
`ContextSubcommand.ENRICH_PLAN → enrich.run_plan` and
`ENRICH_APPLY → enrich.run_apply` (`dummyindex/cli/__init__.py:100-101`):

- `run_plan(args: list[str]) -> int` (`dummyindex/cli/enrich.py:12-57`).
- `run_apply(args: list[str]) -> int` (`dummyindex/cli/enrich.py:60-129`).

Public domain functions (`dummyindex/context/domains/enrich.py`):

- `build_plan(context_dir: Path, *, now: datetime | None = None) -> EnrichPlan`
  — walks `<context_dir>/tree.json`, raises `FileNotFoundError` if missing
  (`:93-183`).
- `write_plan(path: Path, plan: EnrichPlan) -> None` — atomic temp-then-`replace`
  write of the plan JSON, creating the parent dir (`:186-191`).
- `apply_updates(context_dir: Path, updates: dict[str, str]) -> ApplyResult`
  — merges known abstracts and returns touched + unknown ids; changed entries
  receive `INFERRED` and lose `source-stale`. Identical existing `INFERRED`
  entries retain their labels (`:207-227`, `:268-285`).

Frozen dataclasses (`dummyindex/context/domains/enrich.py`):

- `EnrichNode(node_id, kind, title, path, range, stub_abstract, evidence_files)`
  (`:31-41`).
- `EnrichBatch(name, kind, node_ids)` (`:44-50`).
- `EnrichPlan(schema_version, generated_at, context_dir, tree_path, stats,
  batches, nodes)` with `to_dict() -> dict` (`:53-90`).
- `ApplyResult(updated: tuple[str, ...], unknown: tuple[str, ...])` (`:194-205`).

JSON shapes:

- **Plan** (`_enrich_plan.json`, `SCHEMA_VERSION = 1` at `:28`) — `to_dict`
  emits `{schema_version, generated_at, context_dir, tree_path, stats, batches,
  nodes}`; `stats = {total_nodes, stub_nodes, by_kind}`; each batch is
  `{name, kind, node_ids}`; each node is `{node_id, kind, title, path, range,
  stub_abstract, evidence_files}` (`:63-90`).
- **Apply input** — a JSON object mapping string `node_id` to string `abstract`
  (`dummyindex/cli/enrich.py:106-114`).

## Examples

Plan, then apply (the `/dummyindex` session authors the JSON between the two):

```
$ dummyindex context enrich-plan
context enrich-plan: wrote .context/cache/_enrich_plan.json
  total nodes: 612  stubs: 488  by_kind: {'file': 41, 'symbol': 444, 'dir': 3}
  batches: 42

$ dummyindex context enrich-apply --from-json /tmp/abstracts.json
context enrich-apply: updated 488 abstract(s) in .context/tree.json
```

A typo'd `node_id` is surfaced, not silently dropped — `apply_updates` checks it
against the tree's id set (`dummyindex/context/domains/enrich.py:219-221`) and
`run_apply` exits `1`, listing the unknown ids on stderr
(`dummyindex/cli/enrich.py:121-128`). Reapplying an identical abstract to an
already-`INFERRED` node adds no updated ID; `_apply` skips that node's update
block, including label cleanup. An existing `source-stale` label therefore
remains and the node is selected by later planning. `apply_updates` still
serializes and replaces the tree file even when no node changes
(`dummyindex/context/domains/enrich.py:207-227`,
`dummyindex/context/domains/enrich.py:268-285`).

## Reconcile 2026-08-23

The enrich seam itself is unchanged at HEAD (no commit has touched
`cli/enrich.py` / `domains/enrich.py` since the last council); this pass
refreshed drifted line anchors only. The surrounding train changed the
*orchestrator*: Phase 4.5 now runs in every mode including light unless
`--no-tree-enrich` (`skills/skill.md:96,339-340`), and the drift/stamp engine
this feature feeds (`context/drift.py`, `build/reconcile.py:stamp_reconciled`)
gained a doc-basis snapshot + ack store owned by `session-memory`. The
deterministic backbone at HEAD (`tree.json`/`map/`) currently indexes only the
foreign `results/benchmarks/` workspaces — see `concerns.md` placement note.

## Release reconciliation 2026-11-06

The integration changes this feature's shared
`tests/context/domains/test_query.py` membership, not the tree-enrichment
domain. The file-fallback, IDF/size-normalization, exact-stem, synonym, directory
and top-five symbol regressions exercise `context-query`
(`tests/context/domains/test_query.py:339-483`). They do not change tree planning
or abstract application. `build_plan` still prepares the enrichment worklist
and `apply_updates` still merges authored abstracts into the canonical tree
(`dummyindex/context/domains/enrich.py:93-119`,
`dummyindex/context/domains/enrich.py:207-227`). No new enrichment behavior or
measurement is claimed from this shared-test delta.
