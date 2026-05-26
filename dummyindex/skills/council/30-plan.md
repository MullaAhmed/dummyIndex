# Stage 2 — `/plan` (architect reorganises plan.md)

The architect reads the dev's draft `plan.md` and restructures it in place. One
author, one artifact. Runs after stage 1, skipped in `light` mode.

## Inputs (per feature)

- `features/<id>/plan.md` — the dev's draft (already snapshotted to
  `council/01-dev-draft.md` in stage 1).
- `feature.json` + the source files the plan cites.
- `architecture/overview.md` — the deterministic top-level layout.

## Reasoning mode (Sequential Thinking)

The revision is a judgment call, so when available it runs as explicit revisable
steps:

> If your runtime exposes `mcp__sequentialthinking_*`, dispatch this stage with
> `mcp__sequentialthinking_sequentialthinking__sequentialthinking`: **identify**
> what to sharpen in the dev's draft → **propose** changes → **check** each
> against `map/symbols.json` (does the symbol exist with that signature?) →
> **revise**. Otherwise fall back to single-shot reasoning. The `.context/`
> artifacts have the same shape either way — only the quality of the reasoning
> changes.

The step-by-step audit trail lands in `council/02-architect-notes.md` (below),
whether or not the MCP ran.

## Dispatch

Single Task subagent. Read `subagent_type` from `agents/architect.md`
frontmatter — it's `Backend Architect`. Build the prompt: the architect persona
body + the draft `plan.md` + the doc-evidence directive verbatim.

The architect's mandate (full detail in `agents/architect.md` Job B):

- Sharpen bounded context; strip non-load-bearing detail.
- Name patterns explicitly (repository, dispatcher, port/adapter, …).
- Make dependencies visible (upstream / downstream / cycles).
- Promote unstated decisions into explicit "decided X because Y".
- Cut filler.

## Doc-evidence directive (include verbatim)

> Catalogued prose docs carry `confidence` (high/medium/low) and `broken_refs`.
> Quote only `high`/`medium` after spot-checking each cited identifier against
> `map/symbols.json`. Treat `low` as historical context, never as authority. If
> a doc contradicts the code, the code wins — flag the conflict in the audit
> trail.

## What the architect writes

1. Revised `plan.md` (overwrites the dev draft) via
   `dummyindex context section-write --feature <id> --section plan --from-file <tmp>`.
2. `features/<id>/council/02-architect-notes.md` — what changed and why.

The dev's `spec.md` is left untouched.

## Logging

```bash
dummyindex context council-log --feature <id> --stage 2 --agent architect --status started
dummyindex context council-log --feature <id> --stage 2 --agent architect --status complete
```

## Skip logic

- Mode = `light`: skip entirely — `plan.md` stays as the dev's draft.
- `latest_status(<id>, stage=2, agent=architect) == complete` AND source
  unchanged → skip.

## Failure handling

If the architect fails: the dev's `plan.md` survives as the finalised plan; log
the failure and proceed to stage 3 (critics read whatever `plan.md` exists).

## Output

- Revised `features/<id>/plan.md`.
- `features/<id>/council/02-architect-notes.md`.
- Log entries.

Next → `40-critique.md`.
