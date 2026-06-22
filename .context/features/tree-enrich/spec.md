# Tree abstract enrichment — spec

confidence: INFERRED

## Intent

Fill the `abstract` field of every `.context/tree.json` node with real prose so a
future PageIndex-style tree walk reads meaningful summaries instead of
deterministic stubs. The deterministic ingest seeds each node with an
`EXTRACTED`-confidence stub abstract; this domain plans which nodes still carry a
stub, hands the work-list to the Claude session running `/dummyindex`, and merges
the session's authored abstracts back into `tree.json`, bumping each touched node
from `EXTRACTED` → `INFERRED`
(`dummyindex/context/domains/enrich.py:1-15`, `:114`, `:268-271`).

The merge is deliberately a one-way confidence promotion: `apply_updates` only
ever sets `INFERRED`, never demotes, and re-applying identical abstracts is a
no-op (`dummyindex/context/domains/enrich.py:202-222`, `:261-275`).

## User-visible behavior

Two `dummyindex context` subcommands bracket the LLM step:

1. **`enrich-plan [path] [--root DIR]`** walks `tree.json`, collects stub
   (`EXTRACTED`) nodes top-down (project → dir → file → in-file symbol), groups
   them into per-file batches, and writes the work-list to
   `.context/cache/_enrich_plan.json` (a gitignored scratch artefact). It prints
   total/stub node counts, a by-kind tally, and the batch count
   (`dummyindex/cli/enrich.py:10-55`).
2. **The `/dummyindex` session authors batches** — reads the plan, writes a real
   abstract per node, one file-batch at a time so partial progress survives an
   interrupted session (`dummyindex/context/domains/enrich.py:6-9`, `:142-158`).
3. **`enrich-apply [path] [--root DIR] --from-json FILE`** reads a
   `{node_id: abstract}` JSON mapping and merges it into `tree.json`. It reports
   the count of updated abstracts and, on stderr, warns about any `node_id` not
   present in the tree (exit `1` when unknown ids exist, else `0`)
   (`dummyindex/cli/enrich.py:58-124`).

Both verbs are mode-gated through the `context` dispatcher
(`ContextSubcommand.ENRICH_PLAN` / `ENRICH_APPLY` at
`dummyindex/cli/__init__.py:89-90`); both refuse with exit `2` when `.context/`
or `tree.json` is absent (`dummyindex/cli/enrich.py:22-28`, `:94-99`).

## Contracts

Public domain functions (`dummyindex/context/domains/enrich.py`):

- `build_plan(context_dir: Path, *, now: datetime | None = None) -> EnrichPlan`
  — walks `<context_dir>/tree.json`, raises `FileNotFoundError` if missing
  (`:90-177`).
- `write_plan(path: Path, plan: EnrichPlan) -> None` — atomic temp-then-replace
  write of the plan JSON (`:180-185`).
- `apply_updates(context_dir: Path, updates: dict[str, str]) -> ApplyResult`
  — merges abstracts, promotes confidence, returns touched + unknown ids
  (`:202-222`).

Frozen dataclasses (`dummyindex/context/domains/enrich.py`):

- `EnrichNode(node_id, kind, title, path, range, stub_abstract, evidence_files)`
  (`:28-38`).
- `EnrichBatch(name, kind, node_ids)` (`:41-47`).
- `EnrichPlan(schema_version, generated_at, context_dir, tree_path, stats,
  batches, nodes)` with `to_dict() -> dict` (`:50-87`).
- `ApplyResult(updated: tuple[str, ...], unknown: tuple[str, ...])` (`:188-199`).

CLI handlers (`dummyindex/cli/enrich.py`):

- `run_plan(args: list[str]) -> int` (`:10-55`).
- `run_apply(args: list[str]) -> int` (`:58-124`).

`SCHEMA_VERSION = 1` stamps every plan
(`dummyindex/context/domains/enrich.py:25`).

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

A typo in a `node_id` is surfaced, not silently dropped — `enrich-apply` exits `1`
and lists the unknown ids on stderr
(`dummyindex/cli/enrich.py:116-123`,
`dummyindex/context/domains/enrich.py:213-215`).
