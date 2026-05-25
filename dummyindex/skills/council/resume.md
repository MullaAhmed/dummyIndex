# Resumption — pick up where we left off

The council is expensive and can be interrupted. Resumption is built in.

## State sources

Per feature, the skill checks:

1. **`features/<id>/council/_council-log.json`** — the entries log.
2. **`features/<id>/feature.json`** `confidence` field — `INFERRED` means chairman finished.
3. **`features/<id>/.hash`** (optional v0.8+) — aggregate source hash at last council run.

## Skip rules

For a given feature in mode `deep`:

| Condition | Action |
|---|---|
| `confidence: INFERRED` AND source hash unchanged | Skip the entire council |
| `is_stage_complete(feature, 1)` AND mode in (deep, standard) AND source unchanged | Skip stage 1 |
| `is_stage_complete(feature, 2)` AND mode = deep AND source unchanged | Skip stage 2 |
| `is_stage_complete(feature, 3)` | Skip stage 3 (chairman) |
| `latest_status(feature, 4, senior-developer) == complete` | Skip flow refinement |

## Per-agent resumption (within a stage)

Within stage 1 (or stage 2), individual personas may have completed while others failed. Re-running:

```python
for persona in personas_in_mode:
    if latest_status(feature_id, stage=1, agent=persona) == "complete":
        skip
    elif latest_status(feature_id, stage=1, agent=persona) == "failed":
        retry (mark as started)
    else:
        dispatch
```

## What invalidates the skip

Aggregate source hash. If the feature's files have changed since the council ran, **every stage** for that feature re-runs (we don't try to do per-stage hashing — too brittle).

Hash storage: write `features/<id>/.hash` after stage 3 completes:

```bash
sha256(sorted concatenation of every source file's sha256) → features/<id>/.hash
```

On the next run, recompute and compare. Mismatch → full re-council for that feature.

## Forced re-run

`/dummyindex --recouncil` re-runs everything regardless of state.

`/dummyindex --recouncil <feature_id>` re-runs that one feature.

`/dummyindex --recouncil --force` re-runs and ignores hashes.

## What's never skipped

- The structural review pre-stage. Always runs at the start of a non-`--recouncil`-targeted run (unless the user has only 1-2 features).
- `refresh-indexes` after the council. Cheap; always reconciles.

## Failure semantics

If `latest_status(...) == "failed"`:

- The agent will be re-dispatched on the next council run.
- If it fails again, surface to the user — don't loop.
- Three consecutive failures → mark the feature as `confidence: AMBIGUOUS` and move on.

## Audit visibility

`dummyindex context council-log` (no args, v0.8 roadmap) will print a per-feature progress table. For now, agents inspecting `_council-log.json` directly is the only path.
