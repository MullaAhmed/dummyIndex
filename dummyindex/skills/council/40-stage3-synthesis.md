# Stage 3 — Chairman synthesis

The chairman reads everything and writes the canonical docs. This is the **sequential** stage — it depends on stages 1 + 2 being complete.

## Inputs (per feature)

- All 5 `council/0N-<persona>.md` files (stage 1).
- `council/10-reviews.md` (stage 2).
- `council/_review-key.json` (the de-anonymization map).
- `feature.json`.
- The source files (chairman may spot-check disputed claims).

## Dispatch

Single Task subagent. Read `subagent_type` from `agents/chairman.md` frontmatter — it's `Agents Orchestrator`. That subagent is purpose-built for multi-agent synthesis.

Prompt template:

> You are the **Chairman**. Synthesize the council's work for feature `<feature_id>`.
> 
> ## Inputs you have
> 
> The five stage-1 perspectives, plus the cross-review matrix (de-anonymized below).
> 
> --- 01-ARCHITECT.md ---
> <content>
> 
> --- 02-SENIOR-DEVELOPER.md ---
> <content>
> 
> (… etc through 05-product-manager.md and 10-reviews.md, with key applied)
> 
> ## Your output
> 
> Write **six markdown files** to disk via `dummyindex context section-write`:
> 
> 1. `README.md` — the synthesized overview.
> 2. `architecture.md` — architect's section, refined.
> 3. `implementation.md` — senior dev's section, refined.
> 4. `data-model.md` — DBA's section, refined.
> 5. `security.md` — security's section, refined.
> 6. `product.md` — PM's section, refined.
> 
> And write **one audit file directly**: `council/20-chairman.md`.
> 
> See `skills/agents/chairman.md` for the required structure of each.
> 
> ## Synthesis discipline
> 
> - Where the cross-review surfaced agreement, integrate.
> - Where it surfaced a contradiction:
>   - Spot-check against the source.
>   - If resolvable, take the better-grounded view.
>   - If not, document both views in `README.md`'s "Open questions".
> - Cite `path:range` when settling a dispute.
> - Quote the source, not the perspectives.
> 
> ## When done
> 
> Log: `dummyindex context council-log --feature <id> --stage 3 --agent chairman --status complete`.

## Atomic section writes

The chairman uses the section-write CLI for each domain doc:

```bash
# Build a tmp file with the architecture section
echo "..." > /tmp/architecture.md

# Atomic placement
dummyindex context section-write \
    --feature <id> --section architecture --from-file /tmp/architecture.md
```

`README.md` and `20-chairman.md` go through `Write` directly (no atomic-rename needed for those — they're not load-bearing for other agents during this run).

## Skip logic

- Mode = `light`: chairman runs without stages 1/2 (writes a minimal README from feature.json + source samples only).
- Otherwise: chairman waits for stages 1 + 2 to be `complete` (or stage 1 only if mode = `standard`).

## Failure handling

If the chairman fails:
- The 5 perspectives + review survive on disk.
- Re-run with `/dummyindex --recouncil <feature_id>` resumes from stage 3.
- The chairman is the only sequential step — re-running is cheap.

## Reality check (optional)

Before publishing, the chairman may dispatch a **Reality Checker** subagent. Claude Code ships a purpose-built `Reality Checker` subagent_type — use it directly:

```
Task(
  subagent_type="Reality Checker",
  prompt="Verify each claim below against the source files. Output: red/green for each.\n\nClaims:\n  1. 'foo() calls bar()' — verify in source.\n  2. ...",
)
```

Verified claims stay `INFERRED`. Failed claims get demoted to `AMBIGUOUS` in the published doc and noted in `README.md` open questions.

This is optional and roadmap'd for v0.8 — not required for v0.7.

## Output

- `README.md`, `architecture.md`, `implementation.md`, `data-model.md`, `security.md`, `product.md` — the canonical docs.
- `council/20-chairman.md` — the synthesis audit.
- Updated `feature.json` `confidence: INFERRED` and `summary` field.
- Log entry: stage 3, agent chairman, status complete.

After this, the feature is **fully enriched**. Move to flow refinement (`50-flow-narrative.md`).
