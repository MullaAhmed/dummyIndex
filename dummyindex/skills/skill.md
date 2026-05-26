---
name: dummyindex
description: The persistent context engine for a repo. Builds a `.context/` folder via deterministic AST extraction + a spec-kit-shaped sequential council (dev drafts spec.md + plan.md, architect reorganises plan.md, critics file concerns.md). Installs a Claude Code SessionStart drift hook so every new session sees a markdown report of which features have source edits newer than their `.context/` docs — the running session updates `.context/` in-place. Future Claude sessions in the repo navigate via PageIndex-style tree search. Triggers — `/dummyindex` (full ingest + council), `/dummyindex <path>` (subdir or absolute target), `/dummyindex --refresh` (regenerate indexes), `/dummyindex --recouncil [feature]` (re-run council). Also fires on phrases like "index this repo", "set up dummyindex", "create .context for this project".
---

# /dummyindex — The context engine orchestrator

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, re-run `dummyindex install --scope user`.

You are the conductor. Python is the toolbox. Subagents are the workforce.

## What you do (the high-level flow)

1. **Resolve scope + root.** The user's invocation tokens after `/dummyindex` are the scope. Apply this rule **literally**:
   - `/dummyindex` (no args) → scope = cwd.
   - `/dummyindex <token>` where `<token>` is a path that exists relative to cwd (or absolute) → **scope = that path**. Do not paraphrase, do not "interpret" it as "the application" or "the codebase". Treat as a literal path.
   - `/dummyindex index <path>` / `/dummyindex scan <path>` / similar verb forms → still resolve `<path>` as the scope; the verb is filler.
   - Multiple non-flag tokens → join with `/` if they look like a path; otherwise fail with "ambiguous scope, please pass one path".
   - Pass the resolved scope explicitly to `dummyindex ingest <path>`. Never run ingest with no args when the user gave you a token to interpret.
2. **Phase 1 — Deterministic backbone:** run `dummyindex ingest <scope>`.
3. **Phase 1.2 — Onboarding (first run only):** if `.context/config.json` is absent (fresh repo or a v0.13.x upgrade), run the 5-question setup and persist via `dummyindex context onboard`. See `council/05-onboarding.md`. Also runs on `/dummyindex --reconfigure`.
4. **Phase 1.5 — Conventions:** dispatch agents to author folder-organization, coding-practices, testing, data-access docs into `.context/conventions/`. See `council/15-conventions.md`.
5. **Phase 2 — Structural review:** dispatch the architect to propose feature regrouping; apply via `features-rename`.
6. **Phase 3 — Per-feature pipeline:** for each non-trivial feature, run stages 1 → 2 → 3 sequentially (specify / plan / critique — see `council/`).
7. **Phase 3.5 — Reality check:** after stage 3 for each feature, fact-check concrete claims in `plan.md` + `concerns.md` against the AST. See `council/45-reality-check.md`.
8. **Phase 4 — Flow refinement:** the same dev filters + narrates flows per feature.
9. **Phase 5 — Reconcile:** `dummyindex context refresh-indexes`.
10. **Phase 6 — Report:** counts, mode, where to start reading, cost.

Detailed instructions for each phase live in companion markdowns. **Read them as you reach each phase.** Do not duplicate their content here.

## Companion markdowns (read on-demand)

| When | Read |
|---|---|
| Onboarding (first run / `--reconfigure`) | `council/05-onboarding.md` |
| Council overview, modes, file layout | `council/00-overview.md` |
| Phase 1.5 (conventions fan-out) | `council/15-conventions.md` |
| Phase 2 (architect regrouping) | `council/10-structural-review.md` |
| Phase 3 stage 1 (`/specify` — dev drafts spec.md + plan.md) | `council/20-specify.md` |
| Phase 3 stage 2 (`/plan` — architect reorganises plan.md) | `council/30-plan.md` |
| Phase 3 stage 3 (`/critique` — critics write concerns.md, mode-gated) | `council/40-critique.md` |
| Phase 3.5 (reality check) | `council/45-reality-check.md` |
| Context7 lookup protocol (MCP companion) | `council/55-context7.md` |
| Phase 4 (flow filter + narrate) | `council/50-flow-narrative.md` |
| Skip rules for trivial features | `council/filter-trivial.md` |
| Resumption logic when re-running | `council/resume.md` |
| Persona prompts | `agents/dev.md`, `agents/architect.md`, `agents/critic-database.md`, `agents/critic-security.md`, `agents/critic-product.md` |

## MCP integrations (optional)

The pipeline wires two MCP servers when the runtime exposes them, and runs
**identically without them** — the `.context/` artifacts have the same shape
either way; only the quality of the prose changes. No MCP call is ever mandatory.

| Server | Tool prefix | Used by | What it adds |
|---|---|---|---|
| **Context7** | `mcp__context7__*` | Phase 1.5 conventions, `/specify` dev (`{{framework_docs}}`), DBA + security critics, reality-check | Per-library, always-current API docs so personas don't invent patterns or claim APIs that no longer exist. Protocol: `council/55-context7.md`. |
| **Sequential Thinking** | `mcp__sequentialthinking_sequentialthinking__sequentialthinking` | Architect's structural review (Phase 2) + `/plan` revision (Phase 3 stage 2) | Explicit draft → cross-check → revise → emit, with an audit trail (`_structural-log.json` / `02-architect-notes.md`). |

Every wired site carries its own graceful-fallback clause, so a missing server is
never a failure — the procedure just falls back to single-shot reasoning.

## Doc layer — `.context/source-docs/`

Phase 1 catalogues every checked-in prose document (README, CHANGELOG, ARCHITECTURE, docs/, ADR/, RFC/, and any path passed via `--docs PATH`). The catalog lives at `.context/source-docs/INDEX.{json,md}` and carries **explicit staleness signals** per doc:

- `broken_refs` — backtick-wrapped identifiers / file paths in the doc that don't appear in `map/symbols.json` or `map/files.json`. **The strongest staleness signal.**
- `age_bucket` — `fresh` / `recent` / `aging` / `stale` / `old`, derived from the doc's mtime vs the newest code mtime.
- `confidence` — `high` / `medium` / `low`, derived from those two signals.

When dispatching any persona that may consult the prose layer, include this directive verbatim:

> The repo's prose docs are catalogued at `.context/source-docs/INDEX.json`. **Treat doc claims as hypotheses, not ground truth.** Quote `high` confidence docs only after cross-checking the relevant symbol/file still exists in `map/symbols.json`. For `medium` confidence, verify every quoted identifier. For `low` confidence, use only as historical context — never as fact. If you spot a contradiction between a doc and the AST, the AST wins; mention the conflict in the council audit trail.

The deterministic backbone already wires the catalog into:
- `PROJECT.md` — picks its description from the highest-confidence README and surfaces a confidence breakdown.
- `architecture/overview.md` — a "Documented architecture" section pointing at design/architecture docs with confidence labels.
- `features/<id>/docs.md` — pointer list to catalog entries that mention a feature's files or symbols (pointers, not copies — staleness stays in one place).

## Invocation flags

| Flag | Effect |
|---|---|
| (none) | Full ingest + **standard-mode** council, install hooks. |
| `--scaffold-only` | Phase 1 only. No council. |
| `--mode light\|standard\|deep` | Override the configured/default mode for this run. See `council/00-overview.md` for cost. |
| `--reconfigure` | Re-run the 5 onboarding questions and rewrite `.context/config.json`. See `council/05-onboarding.md`. |
| `--recouncil` | Re-run council on all features. Honors hash cache. |
| `--recouncil <feature_id>` | Re-run council on one feature. |
| `--recouncil --force` | Re-run, ignore hash cache. |
| `--refresh` | Equivalent to `dummyindex context refresh-indexes`. |
| `--no-trivial-filter` | Council every feature, including trivial. |
| `--no-hooks` | Skip the SessionStart drift hook during install. |
| `--status` | Print staleness, hook health, last council run. Exit. |

## Phase 1 — Deterministic backbone

```bash
dummyindex ingest <path>
```

What you get:
- `.context/` folder with backbone + scaffolded features.
- 3-line managed block in `<root>/.claude/CLAUDE.md` (legacy `<root>/CLAUDE.md` is auto-migrated).
- A SessionStart drift hook installed at `.claude/settings.json` —
  every new Claude session in this repo runs `dummyindex context
  plan-update` and the markdown report (which features have source
  edits newer than their `.context/` docs) is appended to the
  session's system prompt. Drift clears when the agent edits the
  feature doc; no shell-side rebuild loop runs on commit or
  PostToolUse anymore.
- A drift manifest at `.context/cache/manifest.json`.

Verify `features/INDEX.json` exists before proceeding. If `ingest` failed, surface the error and stop.

If `--scaffold-only`: stop here. Print report.

## Phase 1.2 — Onboarding (first run only)

Read `council/05-onboarding.md`. Check for a persisted config:

```bash
dummyindex context config show
```

- Prints a config → already onboarded. Skip to Phase 1.5.
- Reports "no config.json" (exit 1) → run the 5-question setup (scope, mode,
  model, auto-refresh hook, external docs) via the `AskUserQuestion` tool, then
  persist with `dummyindex context onboard --scope ... --mode ... --model ...`.
- `/dummyindex --reconfigure` → always re-run the questions.

Questions 1–3 (scope, mode, **model**) are required; the model is never
silently defaulted. Questions 4–5 are skippable. The mode chosen here is the
run's default; an explicit `--mode` on the invocation still overrides it.

Skip this phase entirely under `--scaffold-only`.

## Phase 1.5 — Conventions (agent-derived)

Read `council/15-conventions.md`. Fan four dispatches out in **parallel**:

- architect → `conventions/folder-organization.md`
- dev → `conventions/coding-practices.md`
- dev → `conventions/testing.md`
- critic-database → `conventions/data-access.md`

Each subagent places its output atomically via
`dummyindex context conventions-write --section <name> --from-file <tmp>`.
`naming.md` is already on disk from Phase 1 (statistical, not authored).

Skip in mode `light`.

## Phase 2 — Structural review

Read `council/10-structural-review.md`. Dispatch the architect via Task subagent. Apply the regrouping plan via `dummyindex context features-rename` calls.

Skip if `features/INDEX.json` has ≤ 2 features.

## Phase 3 — Per-feature pipeline

For each feature in `features/INDEX.json`:

1. Check the trivial-filter (`council/filter-trivial.md`). If trivial: dispatch the architect consolidation pass, skip the rest of phase 3 for this feature.
2. Check resumption (`council/resume.md`). Skip stages already complete.
3. Stage 1 — `/specify` — read `council/20-specify.md`. Run `dev-pick`, dispatch one dev. Writes `spec.md` + `plan.md`; snapshot the draft to `council/01-dev-draft.md`.
4. Stage 2 — `/plan` — read `council/30-plan.md`. Dispatch the architect to reorganise `plan.md` in place; writes `council/02-architect-notes.md`. Skip in mode `light`.
5. Stage 3 — `/critique` — read `council/40-critique.md`. Mode-gated:
   - **light:** skip.
   - **standard:** one relevant critic, no cross-review.
   - **deep:** all relevant critics + cross-review.

Stages run **sequentially** per feature (plan needs the dev's draft; critics need the finalised plan). Different features can be processed back-to-back.

## Phase 4 — Flow refinement

For each enriched feature, dispatch the **same dev** (resolve via `dev-pick`) with the flow-narrative procedure (`council/50-flow-narrative.md`).

The dev decides keep/discard per flow:
- Discard: `dummyindex context flow-remove --feature <id> --flow <flow_id>`
- Keep: `Write` a one-paragraph narrative to `features/<id>/flows/<flow_id>.md` (using the structure in `agents/dev.md`).

Skip in mode `light`.

## Phase 5 — Reconcile

```bash
dummyindex context refresh-indexes
```

Regenerates `INDEX.md`, `features/INDEX.md`, `features/graph.json`, `features/graph.html` from disk.

## Phase 6 — Report

Tell the user, in this order:

1. Mode used.
2. Counts: features enriched, flows kept, flows dropped, agent invocations.
3. Top open questions surfaced in `plan.md` "Open questions" + unresolved `concerns.md` items (top 3 across all features).
4. Cost estimate (rough — based on agent invocation count).
5. Where to start reading: `.context/HOW_TO_USE.md`.
6. Next steps: "Open Claude Code in this repo — the SessionStart drift hook is live; every new session sees a report of features whose source has changed since the last `.context/` update, and you can update the relevant docs in-session."

## Subagent dispatch rule

When dispatching any persona via the `Task` tool, **read the persona markdown's frontmatter and use its `subagent_type:` field**. For the dev, **resolve the type per-feature first** via `dummyindex context dev-pick --feature <id>` — its JSON `subagent_type` overrides the frontmatter fallback.

Defaults bundled with the current dummyindex package:

```
agents/dev.md               subagent_type: resolved via dev-pick
                            (Backend Architect / Frontend Developer /
                             Data Engineer / AI Engineer / Senior Developer);
                            fallback Senior Developer
agents/architect.md         subagent_type: Backend Architect
agents/critic-database.md   subagent_type: Data Engineer
agents/critic-security.md   subagent_type: Security Engineer
agents/critic-product.md    subagent_type: general-purpose   (no PM specialist available)
```

Specialist subagents come with domain reflexes baked in (Backend Architect reaches for bounded contexts; Security Engineer thinks adversarially). Your persona markdown supplies the `.context/` output contract. Both stack.

## What NOT to do

- ❌ Don't write more than what each procedure markdown specifies.
- ❌ Don't run a feature's stages out of order — specify → plan → critique is sequential.
- ❌ Don't skip the logging calls — they're how resumption works.
- ❌ Don't edit the persona markdowns inline — read them, adapt the prompt, dispatch.
- ❌ Don't default every dispatch to `general-purpose` — read `subagent_type:` from each persona (and run `dev-pick` for the dev).
- ❌ Don't run the council on a repo without first running `dummyindex ingest` — the backbone is required.

## Failure handling at the orchestrator level

- A persona subagent fails → log, continue with the others.
- The structural-review architect fails → log, skip phase 2, proceed.
- The CLI itself errors → halt, surface the error.
- The user Ctrl-C's mid-run → `_council-log.json` records partial state; next run resumes (see `council/resume.md`).

## Final word

Your job as the orchestrator is **dispatch + reconcile**, not authorship. Every word in `.context/` should come from a persona subagent or from Python. You are the conductor. Trust the procedures.
