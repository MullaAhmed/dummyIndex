# Stage 1 — Independent perspectives

Five personas read the feature **in parallel**. Each writes one stage-1 markdown.

## Inputs (per feature)

For each feature in `features/INDEX.json` (post-structural-review):

- `feature.json`
- Source files listed under `files` (or a sample if >15 files — pick the largest 8 + entry points)
- `tree.json` (just the subtree under each file in this feature)
- `map/symbols.json` (filtered to this feature's members)
- `features/symbol-graph.json` (filtered to this feature's nodes)

## Dispatching

For each persona — Architect, Senior Developer, Database Engineer, Security Analyst, Product Manager:

```
persona_md = read("skills/agents/<persona>.md")
subagent_type = persona_md.frontmatter["subagent_type"]   # e.g. "Backend Architect"

Task subagent (subagent_type) {
  feature context = {
    "feature.json": <content>,
    "source_files": [path1, path2, ...],   # paths only, agent will Read them
    "flow_ids": [...],                      # let agent decide which flows to read
    "stage": 1,
    "feature_id": <id>,
  }
  full prompt = persona_md.body + "\n\n## Feature context\n\n" + feature context
  
  output: write to features/<id>/council/0N-<persona>.md
  log: dummyindex context council-log --stage 1 --agent <persona> --status started|complete
}
```

**Dispatch all 5 in parallel** via a single message with 5 Task tool calls — each with its persona's specialist `subagent_type`. This is the cost win — five 30K-token context windows in parallel beats one 150K sequentially.

The mapping (from each persona's frontmatter):

- Architect          → `Backend Architect`
- Senior Developer   → `Senior Developer`
- Database Engineer  → `Data Engineer`
- Security Analyst   → `Security Engineer`
- Product Manager    → `general-purpose` (no PM-specific type)

## Skip logic

For each (persona, feature) pair, check `_council-log.json`:

```python
if latest_status(feature_id, stage=1, agent=persona) == "complete":
    # And feature hash unchanged
    skip
```

## Failure handling

If a persona returns `failed` or its output file is missing:

1. Log the failure.
2. Continue with the other 4 personas (don't block stage 2 on one missing perspective).
3. Surface to the user after the run: "X persona failed for feature Y; re-run with `--recouncil <feature_id>`."

## Cost guards

- Cap source file read per persona at ~5 files for features with > 15 source files.
- If `feature_id` is in the trivial-filter list (see `filter-trivial.md`), skip stage 1 entirely.

## Verification

After all 5 personas return, the skill verifies each output file exists:

```
features/<id>/council/01-architect.md       ✓
features/<id>/council/02-senior-developer.md ✓
features/<id>/council/03-database-engineer.md ✓
features/<id>/council/04-security-analyst.md  ✓
features/<id>/council/05-product-manager.md   ✓
```

Missing files → log a stage-1 failure for that persona.

## Mode handling

- **deep**: all 5 personas (default).
- **standard**: architect + 1 relevance-picked specialist:
  - DBA if any file matches `*sql*`, `*migrations*`, `*models*`, `*schema*`.
  - Security if any file matches `*auth*`, `*jwt*`, `*permission*`, `*acl*`, `routes/*`.
  - PM if any file matches `routes/*`, `handlers/*`, `views/*`, `controllers/*`.
  - Else: architect alone.
- **light**: no stage 1.

## Output

Per feature, up to 5 files under `features/<id>/council/`. Plus log entries.

Next step → `30-stage2-cross-review.md`.
