# Tree abstract enrichment — concerns

`confidence: INFERRED`

## Data integrity

- `dummyindex/context/domains/enrich.py:214-226`. Apply reads and replaces the whole tree.
  No generation check or project lock exists. Concurrent applies or rebuilds can overwrite each other.
  A stale mapping is checked only for current ID membership.
  Serialize these writes. Replan after backbone changes.
- `dummyindex/context/domains/enrich.py:273-282`. An already-INFERRED node with the identical abstract stays out of the update block.
  Its existing `source-stale` label remains.
  Planning still selects it (`dummyindex/context/domains/enrich.py:116-120`).
  An empty `updated` list alone does not prove stale annotations were cleared.

## Security

- `dummyindex/cli/enrich.py:106-114`, `dummyindex/context/domains/enrich.py:268-284`. An authored update can persist instruction-like or very large prose as an `INFERRED` abstract.
  The boundary validates string types only, not trustworthiness or size.
  Host readers must treat abstracts as repository data, not higher-priority instructions.
  This seam never executes abstract text.
  The confidence label is provenance, not security approval.
- `dummyindex/cli/enrich.py:106-116`, `dummyindex/context/domains/enrich.py:214-226`. The update JSON and current tree are read and parsed without a byte cap or full schema validation.
  Corrupt or oversized owner-supplied artifacts can crash or exhaust this local command.
  Known IDs limit which existing nodes change. Unknown IDs are reported.
  IDs never become filesystem paths.
  No general size or schema guard exists on this read boundary.

## Product surface

- **Batch with one obsolete or typo ID.** Known IDs are written first.
  Then unknown IDs are listed and the CLI exits `1`.
  A nonzero exit can mean partial success, not rollback.
  Apply checks current tree membership, not the worklist generation.
  So the message cannot tell a typo from a renamed ID after rebuild (`dummyindex/context/domains/enrich.py:217-227`, `dummyindex/cli/enrich.py:116-129`).
- **Many small file batches on a large tree.** Each apply rereads and rewrites all of `tree.json`, even when no abstract changes.
  Per-file authoring does not make storage incremental.
  Replanning also replaces the scratch plan.
  Its printed counts are the progress signal. No separate status service exists (`dummyindex/context/domains/enrich.py:207-227`, `dummyindex/cli/enrich.py:44-57`).
- **Invalid or truncated update JSON.** The unguarded parse raises `JSONDecodeError` before the string-map shape check.
  So this input failure prints a traceback, not the exit-2 shape error (`dummyindex/cli/enrich.py:106-114`).
- **Light-mode contradiction.** The phase says it runs in every mode.
  The scope text says light skips.
  Host behavior depends on which instruction it follows.
  The mode-agnostic Python verbs cannot resolve this (`dummyindex/skills/skill.md:341-347`, `dummyindex/skills/council/52-tree-enrich.md:11-12`, `dummyindex/skills/council/52-tree-enrich.md:34-43`).
- **Identical prose for an already-INFERRED stale node.** The abstract and confidence guard reports no update.
  It leaves `source-stale` intact, so the next plan selects the node again.
  A zero update count does not prove stale labels were cleared.
  Changed entries do clear them (`dummyindex/context/domains/enrich.py:116-120`, `dummyindex/context/domains/enrich.py:268-285`).
