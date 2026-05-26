# 05 — Multi-agent council

The deep-dive layer. Inspired by [spec-kit](https://github.com/github/spec-kit) (sequential, layered artifacts) and Karpathy's `llm-council` (peer-ranked critique).

**Shape**: backbone scaffolds → dev drafts → architect reorganises → critics file concerns. Each step has one author and one artifact. No essay redundancy. No synthesis step.

## The three stages

### Stage 1 — `/specify` (stack-specialist dev drafts)

- One author. The dev persona is **dispatched as the stack specialist** for the feature's primary domain — backend-fastapi for FastAPI features, frontend-react for React features, data-engineer for SQL/migrations, etc. (See `06-personas.md` for the picker.)
- Input: `feature.json`, sample source files, flow traces, `features/<id>/docs.md` if present, the **doc-evidence directive** verbatim.
- Output: `spec.md` (intent, user-visible behavior, contracts) + `plan.md` (architecture, file map, key decisions, data model).
- Audit trail: `council/01-dev-draft.md` snapshot of the unrevised `plan.md`.

The dev writes both because spec and plan are inseparable at draft time — one author's coherent voice across "what" and "how" beats two disconnected drafts.

### Stage 2 — `/plan` (architect reorganises)

- Architect reads `plan.md` and restructures it.
- Sharpens module boundaries, names dependencies, surfaces unstated decisions, removes accidental detail.
- Keeps the **regrouping privilege**: across-feature merges/splits via `features-rename` still happen in the pre-stage before any dev dispatch.
- Output: revised `plan.md` (overwrites the dev draft).
- Audit trail: `council/02-architect-notes.md` records what changed and why.

### Stage 3 — `/critique` (critics file concerns)

- Critics read the **finalized plan.md** with one question: _is anything wrong, missing, or risky?_
- Critics write into `concerns.md` — a single shared file organized by domain:
  - `## Data integrity` — DBA
  - `## Security` — security analyst
  - `## Product surface` — PM
- Each finding cites `path:range`. No essays. Bullet points and table entries only.
- Audit trail: `council/10-critiques.md` retains raw per-critic output for resumption.

## Doc-evidence directive (verbatim in every prompt)

Catalogued prose docs carry `confidence` (high/medium/low) and `broken_refs`. Quote only `high`/`medium` after spot-checking each cited identifier against `map/symbols.json`. Treat `low` as historical context, never as authority. If a doc contradicts the code, the code wins — flag the conflict in the audit trail.

## Modes

User-selectable per run:

| Mode | Stage 1 (dev) | Stage 2 (architect) | Stage 3 (critics) | Cost (14-feature repo) |
|---|---|---|---|---|
| **light** | ✓ | — | — | ~$2–4 |
| **standard** (default) | ✓ | ✓ | 1 critic, picked by relevance | ~$6–10 |
| **deep** | ✓ | ✓ | All relevant critics + cross-review | ~$15–25 |

Critic relevance signals (per feature):

- **DBA** if any file matches `*sql*`, `*migrations*`, `*models*`, `*schema*`.
- **Security** if any file matches `*auth*`, `*jwt*`, `*permission*`, `*acl*`, or auth-bearing routes.
- **PM** if any file matches `routes/*`, `handlers/*`, `views/*`, `controllers/*`.

In `standard` the first matching critic wins. In `deep` all matching critics run, and they cross-review each other's findings before writing into `concerns.md`.

## Why this beats the v0.13 parallel-essay model

- **No redundancy**. Three docs, three jobs. Today's 6 essays overlap heavily; the architect's "module boundaries" reappears in the senior dev's "code organisation" and the chairman's `README` synthesis.
- **Coherent voice**. One author per layer. The dev's spec/plan reads like one engineer wrote it, not five committees stitched together by a chairman.
- **Concrete critic task**. Critics react to a finalised plan — "find what's wrong" — instead of producing parallel essays the chairman has to reconcile.
- **Lower cost by construction**. ~3 sequential dispatches per feature in standard mode beats today's 3 parallel + chairman synth + cross-review on deep.
- **Stack-aware authorship**. A FastAPI specialist writing about a FastAPI feature won't miss framework idioms a generic senior-dev would.

## Skip-trivial filter

Some features don't deserve a council pass.

- Skip if: `member_count < 3`, `file_count < 2`, `entry_point_count == 0` AND name suggests utility (`*-utils-*`, `typing-*`, `*-marker`, `*-config`).
- Trivial features get a one-paragraph `spec.md` from a template. No `plan.md`, no `concerns.md`.

## Resumption

- Each stage writeback updates `council/_council-log.json`.
- A re-run skips stages already complete for the feature.
- Force re-run with `--force`.
- Source hash unchanged + log complete → fast no-op.

## Cache

- Each feature's source files are content-hashed.
- All hashes match the last council → skip entirely (`spec.md` / `plan.md` / `concerns.md` survive).
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
