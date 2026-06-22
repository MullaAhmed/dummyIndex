# How to navigate `features/`

This folder is the **feature-oriented** view of the codebase. Use it
when the user asks about behavior ("how does login work?", "what
happens on checkout?") rather than about symbols.

## Read in this order

1. **`INDEX.json`** — the machine-readable list of features. Each
   entry has `feature_id`, `name`, `path`, and summary counts. Start
   here; it's much smaller than walking every folder.
2. **`<feature-id>/feature.json`** — canonical description of one
   feature: members (symbol node_ids), files, entry_points, and a
   `flow_ids` list pointing into `flows/`.
3. **`<feature-id>/flows/<flow-id>.json`** — an ordered call sequence
   from a single entry point. Each step has `node_id`, `label`,
   `path`, `range`, and `depth`. Use this when the user wants the
   sequence of calls that implements a particular flow.
4. **`<feature-id>/spec.md`** (entry) / **`plan.md`** /
   **`concerns.md`** / **`flows/<flow-id>.md`** — human prose.
   `spec.md` is the entry point (what the feature does); `plan.md`
   covers how it's built; `concerns.md` records risks/gaps. After
   the `/dummyindex` skill enriches, these become the primary docs
   for someone reading without an agent.

## Cross-reference with `tree.json` and `map/`

Every `node_id` in feature / flow JSON also appears in
`../tree.json` and `../map/symbols.json` — use those to resolve a
node to its exact source range when reading code.

## Confidence

Every feature / flow has a `confidence` field. `EXTRACTED` means
deterministic (graph communities, BFS traces). `INFERRED` means an
LLM (the Claude session running the `/dummyindex` skill) rewrote
the name / summary / narrative based on actual source.

## Don't grep `features/`

Always start from `INDEX.json` and walk by `feature_id` /
`flow_id`. Folder names may be renamed by enrichment; the
`feature_id` in JSON is stable.
