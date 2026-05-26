# Flow refinement — keep, discard, narrate

Run **after** stages 1-3 complete for a feature. The **same dev** that authored
the feature's `spec.md` + `plan.md` decides which flows are real and narrates
them. There is no separate flow persona.

## Why this is owned by the dev

The dev has already written `spec.md` + `plan.md` for this feature and knows what
business logic looks like here. Many deterministic flows are noise (private
helpers, enum classes, broad traces) and should be removed rather than narrated.

## Inputs (per feature)

- `feature.json` — the list of `flow_ids`.
- Every `flows/<flow_id>.json` for this feature.
- The entry-point source for each flow.

## Dispatch

Single Task subagent per feature, dispatched as the **same dev** that ran stage 1.
Resolve the `subagent_type` exactly as stage 1 did:

```bash
dummyindex context dev-pick --feature <id>
```

Dispatch with the returned `subagent_type` (fallback `Senior Developer`). Pass
the flow-refinement prompt below; the full discard criteria + narrative template
live in `agents/dev.md`.

> You are the **{{framework}} dev**, refining flows for feature `<feature_id>`.
>
> Below are the deterministic flows detected for this feature. For each, decide
> **keep** or **discard**.
>
> ## Discard criteria
>
> - Entry point is a private helper (`_`-prefixed) — discard.
> - Entry point is an enum class or type alias — discard.
> - Trace is 1 step (no meaningful sequence) — discard.
> - Trace is > 100 steps across many files — discard (mis-detected breadth).
> - The sequence is trivial getter/setter chaining — discard.
>
> ## Action
>
> **Discard:**
> ```bash
> dummyindex context flow-remove --feature <feature_id> --flow <flow_id>
> ```
>
> **Keep:** overwrite `features/<feature_id>/flows/<flow_id>.md` with a
> one-paragraph narrative (entry / trigger / step-by-step / return / failure
> modes — see `agents/dev.md`).
>
> Log each decision:
> ```bash
> dummyindex context council-log \
>   --feature <feature_id> --stage 4 --agent dev \
>   --status complete --note "kept flow-001 (login), discarded flow-002 (enum), …"
> ```

## Expected reduction

On a backend with ~75 deterministic flows: expect 15–25 to survive. The rest are
private helpers, enum classes, and BFS over-reach.

The dev's `plan.md` (from stage 1, architect-revised in stage 2) often
**references** the kept flow IDs by their narrative title, so this stage closes
the loop.

## Logging

```bash
dummyindex context council-log --feature <id> --stage 4 --agent dev --status complete
```

## Skip logic

- Mode = `light`: skip flow refinement entirely. Keep all deterministic flows
  (noisy but no LLM cost).
- Otherwise: run.
- If `latest_status(<id>, stage=4, dev) == complete` and feature hash unchanged:
  skip.

## Output

- Reduced `flow_ids` in `feature.json`.
- Updated `INDEX.json` flow counts.
- Updated `graph.json` (flow nodes for discarded flows removed).
- Narrated `flows/<id>.md` for kept flows.
- One log entry per feature.
