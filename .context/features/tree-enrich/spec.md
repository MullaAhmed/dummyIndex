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
its labels unchanged (`dummyindex/context/domains/enrich.py:109-113`,
`dummyindex/context/domains/enrich.py:259-276`). Planning and application perform
filesystem I/O; the prose-authoring step remains outside the Python process.

## User-visible behavior

Two `dummyindex context` subcommands bracket the out-of-process LLM step.

1. **`enrich-plan [path] [--root DIR]`** walks `tree.json`, selects `EXTRACTED`
   nodes or nodes labeled `source-stale` regardless of their prior confidence,
   top-down (project → dir → file → in-file symbol), and groups
   them into a `structure` batch plus one `file_subtree` batch per file, and
   writes the work-list to `.context/cache/_enrich_plan.json` — a gitignored
   scratch artefact. It prints total/stub node counts, a by-kind tally, and the
   batch count (`dummyindex/cli/enrich.py:12-51`). Before writing it runs the
   shared context-layout migration (`dummyindex/cli/enrich.py:37`): merges the
   managed `.context/.gitignore` and `.gitattributes`, deletes the pre-0.21
   root-level plan copy, and removes retired paths — `equipment-evals/`
   (unedited v0.36 starter suites deleted, anything else backed up first) and
   the pre-v0.6 `graph/` (always backed up to `_doc_backups/retired/<version>/`)
   (`dummyindex/context/build/upgrade.py:300-307`,
   `dummyindex/context/build/upgrade.py:501-552`). The migration prints nothing:
   its removals, backups and errors are not reported.
2. **The `/dummyindex` session authors batches** out of band — reads the plan,
   writes one real abstract per node, one file-batch at a time so partial
   progress survives an interrupted session
   (`dummyindex/context/domains/enrich.py:3-5`).
3. **`enrich-apply [path] [--root DIR] --from-json FILE`** reads a
   `{node_id: abstract}` JSON object and merges it into `tree.json`. It reports
   the count of updated abstracts and, on stderr, warns about any `node_id` not
   present in the tree, exiting `1` when unknown ids exist and `0` otherwise
   (`dummyindex/cli/enrich.py:54-123`).

Both verbs refuse with exit `2` when `.context/` or `tree.json` is absent
(`dummyindex/cli/enrich.py:22-32`, `:93-98`) — for `enrich-plan` this happens
before the migration, so a failed plan has no side effects — and reject unknown
trailing arguments with exit `2` (`:17-19`, `:74-79`). `enrich-apply` checks
that `--from-json` is supplied (`:81-86`) and exists (`:87-89`) before the tree
check, and that the payload is a JSON object of `str -> str` (`:101-108`); each
failure is exit `2`. Malformed JSON is not handled: `json.loads` (`:100`) raises
an uncaught `JSONDecodeError`, so the process exits `1` with a traceback.

**Mode gating is a skill-orchestration concern, not a CLI flag.** The verbs
themselves are mode-agnostic — planning selects the whole stub/stale set. The
`/dummyindex` skill scopes *which* batches it authors by run mode (Phase 4.5,
`dummyindex/skills/skill.md:320-340`): **standard** authors the `structure`
batch (project + dirs + files) via one architect subagent; **deep**
additionally fans a dev out per `file_subtree` batch for symbol-level abstracts.
Phase 4.5 is **on by default in every mode — including light — and is skipped
only when the run passes `--no-tree-enrich`** (`dummyindex/skills/skill.md:96`, `:339-340`).
`skill.md` still carries an older "Scope by mode" paragraph (`:334-337`) saying
light skips — flagged as an orchestrator-level contradiction in `concerns.md`.
The skill dispatches the authors and calls `enrich-apply`; the domain never sees
a mode.

## Contracts

CLI entry points — routed from the `context` dispatcher, which maps
`ContextSubcommand.ENRICH_PLAN → enrich.run_plan` and
`ENRICH_APPLY → enrich.run_apply` (`dummyindex/cli/__init__.py:91-92`):

- `run_plan(args: list[str]) -> int` (`dummyindex/cli/enrich.py:12-51`).
- `run_apply(args: list[str]) -> int` (`dummyindex/cli/enrich.py:54-123`).

Public domain functions (`dummyindex/context/domains/enrich.py`):

- `build_plan(context_dir: Path, *, now: datetime | None = None) -> EnrichPlan`
  — walks `<context_dir>/tree.json`, raises `FileNotFoundError` if missing
  (`:86-173`).
- `write_plan(path: Path, plan: EnrichPlan) -> None` — atomic temp-then-`replace`
  write of the plan JSON, creating the parent dir (`:176-181`).
- `apply_updates(context_dir: Path, updates: dict[str, str]) -> ApplyResult`
  — merges known abstracts and returns touched + unknown ids; changed entries
  receive `INFERRED` and lose `source-stale`. Identical existing `INFERRED`
  entries retain their labels (`:198-218`, `:259-276`).

Consumed migration seam: `migrate_context_layout(context_dir: Path, *,
package_version: str | None) -> LayoutMigration` — never raises; each step's
failure lands in `LayoutMigration.errors`. `run_plan` passes
`package_version=None`, which skips extraction-cache version scoping
(`dummyindex/context/build/upgrade.py:501-552`).

Frozen dataclasses (`dummyindex/context/domains/enrich.py`):

- `EnrichNode(node_id, kind, title, path, range, stub_abstract, evidence_files)`
  (`:24-34`).
- `EnrichBatch(name, kind, node_ids)` (`:37-43`).
- `EnrichPlan(schema_version, generated_at, context_dir, tree_path, stats,
  batches, nodes)` with `to_dict() -> dict` (`:46-83`).
- `ApplyResult(updated: tuple[str, ...], unknown: tuple[str, ...])` (`:184-195`).

JSON shapes:

- **Plan** (`_enrich_plan.json`, `SCHEMA_VERSION = 1` at `:21`) — `to_dict`
  emits `{schema_version, generated_at, context_dir, tree_path, stats, batches,
  nodes}`; `stats = {total_nodes, stub_nodes, by_kind}`; each batch is
  `{name, kind, node_ids}`; each node is `{node_id, kind, title, path, range,
  stub_abstract, evidence_files}` (`:56-83`).
- **Apply input** — a JSON object mapping string `node_id` to string `abstract`
  (`dummyindex/cli/enrich.py:100-108`).

## Examples

Plan, then apply (the `/dummyindex` session authors the JSON between the two):

```
$ dummyindex context enrich-plan
context enrich-plan: wrote .context/cache/_enrich_plan.json
  total nodes: 612  stubs: 488  by_kind: {'project': 1, 'dir': 3, 'file': 41, 'function': 380, 'class': 24, 'method': 39}
  batches: 42

$ dummyindex context enrich-apply --from-json /tmp/abstracts.json
context enrich-apply: updated 488 abstract(s) in .context/tree.json
```

A typo'd `node_id` is surfaced, not silently dropped — `apply_updates` checks it
against the tree's id set (`dummyindex/context/domains/enrich.py:209-211`) and
`run_apply` exits `1`, listing the unknown ids on stderr
(`dummyindex/cli/enrich.py:115-122`). Reapplying an identical abstract to an
already-`INFERRED` node adds no updated ID; `_apply` skips that node's update
block, including label cleanup. An existing `source-stale` label therefore
remains and the node is selected by later planning. `apply_updates` still
serializes and replaces the tree file even when no node changes
(`dummyindex/context/domains/enrich.py:198-218`,
`dummyindex/context/domains/enrich.py:259-276`).
