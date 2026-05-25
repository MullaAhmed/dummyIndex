# Flow refinement — keep, discard, narrate

Run **after** stages 1-3 complete for a feature. The senior dev decides which flows are real and writes narratives for them.

## Why this is separate from stages 1-3

Stage 1-3 produce the **feature-level** docs. Flows are sub-units. Many deterministic flows are noise (private helpers, enum classes, broad traces) and should be removed entirely rather than reviewed by 5 personas.

The senior dev is the right judge of "is this a real flow?" — they've already written `implementation.md` in stage 3 and know what business logic looks like in this feature.

## Inputs (per feature)

- `feature.json` — the list of `flow_ids`.
- Every `flows/<flow_id>.json` for this feature.
- The entry-point source for each flow.

## Dispatch

Single Task subagent per feature. Read `subagent_type` from `agents/senior-developer.md` frontmatter — it's `Senior Developer`. Pass the flow-refinement-specific prompt below:

> You are the **Senior Developer**, refining flows for feature `<feature_id>`.
> 
> Below are the deterministic flows detected for this feature. For each, decide **keep** or **discard**.
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
> For each `flow_id`:
> 
> **Discard:**
> ```bash
> dummyindex context flow-remove --feature <feature_id> --flow <flow_id>
> ```
> 
> **Keep:** overwrite `features/<feature_id>/flows/<flow_id>.md` with a real narrative. Use the structure in `agents/senior-developer.md` (entry / trigger / step-by-step / return / failure modes).
> 
> Log each decision:
> ```bash
> dummyindex context council-log \
>   --feature <feature_id> --stage 4 --agent senior-developer \
>   --status complete --note "kept flow-001 (login), discarded flow-002 (enum), …"
> ```

## Expected reduction

On the user's NEW-BOS/backend with 75 deterministic flows: expect 15–25 to survive. The rest are private helpers, enum classes, and BFS over-reach.

The senior dev's `implementation.md` (from stage 3) often **references** the kept flow IDs by their narrative title, so this stage closes the loop.

## Logging

```bash
dummyindex context council-log --feature <id> --stage 4 --agent senior-developer --status complete
```

## Skip logic

- Mode = `light`: skip flow refinement entirely. Keep all deterministic flows (noisy but no LLM cost).
- Otherwise: run.
- If `latest_status(<id>, stage=4, senior-developer) == "complete"` and feature hash unchanged: skip.

## Output

- Reduced `flow_ids` in `feature.json`.
- Updated `INDEX.json` flow counts.
- Updated `graph.json` (flow nodes for discarded flows removed).
- Narrated `flows/<id>.md` for kept flows.
- One log entry per feature.
