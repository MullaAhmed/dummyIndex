# Tree abstract enrichment — plan

`confidence: INFERRED`

## Bounded context

`dummyindex/context/domains/enrich.py` owns the enrichment worklist and tree
writeback; `dummyindex/cli/enrich.py` validates CLI arguments/payloads and maps
outcomes to exit codes. Both layers perform filesystem I/O. The authoring step
belongs to the host workflow, not a Python model client. Co-clustered CLI tests
and `tests/context/domains/test_query.py` do not make other CLI/retrieval domains
part of enrichment's ownership boundary.

The frozen records are `EnrichNode`, `EnrichBatch`, `EnrichPlan` and `ApplyResult`
(`dummyindex/context/domains/enrich.py:31-90`,
`dummyindex/context/domains/enrich.py:193-204`). The shared dispatcher exposes
`enrich-plan`/`enrich-apply`; this feature consumes that dispatch seam.

## Plan / author / apply

1. `build_plan` resolves the context directory and walks `tree.json` in
   pre-order. It selects nodes with `EXTRACTED` confidence **or** a
   `source-stale` label. Project/directory nodes form `structure`; file nodes
   and their selected symbols form `file_subtree` batches. A file node need
   not itself be selected for its stale child to enter a batch
   (`dummyindex/context/domains/enrich.py:93-182`).
2. `run_plan` upgrades the managed ignore rules, removes the legacy root plan
   and atomically writes `.context/cache/_enrich_plan.json`. The host authors
   a string-to-string update mapping outside the process
   (`dummyindex/cli/enrich.py:12-57`,
   `dummyindex/context/domains/enrich.py:185-190`). This is a plan/apply workflow,
   not an atomic transaction spanning authoring.
3. `run_apply` validates the mapping's shape, then `apply_updates` checks IDs
   against the current tree, applies known entries and replaces `tree.json`.
   `_apply` sets the supplied abstract and confidence to `INFERRED`, clearing
   `source-stale` on changed entries. Identical abstract/confidence is a no-op
   for that node (`dummyindex/cli/enrich.py:60-129`,
   `dummyindex/context/domains/enrich.py:207-227`,
   `dummyindex/context/domains/enrich.py:268-285`).

## Dependencies and feedback

The deterministic backbone supplies the tree and stale labels; the host consumes
the plan and supplies authored updates. The written tree feeds future tree
navigation and the next plan. This is data feedback through the tree, not a
Python dependency on the authoring model. Enrichment runs after feature council
and before index refresh in the declared workflow
(`dummyindex/skills/council/52-tree-enrich.md:3-12`). The domain never accepts a
run-mode flag.

## Decisions and limits

- Per-file batches permit incremental authoring and application. `structure`
  contains project/directories; file heads remain in their file batches
  (`dummyindex/context/domains/enrich.py:137-164`). A host choosing skeleton-only
  work must filter node kinds, not assume every file is in `structure`.
- Apply accepts any current tree ID, not only IDs from the latest worklist.
  Unknown IDs are reported after known updates are written; the CLI exits `1`
  for that partial result. It is not an all-or-nothing rejection
  (`dummyindex/context/domains/enrich.py:217-227`,
  `dummyindex/cli/enrich.py:116-129`).
- Temp-file replacement protects each completed write from a partial-file
  publish. It does not provide a project lock or detect an intervening tree
  generation (`dummyindex/context/domains/enrich.py:185-190`,
  `dummyindex/context/domains/enrich.py:223-226`).
- Current workflow prose disagrees on light mode: the phase says on in every
  mode, while the mode table says skip. That is an unresolved orchestration
  contradiction; the mode-agnostic domain cannot settle it
  (`dummyindex/skills/skill.md:341-347`,
  `dummyindex/skills/council/52-tree-enrich.md:11-12`,
  `dummyindex/skills/council/52-tree-enrich.md:34-43`).

## Verification seam

`tests/context/domains/test_enrich.py:35-159` covers planning, file grouping,
writeback, unknown IDs and repeated applies. Its CLI checks cover scratch-plan
placement/migration, payload validation and exit behavior
(`tests/context/domains/test_enrich.py:166-296`). The release's shared query-test
changes add no enrichment behavior or new model-quality measurement. Historical
claims that this checkout indexes only foreign benchmark files are no longer
current and are not an architectural dependency.
