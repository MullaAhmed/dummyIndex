# Structural review (pre-stage)

Runs **once** before per-feature councils start. The architect looks at the whole feature set and proposes regrouping. Bad communities → split. Overlapping communities → merge.

## When to run

- First-time `/dummyindex` on a repo.
- After `--recouncil` if `features-rename` hasn't been called manually.
- Skip if `features/INDEX.json` has only 1–2 features (nothing to regroup).

## Inputs

- `.context/features/INDEX.json` — full feature list.
- `.context/features/<id>/feature.json` for every feature — members, files, entry points.
- `.context/features/symbol-graph.json` — raw call graph.
- Sample source files from the top-3 largest features (for grounding).

## Reasoning mode (Sequential Thinking)

Regrouping is the architect's biggest judgment call, so when available it runs as
explicit revisable steps:

> If your runtime exposes `mcp__sequentialthinking_*`, dispatch this stage with
> `mcp__sequentialthinking_sequentialthinking__sequentialthinking`: **draft** a
> regrouping plan → **cross-check** each merge/split against the communities in
> `features/symbol-graph.json` → **revise** → **emit**. Otherwise fall back to
> single-shot reasoning and emit the plan directly. The `.context/` artifacts
> have the same shape either way — only the quality of the reasoning changes.

Log each revision step to `.context/features/_structural-log.json` (the synthetic
log file named under **Log**, below) so the regrouping is auditable. This is the
*revision* audit trail — distinct from per-feature `_council-log.json` status
logging, which this pre-stage does not write (there's no feature folder yet).

## Dispatch

Single Task subagent, persona = `agents/architect.md`.

Prompt template:

> You are the **Architect**, performing a structural review (pre-stage).
> 
> Read all `feature.json` files under `.context/features/`. For each feature with `member_count > 20`, also read a sample (3–5 files) of its source.
> 
> Then propose a regrouping plan. **Merge** features that share >50% of their members or files. **Split** features where the member set contains >2 distinct subdomains.
> 
> Emit a JSON regrouping plan in this exact shape:
> 
> ```json
> {
>   "renames": [
>     {
>       "from": "community-0",
>       "to": "<slug>",
>       "name": "<Human Name>",
>       "summary": "<one sentence>"
>     }
>   ],
>   "merges": [
>     {
>       "into": "<existing or new slug>",
>       "from": ["community-X", "community-Y"],
>       "name": "<Human Name>",
>       "summary": "<one sentence>",
>       "rationale": "<why these belong together>"
>     }
>   ],
>   "splits": [
>     {
>       "from": "community-Z",
>       "rationale": "<why splitting>",
>       "note": "leider can't actually split yet — flag the split for human follow-up"
>     }
>   ]
> }
> ```
> 
> Write the plan to `.context/features/_structural-plan.json`.
> 
> If no regrouping is warranted, write `{"renames": [], "merges": [], "splits": []}`.

## Apply the plan

After the architect returns:

```bash
# For each rename
for r in plan.renames:
    dummyindex context features-rename \
        --from "$r.from" --to "$r.to" \
        --name "$r.name" --summary "$r.summary"

# For each merge — first rename all sources to the target id, then dedupe
# (current limitation: merges only update metadata; members aren't unioned
# automatically — flag for human review)
for m in plan.merges:
    log: "Merge proposed: $m.from -> $m.into. Requires manual member union."
```

**Splits are deferred to v0.8** — for now we surface them as warnings, not apply them.

## What about a fresh `community-N`?

If Leiden created an entirely junk community (e.g., 1 file, 0 entry points, no semantic coherence), the architect should propose renaming it to `utils-<dirname>` or similar — clearly marking it as a non-feature.

## Log

```bash
dummyindex context council-log --feature _structural-review --stage 0 --agent architect --status complete
```

(Yes, `_structural-review` is a synthetic feature id used only for logging this pre-stage. The CLI won't accept it because there's no folder — log manually to a global file `.context/features/_structural-log.json` instead.)

For the **status** of this pre-stage: just `print` the plan applied and skip the
per-stage `council-log` call (there's no feature folder to log into). But when
sequential-thinking ran, **do** append its revision steps to
`.context/features/_structural-log.json` — that file is the regrouping's audit
trail, not a status log. When the MCP isn't available there are no revision steps
to record, so the file may be absent; that's fine.

## Output

`.context/features/_structural-plan.json` (kept for audit; gitignored if you want it ephemeral).

After this stage, `features/INDEX.json` reflects the regrouped state. Per-feature councils proceed against the new feature IDs.
