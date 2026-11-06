## Data integrity

- `dummyindex/context/domains/enrich.py:214-226` — apply reads and replaces the whole current tree without a generation check or project lock. Concurrent applies/rebuilds can overwrite each other's results, and a stale authored mapping is checked only for current ID membership; serialize these writes and replan after backbone changes.
- `dummyindex/context/domains/enrich.py:271-282` — an already-INFERRED node receiving the identical abstract does not enter the update block, so an existing `source-stale` label remains. Such a node continues to be selected by planning (`dummyindex/context/domains/enrich.py:120-123`); an empty `updated` list alone does not prove stale annotations were cleared.

## Security

- `dummyindex/cli/enrich.py:106-114`, `dummyindex/context/domains/enrich.py:268-284` — An authored update can persist instruction-like or very large prose as an `INFERRED` abstract. The boundary validates strings, not their trustworthiness or size; downstream host readers must treat abstracts as repository data rather than higher-priority instructions. This seam does not execute abstract text. The confidence label is provenance, not a security approval.
- `dummyindex/cli/enrich.py:106-116`, `dummyindex/context/domains/enrich.py:214-226` — External update JSON and the current tree are read/parsed without a byte cap or full schema validation, so corrupt or oversized owner-supplied artifacts can crash or exhaust this local command. Known IDs constrain which existing nodes change, and unknown IDs are reported; IDs never become filesystem paths. No general size/schema guard is implemented on this read boundary.

## Product surface

- **Applying a batch with one obsolete/typo ID** — known IDs are written, then
  unknown IDs are listed and the CLI exits 1 — nonzero exit can mean partial
  success, not rollback. Apply checks current tree membership rather than the
  worklist generation, so that message cannot distinguish a typo from a
  renamed ID after rebuild
  (`dummyindex/context/domains/enrich.py:217-227`,
  `dummyindex/cli/enrich.py:116-129`).
- **Applying many small file batches on a large tree** — each apply rereads and
  serializes all of `tree.json`, even when no abstract changes — per-file
  authoring does not make storage incremental. Replanning to inspect remaining
  work also replaces the scratch plan; its printed counts are the delivered
  progress signal, not a separate status service
  (`dummyindex/context/domains/enrich.py:207-227`,
  `dummyindex/cli/enrich.py:44-57`).
- **Passing syntactically invalid or truncated update JSON** — the unguarded
  parse raises `JSONDecodeError` before the friendly string-map shape check —
  this input failure still produces a traceback rather than the shape-error
  exit-2 message (`dummyindex/cli/enrich.py:106-114`).
- **Choosing light mode from current workflow prose** — the phase says it runs
  in every mode while the scope table still says light skips — host behavior
  depends on which instruction is followed; the mode-agnostic Python verbs
  cannot resolve that existing contradiction
  (`dummyindex/skills/skill.md:334-340`,
  `dummyindex/skills/council/52-tree-enrich.md:11-12`,
  `dummyindex/skills/council/52-tree-enrich.md:34-43`).
- **Reauthoring identical prose for an already-INFERRED stale node** — the
  abstract/confidence guard reports no update and leaves `source-stale` intact,
  so the next plan selects the node again — a zero update count does not prove
  stale annotations were cleared; changed entries do clear them
  (`dummyindex/context/domains/enrich.py:116-120`,
  `dummyindex/context/domains/enrich.py:268-285`).
