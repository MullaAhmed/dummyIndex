# Parallel council dispatch — design

**Date:** 2026-06-10
**Version target:** 0.20.0 (minor — new feature + new public CLI verb)
**Status:** approved (brainstorming) → ready for implementation plan

## Problem

The `.context/` build pipeline runs a lot of *independent* LLM work
**sequentially**. The council overview (`skills/council/00-overview.md`) states
the rule plainly:

> Phase 2: Per-feature pipeline (**loop over features, SEQUENTIAL per feature**)

On a 14-feature repo the council processes all 14 features one after another,
even though no feature depends on another. Wall-clock cost scales linearly with
feature count when it could scale with `feature_count / concurrency`.

This is the user's actual complaint: *"a lot of stuff which could be done by
parallel Claude agents is done sequentially."* It is not about the deterministic
tree-sitter extraction (pure CPU; Claude subagents cannot speed that up) and not
about the build loop (already parallel).

## What is already parallel (no work)

Recorded here so the scope is unambiguous:

- **`/dummyindex-build`** — dispatches each wave's items concurrently via parallel
  Task calls in one message, verify-before-tick, waves gated in order
  (`skills/build/SKILL.md`). As parallel as correctness allows; cross-wave
  serialism encodes real dependencies. **No change.**
- **`/dummyindex-plan` critique panel** — 3 critics dispatched in parallel.
  **No change.**
- **`/dummyindex-audit` panel** — 2–5 auditors in parallel per debate round.
  **No change.**

## The one real bottleneck: the council per-feature loop

Within a single feature the three stages are genuinely ordered — a real data
dependency:

1. **specify** (dev) → `spec.md` + `plan.md`
2. **plan** (architect) → reorganises `plan.md`, needs the dev's draft
3. **critique** (critics) → `concerns.md`, needs the finalised `plan.md`

…followed by **flow refinement** (Phase 3) and **tree enrichment** (Phase 3.5),
both per-feature.

**Across features there is no dependency at all.** And the storage layout proves
it is race-free to parallelise: every feature writes *only* to its own
`features/<feature_id>/` tree — `spec.md`, `plan.md`, `concerns.md`, and
`council/_council-log.json` are all per-feature (`context/domains/council.py`).
There is zero shared mutable state across features.

## Approach (chosen): CLI-driven stage batches — the council twin of `--next-wave`

Replace the sequential `for feature in features` loop with a `--next-batch` loop
that mirrors the build loop's proven `--next-wave` mechanism. The deterministic
CLI is the **state machine**; the Claude session is the **conductor** that
dispatches and the agents do the work. The CLI never runs an agent.

### The loop the skill follows

```
loop:
  batch = dummyindex context council-batch --next --cap 8 --json   # deterministic, no LLM
  if batch.complete: break
  # dispatch every unit in `batch` IN PARALLEL — one Task call per unit, all in one message:
  #   - subagent_type per unit (from the batch payload)
  #   - persona body inlined (agents/<persona_id>.md), framework slot filled
  #   - grounded: read spec.md / plan.md / .context/conventions/ first
  #   - each agent calls `council-log ... --status started|complete` itself
  await all (barrier)
  # failure isolation: a failed unit stays at its stage; record it, do NOT stop the loop
repeat
# at the end: report any features that never reached completion
```

### How `council-batch --next` computes a batch (deterministic)

1. Enumerate non-trivial features from `features/INDEX.json`, minus trivial ones
   (`18-filter-trivial.md` rules) and minus features whose work is complete and
   whose source is unchanged (existing resume logic — `is_stage_complete` +
   source mtime).
2. Find the **earliest incomplete stage `S`** across all remaining features
   (exactly analogous to build's "earliest incomplete wave"). Stage order:
   `1 specify → 2 plan → 3 critique → 4 flow → 5 tree-enrich`.
3. Gather the features that need stage `S` **and whose stage `S-1` is logged
   complete**, flatten to **dispatch-units** (see below), and return up to
   `--cap` units. Annotate each unit with its resolved `subagent_type`,
   `persona_id`, `framework`, and grounding paths.
4. When no feature has an incomplete stage, return `{ "complete": true }`.

Because `S` is recomputed from the per-feature logs on every call, **resumption
is automatic** — an interrupted run resumes at the exact stage it stopped, with
no new state introduced.

### Dispatch-unit, and why the cap counts agents not features

A **dispatch-unit** is one Task-tool agent invocation:

- Stages 1, 2, 4, 5 → one unit per feature.
- Stage 3 (critique) → in `deep` mode a feature spawns multiple critics, so it is
  **one unit per (feature, critic)**. Mode-gating (`light`/`standard`/`deep`)
  decides how many critics per feature, unchanged from `40-critique.md`.

`--cap` bounds **concurrent agents** (default 8), so a 40-feature `deep` run
cannot dispatch 120 agents in one message. The CLI returns ≤ `cap` units; the
loop calls `--next` again for the next slice of the same stage.

### subagent_type resolution (unchanged mapping, reused)

- Stage 1 (specify) & Stage 4 (flow) → per-feature via existing
  `dummyindex context dev-pick --feature <id>` (Backend Architect / Frontend
  Developer / Data Engineer / AI Engineer / Senior Developer; fallback Senior
  Developer). Heterogeneous within a batch — each Task call gets its own type.
- Stage 2 (plan) → `Backend Architect`.
- Stage 3 (critique) → fixed map: database→Data Engineer, security→Security
  Engineer, product→general-purpose; mode-gated set.
- Stage 5 (tree-enrich) → per `52-tree-enrich.md`, mode-gated.

### Failure handling — isolate & continue (decided)

Features are independent, so unlike the build loop (which *gates* a wave on any
failure), the council **isolates**: a failed unit is logged
(`--status failed`), its feature stays at the incomplete stage, the rest of the
batch and all later batches proceed, and the conductor **reports the failed
features at the end**. One feature's critic dying must never block thirteen
others.

### Out of scope / unchanged

- **Phase 1 structural review** stays a single serial architect — it regroups
  features and must gate Phase 2. No change.
- **Deterministic extraction / graph build** — pure CPU; not touched here.
- **Build / plan / audit** — already parallel; not touched.

## Components

| Component | Type | Responsibility |
|---|---|---|
| `context/domains/council_batch.py` | new, pure | Compute earliest-incomplete-stage, gather ≤cap dispatch-units, annotate with subagent_type/persona/framework/grounding. No I/O beyond reading logs + index. Deterministic. |
| `cli/council_batch.py` | new, wire-only | `context council-batch --next [--cap N] [--mode ...] [--root DIR] [--json]`. Parses nothing of substance; calls the domain; prints. Models on `cli/build_loop/waves.py`. |
| `cli/help.py` | modify | Document the new verb. |
| `cli/__init__.py` / dispatch table | modify | Register `council-batch`. |
| `skills/council/00-overview.md` | modify | Replace "SEQUENTIAL per feature" sequencing with the batched-parallel loop. |
| `skills/council/22-parallel-dispatch.md` | new | The conductor procedure (the loop above): how to call `--next-batch`, dispatch a batch in parallel, barrier, isolate failures, report. |
| `skills/council/19-resume.md` | modify | Note that resumption is per-stage via `--next-batch` recomputation. |
| `skills/skill.md` | modify | Update Phase 2/3 description (lines ~25, ~221, ~306) away from strict per-feature serialism. |
| `tests/...` mirrored | new | Cover the domain + CLI verb (see Testing). |
| `pyproject.toml` | modify | Version → 0.20.0. |
| `CHANGELOG.md` | modify | 0.20.0 entry. |

## Data flow

```
features/INDEX.json ─┐
per-feature           ├─▶ council_batch domain ─▶ {stage S, units[≤cap], complete} ─▶ CLI --json
  _council-log.json ──┘            ▲                                                      │
                                   │                                                      ▼
                       (recomputed each call)                              conductor dispatches N
                                   │                                       parallel Task agents
        agents write spec/plan/concerns + council-log ◀────────────────────────┘ (barrier)
```

## Error handling

- **Unparseable / missing `INDEX.json`** → CLI exits non-zero with a clear
  message (same discipline as build's not-equipped stop).
- **A feature's stage `S-1` not complete** → it is simply not included in the
  stage-`S` batch (it surfaces only once its prerequisite is logged complete).
- **Agent failure** → isolate & continue (above); conductor reports at end.
- **Concurrent log writes** → already safe: per-feature files, atomic appends
  (`context/domains/council.py` + `atomic_io.py`). No new locking needed.
- **`--cap < 1`** → validation error, fail fast.

## Testing

Follows the repo's mirrored-test-tree + TDD convention.

- **Unit (domain):** earliest-incomplete-stage selection; cap slicing (units not
  features); stage-3 (feature×critic) unit flattening per mode; trivial/complete
  filtering; resume — a half-done feature returns at the right stage;
  `complete:true` when all done.
- **Unit (CLI):** `--json` schema contract (`complete`, `units[]`, per-unit
  `subagent_type`/`persona_id`/`framework`/`grounding`); `--cap` bound; bad-arg
  rejection; `--root` honoured.
- **Integration:** a synthetic features dir with mixed log states drives several
  `--next` calls to completion; assert each batch is correct, race-free
  (different feature dirs), and resumable after a simulated interrupt.
- Coverage target ≥ 80% on the new modules (repo standard).

## Acceptance

1. `dummyindex context council-batch --next --json` returns the next ≤cap
   dispatch-units for the earliest incomplete stage, or `complete:true`.
2. The cap bounds **agents**, verified by a deep-mode multi-critic case.
3. Resumption: interrupting after stage 1 of some features and re-running
   advances exactly those features to stage 2 without redoing stage 1.
4. Failure isolation: a simulated failed unit does not stop later batches and is
   reported at the end.
5. Council skill markdown no longer instructs strict per-feature serialism;
   `00-overview.md` documents the batched loop.
6. Existing per-feature artifacts (`spec.md`/`plan.md`/`concerns.md`/log) are
   byte-for-byte the same as the serial path for a single-feature repo (no
   regression).
7. Build / plan / audit flows unchanged.
