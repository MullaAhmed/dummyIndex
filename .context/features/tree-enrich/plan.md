# Tree abstract enrichment — plan

confidence: INFERRED

## Boundary

Two-verb domain that brackets an out-of-process LLM step: `enrich-plan` emits a
work-list of stub tree nodes, the `/dummyindex` session authors real abstracts,
`enrich-apply` merges them back. The bounded context is exactly two source files:

- **Domain** — `dummyindex/context/domains/enrich.py`: `build_plan` (`:90`),
  `apply_updates` (`:202`), `write_plan` (`:180`), and the frozen DTOs
  `EnrichNode`/`EnrichBatch`/`EnrichPlan`/`ApplyResult`.
- **CLI boundary** — `dummyindex/cli/enrich.py`: `run_plan` (`:10`),
  `run_apply` (`:58`). All argv parsing, file existence gating, and JSON
  payload validation live here; the domain functions take a `Path` + a
  `dict[str, str]` and never touch argv.

Everything else in `feature.json` `members`/`files` (the ~30 `test_*_cli`
modules) is cluster noise — see Open questions.

## Plan / apply bracket (the core pattern)

The pattern is a **plan → out-of-band author → apply** loop, the same shape as
the `enrich-plan`/`enrich-apply` verbs themselves:

1. `build_plan` does a single **pre-order walk** (`_walk`,
   `dummyindex/context/domains/enrich.py:228-235`) of `tree.json["root"]`,
   keeping only nodes still at `EXTRACTED` confidence (`:114`), and partitions
   them into one `structure` batch (project + dir nodes) plus one
   `file_subtree` batch per file (`:142-158`).
2. `run_plan` persists the plan to the gitignored scratch file
   `.context/cache/_enrich_plan.json` (`dummyindex/cli/enrich.py:42-43`).
3. The session reads the plan, writes abstracts, and feeds a
   `{node_id: abstract}` JSON back through `enrich-apply --from-json`.
4. `apply_updates` merges via `_apply` (`:261-275`), flips each touched node to
   `INFERRED`, and returns unrecognised ids in `ApplyResult.unknown` (`:215`).

**Atomic writer pattern** — both writers use temp-then-`replace`: `write_plan`
(`dummyindex/context/domains/enrich.py:182-185`) and the tree rewrite in
`apply_updates` (`:219-221`). A crash mid-write leaves the prior file intact.

## Data model

- **`_enrich_plan.json`** (schema_version 1, `:25`) — serialised `EnrichPlan`
  via `to_dict` (`:60-87`): `stats` (`total_nodes`, `stub_nodes`, `by_kind`),
  `batches` (`{name, kind, node_ids}`), `nodes`
  (`{node_id, kind, title, path, range, stub_abstract, evidence_files}`).
- **`tree.json` node merge** — `_apply` (`:261-275`) sets `node["abstract"]`
  to the authored prose and `node["confidence"]` to `INFERRED`, but **only when
  the value actually changes** (`:266-272`). Ids in `updates` absent from the
  tree are collected into `ApplyResult.unknown` (`:213-215`) rather than applied.

## Dependencies

- **Upstream (in):** `ConfidenceLevel` enum
  (`dummyindex/pipeline/enums.py:16-24`) — the `EXTRACTED`/`INFERRED` strings
  this domain filters and writes; `tree.json["root"]`, produced by the
  deterministic ingest, which seeds every node with an `EXTRACTED` stub.
  `run_plan` also calls `ensure_context_gitignore` + `remove_legacy_enrich_plan`
  from `dummyindex.context.build.runner` (`dummyindex/cli/enrich.py:11-14`).
- **Downstream (out):** the `context` dispatcher in
  `dummyindex/cli/__init__.py` maps `ContextSubcommand.ENRICH_PLAN` →
  `enrich.run_plan` and `ENRICH_APPLY` → `enrich.run_apply`; the enriched
  `tree.json` is consumed by the PageIndex tree walk future sessions navigate.
- **Cycles:** none. The domain depends only on the enum and stdlib; the CLI
  depends on the domain and `build.runner`. No back-edges.

## Decisions

- **Decided: plan is a transient scratch artefact, not a committed doc** —
  because the abstracts feed retrieval (the PageIndex walk), not the council, so
  the work-list has no archival value. It lives under `cache/` and `run_plan`
  actively upgrades the managed `.gitignore` and deletes the pre-0.21 root copy
  (`dummyindex/cli/enrich.py:34-43`).
- **Decided: confidence promotion is one-way and idempotent** — `_apply` only
  ever sets `INFERRED`, never demotes, and re-applying identical abstracts is a
  no-op (`:266-272`) — because interrupted or repeated sessions must converge
  without corrupting prior work.
- **Decided: batch per file subtree, not one flat list** — because the session
  writes abstracts one file at a time and partial progress must survive an
  interrupted session, so each `file_subtree` batch (`:151-158`) is an
  independently-completable unit.
- **Decided: typo'd node_ids surface, never silently drop** — `apply_updates`
  checks `_collect_ids` membership and returns mismatches in `unknown` (`:215`);
  `run_apply` exits `1` and lists them on stderr
  (`dummyindex/cli/enrich.py:116-123`) — because a silent drop would lose an
  authored abstract with no signal.
- **Decided: both verbs are mode-gated, inert without an index** — exit `2`
  early when `.context/`/`tree.json` is absent
  (`dummyindex/cli/enrich.py:22-28`, `:94-99`) — because operating on a missing
  tree is a usage error, not a runtime fault.

## Open questions

- **Membership noise (human follow-up).** This feature was carved from the raw
  Leiden `community-0` cluster, which mixed the genuine enrich domain (the two
  files above) with ~30 unrelated end-to-end CLI test modules
  (`test_audit_cli`, `test_council_cli`, `test_equip_*`, `test_hooks*`,
  `test_placement`, `test_query`, `test_status*`, …). They cluster here only via
  shared test-harness call edges, not the enrich domain. The spec/plan are
  scoped to the real domain; the surplus tests should be reassigned during a
  human-reviewed placement pass.
- **Plan-membership validation.** Whether `enrich-apply` should require incoming
  `node_id`s to have been *planned* (present in the last `_enrich_plan.json`)
  rather than merely present in `tree.json` — today only tree membership is
  enforced (`dummyindex/context/domains/enrich.py:213-215`).
