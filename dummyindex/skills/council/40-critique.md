# Stage 3 — `/critique` (critics file concerns, mode-gated)

> **Parallel dispatch:** the CLI now resolves the critic roster deterministically
> by mode (light = none, standard = `critic-security`, deep = database +
> security + product). See 22-parallel-dispatch.md. The CLI emits one unit per
> (feature, critic). Dispatch them in parallel with the rest of the stage-3
> batch. The mode-relevance pruning below applies only when you re-run a single
> feature by hand (`--recouncil <id>`).

Critics read the **finalised `plan.md`** with one question: *is anything wrong,
missing, or risky?* Each writes its domain section into the shared `concerns.md`.
No essays — bullets and table entries only.

## The three critics

| Persona | Section in `concerns.md` | subagent_type |
|---|---|---|
| `agents/critic-database.md` | `## Data integrity` | `Data Engineer` |
| `agents/critic-security.md` | `## Security` | `Security Engineer` |
| `agents/critic-product.md` | `## Product surface` | `general-purpose` |

## Relevance signals (which critic is relevant, per feature)

> **Batch dispatch does NOT use these signals.** They apply only to manual
> single-feature reruns via `--recouncil <id>`.

- **DBA** if any file matches `*sql*`, `*migrations*`, `*models*`, `*schema*`.
- **Security** if any file matches `*auth*`, `*jwt*`, `*permission*`, `*acl*`,
  or auth-bearing routes.
- **PM** if any file matches `routes/*`, `handlers/*`, `views/*`, `controllers/*`.

## Mode gate

| Mode | Critics that run |
|---|---|
| **light** | none — skip stage 3 entirely. |
| **standard** | exactly one critic — `critic-security` (Security Engineer) — deterministic, no relevance filter, never skipped. |
| **deep** | **all three critics** (database + security + product) + a cross-review pass. |

## Inputs (per critic)

- `features/<id>/plan.md` — the finalised plan (architect's stage 2 output, or
  the dev's draft if stage 2 was skipped/failed).
- The domain source files the plan cites.
- (deep only) `council/10-critiques.md` — the other critics' raw findings.

## Dispatch

For each relevant critic:

1. Read `agents/critic-<domain>.md`. Take `subagent_type` from its frontmatter.
2. Build the prompt: persona body + finalised `plan.md` + the doc-evidence
   directive verbatim.
3. Dispatch `Task`. The critic writes its section into `concerns.md` (via
   `section-write`) and its raw output is snapshotted to
   `council/10-critiques.md`.

## Doc-evidence directive (include verbatim)

> Catalogued prose docs carry `confidence` (high/medium/low) and `broken_refs`.
> Quote only `high`/`medium` after spot-checking each cited identifier against
> `map/symbols.json`. Treat `low` as historical context, never as authority. If
> a doc contradicts the code, the code wins — flag the conflict in the audit
> trail.

## Cross-review (deep only)

After the first critic pass, re-dispatch each critic with the others' raw
findings from `council/10-critiques.md`. Each may flag a peer's finding before
the merged sections land in `concerns.md`.

## Logging

```bash
dummyindex context council-log --feature <id> --stage 3 --agent critic-<domain> --status started
dummyindex context council-log --feature <id> --stage 3 --agent critic-<domain> --status complete
```

## Failure handling

If a critic fails: log it, write whatever sections succeeded, surface the gap in
the Phase 6 report. A missing critic section is not fatal.

## Output

- `features/<id>/concerns.md` — one shared file, organized by domain section.
- `features/<id>/council/10-critiques.md` — raw per-critic findings.
- Log entries.

Next → reality check (`45-reality-check.md`), then flow refinement
(`50-flow-narrative.md`).
