# Tree abstract enrichment — plan

confidence: INFERRED

## Where it lives

The domain logic is `dummyindex/context/domains/enrich.py` (plan-building, the
`EnrichPlan`/`EnrichNode`/`EnrichBatch`/`ApplyResult` dataclasses, and the
tree.json merge). The CLI boundary is `dummyindex/cli/enrich.py`
(`run_plan`/`run_apply`), wired into the `context` dispatcher at
`dummyindex/cli/__init__.py:89-90` as `ENRICH_PLAN` and `ENRICH_APPLY`. The
confidence enum it reads/writes is `ConfidenceLevel` in
`dummyindex/pipeline/enums.py:16-24`. Tests live in
`tests/context/domains/test_enrich.py`.

## Architecture in three sentences

`build_plan` does a pre-order walk of `tree.json`, keeping only nodes still at
`EXTRACTED` confidence, and packs them into a structural batch plus one batch per
file subtree so authored abstracts can be written back incrementally. The CLI
`run_plan` persists that plan to the gitignored `.context/cache/_enrich_plan.json`
scratch file; the `/dummyindex` session reads it, writes real abstracts, and feeds
a `{node_id: abstract}` JSON back through `run_apply`. `apply_updates` merges those
abstracts into `tree.json`, flips each touched node to `INFERRED`, and reports any
unrecognised `node_id` so the session can catch typos.

## Data model

- **`_enrich_plan.json`** (work-list, schema_version 1) — serialised `EnrichPlan`:
  `stats` (`total_nodes`, `stub_nodes`, `by_kind`), `batches`
  (`{name, kind, node_ids}`), and `nodes`
  (`{node_id, kind, title, path, range, stub_abstract, evidence_files}`)
  (`dummyindex/context/domains/enrich.py:60-87`). Written atomically via
  temp-then-replace to `.context/cache/` (`:180-185`,
  `dummyindex/cli/enrich.py:40-43`).
- **`tree.json` node merge** — `apply_updates` sets `node["abstract"]` to the
  authored prose and `node["confidence"]` to `INFERRED`, but only when the value
  actually changes, then atomically rewrites the whole tree
  (`dummyindex/context/domains/enrich.py:261-275`, `:217-221`). The input mapping
  is keyed by `node_id`; ids absent from the tree are collected into
  `ApplyResult.unknown` rather than applied (`:213-215`).

## Key decisions

- **Retrieval-facing, not council input.** The abstracts this writes feed the
  PageIndex tree walk that future sessions navigate; they are not consumed by the
  per-feature council (which authors `spec.md`/`plan.md`/`concerns.md`). The plan
  is a transient *scratch* artefact under `cache/` — explicitly gitignored, not a
  committed doc (`dummyindex/cli/enrich.py:34-43`).
- **Mode scope.** Both verbs are gated behind the `dummyindex context`
  dispatcher and are inert without an ingested `.context/`/`tree.json`, exiting
  `2` early (`dummyindex/cli/enrich.py:22-28`, `:94-99`,
  `dummyindex/cli/__init__.py:89-90`).
- **One-way idempotent promotion.** Confidence only moves `EXTRACTED` → `INFERRED`
  and re-applying identical abstracts is a no-op, so interrupted or repeated
  sessions converge safely (`dummyindex/context/domains/enrich.py:11-14`,
  `:266-272`).
- **Per-file batching for resumability.** Grouping stub nodes by file subtree lets
  the session write back one file at a time and survive interruption with partial
  progress intact (`dummyindex/context/domains/enrich.py:6-9`, `:142-158`).
- **Legacy migration on plan.** `run_plan` upgrades a stale managed
  `.context/.gitignore` and removes the pre-0.21 root-level plan copy before
  writing the current cache path (`dummyindex/cli/enrich.py:34-43`).

## Open questions

- **Membership noise (human follow-up).** This feature was carved from the raw
  Leiden `community-0` cluster, which mixed the genuine enrich domain
  (`dummyindex/context/domains/enrich.py` + `dummyindex/cli/enrich.py`) with ~30
  unrelated end-to-end CLI test modules — `test_audit_cli`, `test_council_cli`,
  `test_equip_*`, `test_hooks*`, `test_placement`, `test_reality_check`,
  `test_query`, `test_status*`, and more (see `feature.json` `members`/`files`).
  Those tests cluster here only through shared test-harness call edges, not
  through the enrich domain; each belongs to the feature it actually exercises.
  The spec/plan are scoped to the real enrich domain; the surplus test membership
  should be reassigned to the owning features during a human-reviewed placement
  pass.
- Whether `enrich-apply` should validate that incoming `node_id`s were actually
  *planned* (present in the last `_enrich_plan.json`) rather than only checking
  presence in `tree.json` — currently only tree membership is enforced
  (`dummyindex/context/domains/enrich.py:213-215`).
