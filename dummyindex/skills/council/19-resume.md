# Resumption — pick up where we left off

The council is expensive and can be interrupted. Resumption is built in.

## State sources

Per feature, the skill checks:

1. **`features/<id>/council/_council-log.json`** — the entries log.
2. **`features/<id>/feature.json`** `confidence` field — `INFERRED` means the
   pipeline finished.
3. **`features/<id>/.hash`** — aggregate source hash at last council run.

## Stages

Numeric, sequential: specify = stage 1, plan = stage 2, critique = stage 3.

## Skip rules

For a given feature:

| Condition | Action |
|---|---|
| `confidence: INFERRED` AND source hash unchanged | Skip the entire pipeline |
| `is_stage_complete(feature, 1)` AND source unchanged | Skip `/specify` |
| `is_stage_complete(feature, 2)` AND mode in (standard, deep) AND source unchanged | Skip `/plan` |
| `is_stage_complete(feature, 3)` AND source unchanged | Skip `/critique` |
| `latest_status(feature, 4, dev) == complete` | Skip flow refinement |

## Per-agent resumption (within stage 3)

In `deep` mode, several critics run at stage 3. Individual critics may have
completed while others failed. Re-running:

```python
for critic in relevant_critics_in_mode:
    if latest_status(feature_id, stage=3, agent=critic) == "complete":
        skip
    elif latest_status(feature_id, stage=3, agent=critic) == "failed":
        retry (mark as started)
    else:
        dispatch
```

## What invalidates the skip

Aggregate source hash. If the feature's files have changed since the council
ran, **every stage** for that feature re-runs (no per-stage hashing — too
brittle).

Hash storage: write `features/<id>/.hash` after stage 3 completes:

```bash
sha256(sorted concatenation of every source file's sha256) → features/<id>/.hash
```

On the next run, recompute and compare. Mismatch → full re-council for that
feature.

## Forced re-run

`/dummyindex --recouncil` re-runs everything regardless of state.

`/dummyindex --recouncil <feature_id>` re-runs that one feature.

`/dummyindex --recouncil --force` re-runs and ignores hashes.

## What's never skipped

- The structural review pre-stage. Always runs at the start of a
  non-`--recouncil`-targeted run (unless the user has only 1–2 features).
- `refresh-indexes` after the council. Cheap; always reconciles.

## Failure semantics

If `latest_status(...) == "failed"`:

- The agent is re-dispatched on the next council run.
- If it fails again, surface to the user — don't loop.
- Three consecutive failures → mark the feature `confidence: AMBIGUOUS` and move
  on.

## Audit visibility

Agents inspecting `_council-log.json` directly is the path to a per-feature
progress view.

## Resumption under parallel dispatch

`council-batch --next` recomputes the earliest incomplete stage from the
per-feature logs on every call, so resuming an interrupted parallel run needs no
special handling — re-run the loop in 22-parallel-dispatch.md and it picks up at
the exact stage each feature stopped.
