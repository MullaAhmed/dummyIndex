# Stage 2 — Anonymized cross-review

Each persona reviews the other four — but author identity is stripped. Inspired by [llm-council](https://github.com/karpathy/llm-council)'s peer-ranking stage.

## Why anonymized

Personas tend to defer to roles they perceive as authoritative ("the architect probably knows best"). Anonymization forces the review to be content-grounded, not deference-driven.

## Inputs (per feature)

The 5 stage-1 outputs:

- `council/01-architect.md`
- `council/02-senior-developer.md`
- `council/03-database-engineer.md`
- `council/04-security-analyst.md`
- `council/05-product-manager.md`

## Dispatching

For each persona, build an **anonymized review prompt**:

1. Read their own persona instructions (`skills/agents/<persona>.md`).
2. Read the 4 *other* perspectives.
3. Map them to `Perspective A`, `B`, `C`, `D` in a stable but anonymous order.
4. The mapping is recorded in a private file `council/_review-key.json` (gitignored) so the chairman can de-anonymize during stage 3.
5. Build the prompt:

> You are the **<persona name>** in this council. Below are four other perspectives on this feature, anonymized as Perspective A, B, C, D.
> 
> Write a section titled `## <Your persona> 's review of peers` and append it to `features/<id>/council/10-reviews.md` (append, don't overwrite).
> 
> For each of A, B, C, D:
> 
> ```markdown
> ### Perspective A
> - **Agrees:** <a specific claim of theirs you can verify in source, with `path:range`>
> - **Disagrees:** <a specific claim you'd argue with, with counter-evidence>
> - **Gap:** <a domain-specific point your role would expect them to cover, that they missed>
> ```
> 
> Be concrete. **Quote `path:range` for every claim, agreement or disagreement.**
> 
> The other perspectives follow:
> 
> --- PERSPECTIVE A ---
> <content of perspective A>
> --- PERSPECTIVE B ---
> ...

## Dispatch all 5 in parallel — using each persona's specialist subagent_type

Each persona reviews the other 4 simultaneously. Read `subagent_type` from the persona's frontmatter; dispatch with that type. The Task tool calls:

```
Task(prompt=architect_review_prompt,   subagent_type="Backend Architect")
Task(prompt=senior_dev_review_prompt,  subagent_type="Senior Developer")
Task(prompt=dba_review_prompt,         subagent_type="Data Engineer")
Task(prompt=security_review_prompt,    subagent_type="Security Engineer")
Task(prompt=pm_review_prompt,          subagent_type="general-purpose")
```

(5 reviewers total, each reviewing the 4 they didn't write — that's 5 parallel calls.)

Specialist subagents are what the persona's frontmatter declares. Their domain reflexes apply during the cross-review too — the security agent will spot a security gap the architect missed, the DBA will catch a transaction issue the senior dev waved past.

## Append semantics

Each reviewer appends to the same `council/10-reviews.md`. The file structure ends up:

```markdown
# Cross-review

## Architect's review of peers
…

## Senior Developer's review of peers
…

## Database Engineer's review of peers
…

## Security Analyst's review of peers
…

## Product Manager's review of peers
…
```

The personas are not anonymized **in the section headers** — only in the perspectives they're reviewing. The chairman reads the de-anonymized version (using `_review-key.json`).

## Skip logic

- Mode = `light`: skip entirely.
- Mode = `standard`: skip entirely.
- Mode = `deep`: run.
- `latest_status(feature_id, stage=2, agent=<persona>) == "complete"`: skip that reviewer.

## Failure handling

If a reviewer fails, log it. The chairman in stage 3 will see the missing reviewer's section and note it as an unresolved gap.

## Output

- `features/<id>/council/10-reviews.md` (consolidated)
- `features/<id>/council/_review-key.json` (gitignored — the de-anonymization map)
- Log entries for each (stage=2, agent=<persona>) pair.

Next step → `40-stage3-synthesis.md`.
