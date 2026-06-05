# Council overview

How dummyindex turns deterministic feature scaffolding into rich, agent-authored
documentation. Spec-kit-shaped: sequential, layered artifacts. One author per
layer, one artifact per step. No essay redundancy, no synthesis step.

## The pattern

For every non-trivial feature in `features/INDEX.json`, three sequential stages:

1. **Stage 1 — `/specify`.** The stack-specialist dev drafts `spec.md` (what) +
   `plan.md` (how). One author. See `20-specify.md`.
2. **Stage 2 — `/plan`.** The architect reorganises `plan.md` in place and
   records the diff in `council/02-architect-notes.md`. See `30-plan.md`.
3. **Stage 3 — `/critique`.** Critics read the finalised `plan.md` and file
   findings into `concerns.md`, mode-gated. See `40-critique.md`.

Followed by:

4. **Flow refinement.** The same dev filters + narrates flows (`50-flow-narrative.md`).
5. **Reconcile.** `refresh-indexes` regenerates derived markdowns.

## Where each piece lives

```
features/<feature_id>/
├── spec.md                    # Stage 1 — dev (what)
├── plan.md                    # Stage 1 dev draft → Stage 2 architect-revised (how)
├── concerns.md                # Stage 3 — critics, one shared file by domain
├── council/
│   ├── 01-dev-draft.md        # the dev's unrevised plan.md (diff-vs-architect)
│   ├── 02-architect-notes.md  # what the architect changed in plan.md, with rationale
│   ├── 10-critiques.md        # raw per-critic findings before merge into concerns.md
│   └── _council-log.json      # resumption state (per stage, per feature)
└── flows/
    ├── <flow_id>.json         # deterministic
    └── <flow_id>.md           # narrated by the dev (or removed)
```

`concerns.md` is organized by section: `## Data integrity` (DBA),
`## Security` (security), `## Product surface` (PM).

## Modes

| Mode | Stage 1 (dev) | Stage 2 (architect) | Stage 3 (critics) | Cost (14-feature repo) |
|---|---|---|---|---|
| **light** | ✓ | — | — | ~$2–4 |
| **standard** (default) | ✓ | ✓ | 1 relevant critic, no cross-review | ~$6–10 |
| **deep** | ✓ | ✓ | all relevant critics + cross-review | ~$15–25 |

Mode passed via `/dummyindex --mode light|standard|deep`.

**Why standard is default:** `deep` runs all relevant critics plus cross-review —
genuinely expensive on a medium repo. Standard gets ~80% of the depth at a
fraction of the cost. Use `--recouncil <feature_id> --mode deep` to deep-dive one
feature before a major refactor.

## Sequencing

```
Phase 0: dummyindex ingest (deterministic backbone)
   │
Phase 1: Structural review (architect pre-stage)
   ├── Dispatch ONE architect over INDEX.json + all feature.jsons
   ├── Architect emits a regrouping plan (merges/splits)
   └── Skill applies via features-rename
   │
Phase 2: Per-feature pipeline (loop over features, SEQUENTIAL per feature)
   │   skip if feature trivial (see filter-trivial.md)
   │   skip if _council-log.json shows complete + source unchanged
   │
   ├── Stage 1 — /specify  (dev-pick → one dev → spec.md + plan.md)
   ├── Stage 2 — /plan      (architect reorganises plan.md)
   └── Stage 3 — /critique  (mode-gated critics → concerns.md)
   │
Phase 3: Flow refinement (same dev decides keep/discard + narrates)
   │
Phase 3.5: Tree enrichment (node abstracts → INFERRED; mode-gated, see 52-tree-enrich.md)
   │
Phase 4: dummyindex context refresh-indexes
```

## Persona → subagent_type mapping

| Persona file | subagent_type |
|---|---|
| `agents/dev.md` | resolved per-feature via `dummyindex context dev-pick` (Backend Architect / Frontend Developer / Data Engineer / AI Engineer / Senior Developer); fallback `Senior Developer` |
| `agents/architect.md` | `Backend Architect` |
| `agents/critic-database.md` | `Data Engineer` |
| `agents/critic-security.md` | `Security Engineer` |
| `agents/critic-product.md` | `general-purpose` (no PM-specific type) |

**Why specialist subagent types:** Anthropic's specialists carry domain reflexes
(Backend Architect reaches for bounded contexts; Security Engineer thinks
adversarially). The persona markdown supplies the `.context/` output contract;
the specialist supplies the reflexes. Both stack.

### The dev picker

The dev persona is **parameterised**, not fixed. The orchestrator resolves the
stack at dispatch time:

```bash
dummyindex context dev-pick --feature <id>
```

It prints `{persona_id, subagent_type, framework}` — deterministic, no LLM. The
orchestrator dispatches the dev with that `subagent_type` and fills the
`{{framework}}` slot in `agents/dev.md`.

## Logging discipline

Every agent invocation, at start AND end, calls:

```bash
dummyindex context council-log --feature <id> --stage <N> --agent <persona> --status started|complete|failed
```

Stage numbers stay numeric: specify = 1, plan = 2, critique = 3. The skill
consults the log to skip completed work (resumption), detect partial failures,
and show progress.

## What this gives the agent reading `.context/` later

- `spec.md` — the WHAT (intent, behavior, contracts).
- `plan.md` — the HOW (architecture, file map, data model, decisions).
- `concerns.md` — the RISKS (data integrity, security, product gaps).
- `council/` audit trail — the dev draft, the architect's changes, raw critiques.
- `flows/` — narrated call sequences.
