# Tree abstract enrichment — spec

`confidence: INFERRED`

## Intent

Fill the `abstract` field of every `.context/tree.json` node with real prose so a
future PageIndex-style tree walk reads meaningful summaries instead of
deterministic stubs. The deterministic ingest seeds each node with an
`EXTRACTED`-confidence stub abstract; this domain plans which nodes still carry a
stub, hands that work-list to the Claude session running `/dummyindex`, and merges
the session's authored abstracts back into `tree.json`, promoting each touched
node from `EXTRACTED` to `INFERRED`. The merge is a one-way confidence promotion
that never demotes and is idempotent under repeated identical applies, so an
interrupted or repeated session converges without corrupting prior work.

## User-visible behavior

Two `dummyindex context` subcommands bracket the out-of-process LLM step.

1. **`enrich-plan [path] [--root DIR]`** walks `tree.json`, collects stub
   (`EXTRACTED`) nodes top-down (project → dir → file → in-file symbol), groups
   them into a `structure` batch plus one `file_subtree` batch per file, and
   writes the work-list to `.context/cache/_enrich_plan.json` — a gitignored
   scratch artefact. It prints total/stub node counts, a by-kind tally, and the
   batch count (`dummyindex/cli/enrich.py:10-55`). Before writing it upgrades the
   managed `.context/.gitignore` and deletes the pre-0.21 root-level plan copy
   (`dummyindex/cli/enrich.py:40-41`).
2. **The `/dummyindex` session authors batches** out of band — reads the plan,
   writes one real abstract per node, one file-batch at a time so partial
   progress survives an interrupted session
   (`dummyindex/context/domains/enrich.py:6-9`).
3. **`enrich-apply [path] [--root DIR] --from-json FILE`** reads a
   `{node_id: abstract}` JSON object and merges it into `tree.json`. It reports
   the count of updated abstracts and, on stderr, warns about any `node_id` not
   present in the tree, exiting `1` when unknown ids exist and `0` otherwise
   (`dummyindex/cli/enrich.py:58-124`).

Both verbs refuse early with exit `2` when `.context/` or `tree.json` is absent
(`dummyindex/cli/enrich.py:22-28`, `:94-99`), and reject unknown trailing
arguments with exit `2` (`:18-20`, `:78-80`). `enrich-apply` further validates
that `--from-json` is supplied (`:82-87`), exists (`:88-90`), and decodes to a
JSON object of `str -> str` (`:101-109`); any failure is exit `2`.

**Mode gating is a skill-orchestration concern, not a CLI flag.** The verbs
themselves are mode-agnostic — they always plan/apply the whole stub set. The
`/dummyindex` skill scopes *which* batches it authors by run mode
(`dummyindex/skills/skill.md:260-263`): **light** skips enrichment entirely;
**standard** authors the `structure` batch (project + dirs + files) via one
architect subagent; **deep** additionally fans a dev out per `file_subtree`
batch for symbol-level abstracts. The skill dispatches the authors and calls
`enrich-apply`; the domain never sees a mode.

## Contracts

CLI entry points — routed from the `context` dispatcher, which maps
`ContextSubcommand.ENRICH_PLAN → enrich.run_plan` and
`ENRICH_APPLY → enrich.run_apply` (`dummyindex/cli/__init__.py:90-91`):

- `run_plan(args: list[str]) -> int` (`dummyindex/cli/enrich.py:10-55`).
- `run_apply(args: list[str]) -> int` (`dummyindex/cli/enrich.py:58-124`).

Public domain functions (`dummyindex/context/domains/enrich.py`):

- `build_plan(context_dir: Path, *, now: datetime | None = None) -> EnrichPlan`
  — walks `<context_dir>/tree.json`, raises `FileNotFoundError` if missing
  (`:90-177`).
- `write_plan(path: Path, plan: EnrichPlan) -> None` — atomic temp-then-`replace`
  write of the plan JSON, creating the parent dir (`:180-185`).
- `apply_updates(context_dir: Path, updates: dict[str, str]) -> ApplyResult`
  — merges abstracts, promotes confidence to `INFERRED`, returns touched +
  unknown ids (`:202-222`).

Frozen dataclasses (`dummyindex/context/domains/enrich.py`):

- `EnrichNode(node_id, kind, title, path, range, stub_abstract, evidence_files)`
  (`:28-38`).
- `EnrichBatch(name, kind, node_ids)` (`:41-47`).
- `EnrichPlan(schema_version, generated_at, context_dir, tree_path, stats,
  batches, nodes)` with `to_dict() -> dict` (`:50-87`).
- `ApplyResult(updated: tuple[str, ...], unknown: tuple[str, ...])` (`:188-199`).

JSON shapes:

- **Plan** (`_enrich_plan.json`, `schema_version = 1` at `:25`) — `to_dict`
  emits `{schema_version, generated_at, context_dir, tree_path, stats, batches,
  nodes}`; `stats = {total_nodes, stub_nodes, by_kind}`; each batch is
  `{name, kind, node_ids}`; each node is `{node_id, kind, title, path, range,
  stub_abstract, evidence_files}` (`:60-87`).
- **Apply input** — a JSON object mapping string `node_id` to string `abstract`
  (`dummyindex/cli/enrich.py:101-109`).

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
against the tree's id set (`dummyindex/context/domains/enrich.py:213-215`) and
`run_apply` exits `1`, listing the unknown ids on stderr
(`dummyindex/cli/enrich.py:116-123`). Re-running the same `enrich-apply` is a
no-op: `_apply` only writes when the abstract or confidence actually changes
(`dummyindex/context/domains/enrich.py:266-272`).
