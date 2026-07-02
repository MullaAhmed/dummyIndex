# 05 — Multi-agent council

The deep-dive layer. Inspired by [spec-kit](https://github.com/github/spec-kit) (sequential, layered artifacts) and Karpathy's `llm-council` (peer-ranked critique).

**Shape**: backbone scaffolds → dev drafts → architect reorganises → critics file concerns → dev narrates flows. Each step has one author and one artifact. No essay redundancy. No synthesis step.

## The pipeline stages

Stages are numbered as written to `_council-log.json` and named after the spec-kit-style verbs they echo — they are **stage roles**, not slash commands (the only slash commands are the eight in [08-skill.md](08-skill.md)). The stage enum is `SPECIFY=1 · PLAN=2 · CRITIQUE=3 · FLOW=4 · TREE=5`; which stages actually run depends on the mode (see [Modes](#modes)).

### Stage 1 — `specify` (stack-specialist dev drafts)

- One author. The dev persona is **dispatched as the stack specialist** for the feature's primary domain — backend-fastapi for FastAPI features, frontend-react for React features, data-engineer for SQL/migrations, etc. (See `06-personas.md` for the picker.)
- Input: `feature.json`, sample source files, flow traces, `features/<id>/docs.md` if present, the **doc-evidence directive** verbatim.
- Output: `spec.md` (intent, user-visible behavior, contracts) + `plan.md` (architecture, file map, key decisions, data model).
- Audit trail: `council/01-dev-draft.md` snapshot of the unrevised `plan.md`.

The dev writes both because spec and plan are inseparable at draft time — one author's coherent voice across "what" and "how" beats two disconnected drafts.

### Stage 2 — `plan` (architect reorganises)

- Architect reads `plan.md` and restructures it.
- Sharpens module boundaries, names dependencies, surfaces unstated decisions, removes accidental detail.
- Keeps the **regrouping privilege**: across-feature merges/splits via `features-rename` still happen in the pre-stage before any dev dispatch.
- Output: revised `plan.md` (overwrites the dev draft).
- Audit trail: `council/02-architect-notes.md` records what changed and why.

### Stage 3 — `critique` (critics file concerns)

- Critics read the **finalized plan.md** with one question: _is anything wrong, missing, or risky?_
- Critics write into `concerns.md` — a single shared file organized by domain:
  - `## Data integrity` — DBA
  - `## Security` — security analyst
  - `## Product surface` — PM
- Each finding cites `path:range`. No essays. Bullet points and table entries only.
- Audit trail: `council/10-critiques.md` retains raw per-critic output for resumption.

### Stage 4 — `flow` (dev narrates flows)

- Runs in **every** mode — it is the one stage `light` keeps besides the dev draft.
- The stack-specialist dev (a `framework`-tagged unit, like `specify`) narrates the feature's execution flows into `features/<id>/flows/<flow-id>.json` (see [04-data-model.md](04-data-model.md)) and filters trivial/false-positive flows via `flow-remove`.

### Stage 5 — `tree` (tree-enrich pass, opt-in)

- Only runs when the batch is requested with `--tree-enrich`; appended after `flow` in any mode.
- A dev unit writes node abstracts into `tree.json` for PageIndex-style navigation (see [12-retrieval.md](12-retrieval.md)).

## Doc-evidence directive (verbatim in every prompt)

Catalogued prose docs carry `confidence` (high/medium/low) and `broken_refs`. Quote only `high`/`medium` after spot-checking each cited identifier against `map/symbols.json`. Treat `low` as historical context, never as authority. If a doc contradicts the code, the code wins — flag the conflict in the audit trail.

## Modes

User-selectable per run:

Selected per run via `--depth light|standard|deep` (`--mode` is a back-compat alias). `flow` runs in every mode; `plan` + `critique` are added by `standard`/`deep`; `tree` is orthogonal, gated by `--tree-enrich`.

| Mode | `specify` (dev) | `plan` (architect) | `critique` (critics) | `flow` (dev) | Cost (14-feature repo) |
|---|---|---|---|---|---|
| **light** | ✓ | — | — | ✓ | ~$2–4 |
| **standard** (default) | ✓ | ✓ | 1 critic (security) | ✓ | ~$6–10 |
| **deep** | ✓ | ✓ | 3 critics (database, security, product) | ✓ | ~$15–25 |

The critic roster is **fixed per mode**, not chosen by per-feature relevance globs — a deterministic, resumable roster (`CRITIC_ROSTER`):

- **light** — no critics.
- **standard** — one critic: security (the most universal).
- **deep** — three critics: database, security, product.

Each critic writes its domain section into the shared `concerns.md` (`## Data integrity` / `## Security` / `## Product surface`).

## Why this beats the v0.13 parallel-essay model

- **No redundancy**. One artifact per stage, one job each. Today's 6 essays overlap heavily; the architect's "module boundaries" reappears in the senior dev's "code organisation" and the chairman's `README` synthesis.
- **Coherent voice**. One author per layer. The dev's spec/plan reads like one engineer wrote it, not five committees stitched together by a chairman.
- **Concrete critic task**. Critics react to a finalised plan — "find what's wrong" — instead of producing parallel essays the chairman has to reconcile.
- **Lower cost by construction**. A handful of sequential dispatches per feature in standard mode beats today's 3 parallel + chairman synth + cross-review on deep.
- **Stack-aware authorship**. A FastAPI specialist writing about a FastAPI feature won't miss framework idioms a generic senior-dev would.

## Skip-trivial filter

Some features don't deserve a council pass.

- A feature is **trivial** if _any_ of:
  - `member_count < 3` AND `entry_point_count == 0` (tiny utility cluster);
  - `file_count == 1` AND `entry_point_count == 0` (single file, no entry points);
  - `name` matches `*-marker`, `typing-*`, `*-aliases`, `*-config`, `*-helpers-*`, or `*-utils-*`;
  - all members are type aliases or constants (no callable definitions).
- Trivial features skip specify → plan → critique; instead an architect consolidation pass decides where they belong. Count fields live in `features/INDEX.json` (not `feature.json`).

## Dispatch plumbing (`council-batch` / `council-log`)

The skill never picks stages by hand — two deterministic CLI verbs drive the loop (documented in [07-cli.md](07-cli.md)):

- **`council-batch --next`** computes the next parallel frontier: the *earliest incomplete stage* across all non-trivial features and the concrete dispatch units for it (`feature_id`, `stage`, `role`, `subagent_type`, `framework`), capped at `--cap` (default 8). `--depth`/`--mode` selects the mode; `--tree-enrich` appends stage 5; `--json` emits the machine payload `{complete, stage, mode, cap, forced, units[]}`.
- The skill fans those units out to parallel Task subagents, barriers, then re-runs `--next` — the council twin of `build --next-wave`. When `complete` is `true`, every feature has finished every active stage for the mode.
- **`council-log --feature ID --stage N --agent NAME --status started|complete|failed|skipped`** records each invocation's outcome to `features/<id>/council/_council-log.json`; the frontier reads it back to know what's done. The `council-log backfill` subverb synthesizes `complete` entries for a pre-v0.20 index whose enrichment artifacts exist but whose logs are empty (run it once before dispatching, or the frontier reschedules — and overwrites — already-curated docs).

## Resumption

- Each stage writeback updates `council/_council-log.json`.
- A re-run skips stages already complete for the feature.
- Force a scoped re-council with `council-batch --next --feature ID --force` — `--force` requires at least one `--feature` (it drops a stage-0 reset marker so the scoped feature re-surfaces at `specify`).
- Source hash unchanged + log complete → fast no-op.

## Cache

- Each feature's source files are content-hashed.
- All hashes match the last council → skip entirely (`spec.md` / `plan.md` / `concerns.md` / `flows/` survive).
- Any file changed → stages re-run in order; architect and critics rerun even if their inputs only mutated through the dev's redraft.

## Regrouping (architect's pre-stage)

Before per-feature dev dispatch, the architect runs once across the full `INDEX.json`:

- Proposes merges (two features overlap heavily) and splits (one community spans multiple domains).
- Applies the plan atomically via `features-rename`.
- Per-feature work runs on the **regrouped** features.

This is unchanged from v0.13 — the value of restructuring before authoring is independent of the per-feature pipeline shape.

## What the audit trail captures

```
council/
├── _council-log.json        # resumption state (per stage, per feature)
├── 01-dev-draft.md          # the dev's unrevised plan.md (for diff-vs-architect)
├── 02-architect-notes.md    # what the architect changed in plan.md, with rationale
└── 10-critiques.md          # raw per-critic findings before merge into concerns.md
```

Same auditability as v0.13's `01-architect.md`..`05-product-manager.md` set — just sharper, because each file has a single job.
