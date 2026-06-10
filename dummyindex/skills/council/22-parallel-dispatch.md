# Parallel dispatch — the council batch loop

The per-feature pipeline runs **in parallel across features**, not one feature
at a time. Features are independent (each writes only to its own
`features/<id>/` tree), so the council dispatches a whole batch of agents
concurrently, waits, and advances.

## The loop

```
loop:
  batch = dummyindex context council-batch --next --cap 8 --mode <mode> [--tree-enrich] --json
  if batch.complete: break
  # dispatch ONE Task per unit in batch.units, ALL IN ONE MESSAGE, so they run concurrently:
  #   - subagent_type   = unit.subagent_type
  #   - inline the persona body: agents/dev.md (role "dev"), agents/architect.md
  #     (role "architect"), or agents/<role>.md (critics, e.g. critic-security.md)
  #   - fill {{framework}} with unit.framework for dev units
  #   - ground each agent: read spec.md / plan.md / .context/conventions/ first
  #   - each agent logs itself: council-log --feature <id> --stage <unit.stage>
  #     --agent <unit.role> --status started|complete (or failed)
  await ALL units (barrier)
repeat
```

## Stages (what the CLI returns, in order)

1 specify (dev) · 2 plan (architect) · 3 critique (critics, mode-rostered) ·
4 flow (dev) · 5 tree-enrich (dev, only when `--tree-enrich`). The CLI returns
the **earliest incomplete stage** across all features and never advances a
feature to stage N+1 until stage N is logged complete for it — so intra-feature
ordering is preserved while cross-feature work runs in parallel.

## Critic roster (deterministic, mode-gated)

- **light** — no critique stage.
- **standard** — one critic: `critic-security` (Security Engineer).
- **deep** — `critic-database` (Data Engineer), `critic-security`
  (Security Engineer), `critic-product` (general-purpose).

The CLI emits one unit per (feature, critic), so the cap bounds **agents**.

## Failure isolation

Features are independent. If one unit fails, log it
(`--status failed`), **leave that feature at its stage, and keep going** — finish
the rest of the batch and all later batches. Do **not** stop the whole council
(that is the build loop's gate, which is wrong here). At the end, **report the
features that never reached completion** so the user can re-run — a re-run
resumes exactly those, because the frontier is recomputed from the logs.

## Resumption

`--next` is stateless beyond the per-feature `_council-log.json`: it recomputes
the frontier every call. An interrupted run resumes with no special handling —
just call `--next` again.
