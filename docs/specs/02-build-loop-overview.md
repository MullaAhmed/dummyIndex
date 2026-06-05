# 02 — Build-loop architecture overview

**Date:** 2026-06-06
**Status:** Orientation map (not a slice spec). Decide the first slice from this, then spec it.
**Relationship to today:** Part 1 (understand + document → `.context/`) ships. This maps the *middle of the loop* — plan, equip, execute — that turns dummyindex from a context engine into a grounded build loop.

## 1. The resolved principle: dummyindex stays the spine

dummyindex **never writes production code itself.** Its new power is that it **creates or installs project-specific tooling** (skills, plugins, agents, hooks, commands) into `.claude/`, and *that tooling* — leaning heavily on `.context/` — does the building. The spine **plans**, **assembles the toolkit**, **orchestrates**, and **re-indexes**. This extends the existing non-goal ("agents that consume `.context/` may write code, but dummyindex doesn't") rather than repudiating it: dummyindex now *produces the consumers*.

> The "Won't do: code generation" line in `docs/brief/11-roadmap.md` is crossed in spirit (we generate the agents that generate code). This is a deliberate, owner-approved scope expansion. `docs/brief/10-non-goals.md` should be updated when the first slice ships.

## 2. The closed loop

```
 [1] UNDERSTAND + DOCUMENT      ✅ ships today  → .context/ (features, conventions, symbols, docs)
        │
        ▼
 [A] PLAN a new feature         ← grounded in .context/: no duplicate feature,
        │                          respects conventions, reuses real symbols
        ▼
 [B] EQUIP the project          ← create/install .claude/ tooling tuned to THIS
        │                          project + this plan; honors preflight safety
        ▼
 [C] EXECUTE the plan           ← run via the equipped tooling (generic fallback),
        │                          each step grounded in .context/; review per task
        ▼
 [1'] RE-INDEX                  ✅ ships today  → drift hook + rebuild document the
                                   new code; the next plan is grounded in a richer index
```

dummyindex owns **[1]/[1']** today. This document maps **[A]/[B]/[C]**. The through-line is **everything is grounded in `.context/`** — that is the entire reason dummyindex (vs. a generic agent harness) should own this loop.

## 3. The three subsystems

### A — Grounded feature planning
- **Provisional command:** `/dummyindex-plan "<feature request>"`
- **Responsibility:** turn a natural-language feature request into a **consistency-checked** `spec.md` + `plan.md` for a *new* feature.
- **Inputs → outputs:** NL request → a proposed-feature folder (intent/contracts + architecture/file-map/decisions) that explicitly lists: related/overlapping existing features, applicable conventions, reusable symbols/modules, and where it slots into the feature graph.
- **How it grounds in `.context/`:** retrieves via `dummyindex context query` + walks `features/INDEX`, `conventions/`, `map/symbols.json`; a **consistency check** (analogue of `reality-check`, but for a *proposed* plan) verifies the plan doesn't duplicate a feature and cites real symbols.
- **Reuses:** the council's `/specify` (dev) + `/plan` (architect) pointed *forward*; `reality-check`; `query`; `dev-pick`.
- **Smallest leap** from what ships today; **prerequisite for C.**
- **Open questions (resolve at spec time):** where proposed-feature plans live (`.context/proposals/<slug>/`? `docs/`?); is consistency *advisory* or a *gate*; how the plan references not-yet-existing symbols.

### B — Project toolkit generation ("equip")
- **Provisional command:** `/dummyindex-equip` (optionally scoped to a plan from A)
- **Responsibility:** decide which skills / agents / hooks / commands / plugins *this* project needs, then **create** bespoke ones and/or **install** existing matching ones into `.claude/`.
- **Inputs → outputs:** project (`.context/` + manifests) [+ optional plan from A] → additive writes under `.claude/skills|agents|commands` + `.claude/settings.json` hooks, each grounded so its prompt points back at `.context/` (HOW_TO_USE, conventions, the relevant feature docs).
- **How it grounds in `.context/`:** stack/convention detection reuses `dev-pick` + `map/files.json` + manifests; generated tooling embeds `.context/` directives so it consults the spine at run time.
- **Safety (load-bearing):** reuses the **preflight inventory** (`settings.json` validity + user hooks, `.claude/rules/`, `.claude/agents/`, CLAUDE.md state) and the **never-clobber + sentinel + backup** discipline already built. Additive only; user-authored tooling is never overwritten.
- **The novel, highest-value, highest-risk piece.** Overlaps with `plugin-dev` / `skill-creator` / `agent-creator` (compose them rather than reinvent).
- **Open questions (resolve at spec time):** **bespoke generation vs. project-tuned templates vs. install-existing** (the central one); once-per-project vs. per-feature regeneration; what registry "install existing" draws from; how generated tooling is versioned/refreshed when conventions change.

### C — Grounded execution
- **Provisional command:** `/dummyindex-build <plan>`
- **Responsibility:** execute A's plan using B's toolkit, then close the loop by re-indexing.
- **Inputs → outputs:** plan [+ equipped tooling] → source changes (written by the dispatched/equipped agents, not by dummyindex) → refreshed `.context/`.
- **How it grounds in `.context/`:** every task dispatch is injected with the relevant feature docs, conventions, and symbol citations + the consistency directive; **spec + quality review per task** (the pattern proven in this very session via `superpowers:subagent-driven-development`); on completion, `rebuild --changed` + the council document the new feature.
- **Reuses:** the subagent-driven execution pattern (already proven), `dev-pick`, the drift/rebuild machinery.
- **Mostly composition** — the value-add is the `.context/` grounding and the automatic re-index, not a new engine.
- **Open questions (resolve at spec time):** own thin execution loop vs. invoke `superpowers` directly; human checkpoints (per-task vs. per-feature); how/when the re-index + council run fires.

## 4. Cross-cutting concerns

- **Consistency-grounding is the spine.** A plans against the graph; B grounds generated tooling in conventions; C injects context per task and re-indexes. Remove the grounding and this is just a generic harness — the grounding is the differentiator.
- **Safety architecture is reused, not rebuilt.** B's writes into `.claude/` go through the same preflight/never-clobber/sentinel/backup path that protects `settings.json` today.
- **The loop compounds.** Each built feature enriches `.context/`, so every subsequent plan is grounded in a richer index. The bookends already exist; we are filling the middle.

## 5. Reuse-over-reinvent map

| Need | Existing building block to compose |
|---|---|
| Draft spec/plan | council `/specify` + `/plan` (point forward) |
| Verify plan vs. code | `reality-check` (generalize to a proposed plan) |
| Retrieve grounding | `dummyindex context query` + tree walk |
| Pick stack specialist | `dev-pick` |
| Generate skills/agents/plugins | `plugin-dev`, `skill-creator`, `agent-creator` (compose) |
| Execute a plan with review | `superpowers:subagent-driven-development` (proven this session) |
| Write into `.claude/` safely | `preflight` + install's never-clobber/sentinel/backup |
| Re-index after build | drift hook + `rebuild --changed` + council |

## 6. Recommended build sequence

**A → C → B.** A is the smallest leap and C's prerequisite; C composes a proven pattern; B is the novel/risky piece best built last, once A+C give it concrete plans/executions to optimize. (The owner may reorder — B-first is "hardest, highest-value first" but hardest to validate in isolation.)

## 7. Decision needed

Pick the **first slice to fully spec** (A, B, or C), or accept the recommended A-first. Each slice then gets its own `docs/specs/` design → `docs/plans/` plan → build cycle, exactly like the session-memory feature.
