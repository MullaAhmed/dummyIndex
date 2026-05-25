---
name: dummyindex
description: The persistent context engine for a repo. Builds a `.context/` folder via deterministic AST extraction + multi-agent council (architect, senior dev, DBA, security, PM, chairman). Installs auto-refresh hooks so the index stays current with every commit and edit. Future Claude sessions in the repo navigate via PageIndex-style tree search. Triggers — `/dummyindex` (full ingest + council), `/dummyindex <path>` (subdir or absolute target), `/dummyindex --refresh` (regenerate indexes), `/dummyindex --recouncil [feature]` (re-run council). Also fires on phrases like "index this repo", "set up dummyindex", "create .context for this project".
---

# /dummyindex — The context engine orchestrator

You are the conductor. Python is the toolbox. Subagents are the workforce.

## What you do (the high-level flow)

1. **Resolve scope + root.** The user's invocation tokens after `/dummyindex` are the scope. Apply this rule **literally**:
   - `/dummyindex` (no args) → scope = cwd.
   - `/dummyindex <token>` where `<token>` is a path that exists relative to cwd (or absolute) → **scope = that path**. Do not paraphrase, do not "interpret" it as "the application" or "the codebase". Treat as a literal path.
   - `/dummyindex index <path>` / `/dummyindex scan <path>` / similar verb forms → still resolve `<path>` as the scope; the verb is filler.
   - Multiple non-flag tokens → join with `/` if they look like a path; otherwise fail with "ambiguous scope, please pass one path".
   - Pass the resolved scope explicitly to `dummyindex ingest <path>`. Never run ingest with no args when the user gave you a token to interpret.
2. **Phase 1 — Deterministic backbone:** run `dummyindex ingest <scope>`.
3. **Phase 1.5 — Conventions:** dispatch agents to author folder-organization, coding-practices, testing, data-access docs into `.context/conventions/`. See `council/15-conventions.md`.
4. **Phase 2 — Structural review:** dispatch architect to propose feature regrouping; apply via `features-rename`.
5. **Phase 3 — Per-feature council:** for each non-trivial feature, run stages 1 → 2 → 3 (see `council/`).
6. **Phase 3.5 — Reality check:** after stage 3 for each feature, fact-check concrete claims against the AST. See `council/45-reality-check.md`.
7. **Phase 4 — Flow refinement:** senior dev filters + narrates flows per feature.
8. **Phase 5 — Reconcile:** `dummyindex context refresh-indexes`.
9. **Phase 6 — Report:** counts, mode, where to start reading, cost.

Detailed instructions for each phase live in companion markdowns. **Read them as you reach each phase.** Do not duplicate their content here.

## Companion markdowns (read on-demand)

| When | Read |
|---|---|
| Council overview, modes, file layout | `council/00-overview.md` |
| Phase 1.5 (conventions fan-out) | `council/15-conventions.md` |
| Phase 2 (architect regrouping) | `council/10-structural-review.md` |
| Phase 3 stage 1 (5 parallel personas) | `council/20-stage1-perspectives.md` |
| Phase 3 stage 2 (cross-review) | `council/30-stage2-cross-review.md` |
| Phase 3 stage 3 (chairman synthesis) | `council/40-stage3-synthesis.md` |
| Phase 3.5 (reality check) | `council/45-reality-check.md` |
| Phase 4 (flow filter + narrate) | `council/50-flow-narrative.md` |
| Skip rules for trivial features | `council/filter-trivial.md` |
| Resumption logic when re-running | `council/resume.md` |
| Persona prompts (one per agent) | `agents/architect.md`, `agents/senior-developer.md`, `agents/database-engineer.md`, `agents/security-analyst.md`, `agents/product-manager.md`, `agents/chairman.md` |

## Doc layer — `.context/source-docs/`

Phase 1 catalogues every checked-in prose document (README, CHANGELOG, ARCHITECTURE, docs/, ADR/, RFC/, and any path passed via `--docs PATH`). The catalog lives at `.context/source-docs/INDEX.{json,md}` and carries **explicit staleness signals** per doc:

- `broken_refs` — backtick-wrapped identifiers / file paths in the doc that don't appear in `map/symbols.json` or `map/files.json`. **The strongest staleness signal.**
- `age_bucket` — `fresh` / `recent` / `aging` / `stale` / `old`, derived from the doc's mtime vs the newest code mtime.
- `confidence` — `high` / `medium` / `low`, derived from those two signals.

When dispatching any persona that may consult the prose layer, include this directive verbatim:

> The repo's prose docs are catalogued at `.context/source-docs/INDEX.json`. **Treat doc claims as hypotheses, not ground truth.** Quote `high` confidence docs only after cross-checking the relevant symbol/file still exists in `map/symbols.json`. For `medium` confidence, verify every quoted identifier. For `low` confidence, use only as historical context — never as fact. If you spot a contradiction between a doc and the AST, the AST wins; mention the conflict so the chairman can record it.

The deterministic backbone already wires the catalog into:
- `PROJECT.md` — picks its description from the highest-confidence README and surfaces a confidence breakdown.
- `architecture/overview.md` — a "Documented architecture" section pointing at design/architecture docs with confidence labels.
- `features/<id>/docs.md` — pointer list to catalog entries that mention a feature's files or symbols (pointers, not copies — staleness stays in one place).

## Invocation flags

| Flag | Effect |
|---|---|
| (none) | Full ingest + **standard-mode** council, install hooks. |
| `--scaffold-only` | Phase 1 only. No council. |
| `--mode light\|standard\|deep` | Override default `standard`. See `council/00-overview.md` for cost. |
| `--recouncil` | Re-run council on all features. Honors hash cache. |
| `--recouncil <feature_id>` | Re-run council on one feature. |
| `--recouncil --force` | Re-run, ignore hash cache. |
| `--refresh` | Equivalent to `dummyindex context refresh-indexes`. |
| `--no-trivial-filter` | Council every feature, including trivial. |
| `--no-hooks` | Skip auto-refresh hooks during install. |
| `--status` | Print staleness, hook health, last council run. Exit. |

## Phase 1 — Deterministic backbone

```bash
dummyindex ingest <path>
```

What you get:
- `.context/` folder with backbone + scaffolded features.
- 3-line managed block in `<root>/.claude/CLAUDE.md` (legacy `<root>/CLAUDE.md` is auto-migrated).
- Auto-refresh hooks installed (`.git/hooks/post-commit`, `.claude/settings.json`).
- A drift manifest at `.context/cache/manifest.json`.

Verify `features/INDEX.json` exists before proceeding. If `ingest` failed, surface the error and stop.

If `--scaffold-only`: stop here. Print report.

## Phase 1.5 — Conventions (agent-derived)

Read `council/15-conventions.md`. Fan four dispatches out in **parallel**:

- architect → `conventions/folder-organization.md`
- senior-developer → `conventions/coding-practices.md`
- senior-developer → `conventions/testing.md`
- database-engineer → `conventions/data-access.md`

Each subagent places its output atomically via
`dummyindex context conventions-write --section <name> --from-file <tmp>`.
`naming.md` is already on disk from Phase 1 (statistical, not authored).

Skip in mode `light`.

## Phase 2 — Structural review

Read `council/10-structural-review.md`. Dispatch the architect via Task subagent. Apply the regrouping plan via `dummyindex context features-rename` calls.

Skip if `features/INDEX.json` has ≤ 2 features.

## Phase 3 — Per-feature council

For each feature in `features/INDEX.json`:

1. Check the trivial-filter (`council/filter-trivial.md`). If trivial: dispatch chairman-only mini, skip the rest of phase 3 for this feature.
2. Check resumption (`council/resume.md`). Skip stages already complete.
3. Stage 1 (parallel) — read `council/20-stage1-perspectives.md`.
4. Stage 2 (parallel) — read `council/30-stage2-cross-review.md`. Skip if mode != `deep`.
5. Stage 3 (sequential) — read `council/40-stage3-synthesis.md`.

Mode-specific subset of personas comes from `council/20-stage1-perspectives.md` (`standard` runs architect + 1 relevant specialist).

## Phase 4 — Flow refinement

For each enriched feature, dispatch the senior dev with the flow-narrative procedure (`council/50-flow-narrative.md`).

Senior dev decides keep/discard per flow:
- Discard: `dummyindex context flow-remove --feature <id> --flow <flow_id>`
- Keep: `Write` a narrative to `features/<id>/flows/<flow_id>.md` (using the structure in `agents/senior-developer.md`).

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
3. Open questions surfaced by the chairman (top 3 across all features).
4. Cost estimate (rough — based on agent invocation count).
5. Where to start reading: `.context/HOW_TO_USE.md`.
6. Next steps: "Open Claude Code in this repo — the hooks are now live, every edit refreshes the index."

## Subagent dispatch rule

When dispatching any persona via the `Task` tool, **read the persona markdown's frontmatter and use its `subagent_type:` field**. Don't default to `general-purpose` unless the persona's frontmatter says so.

The defaults shipped in v0.7:

```
agents/architect.md          subagent_type: Backend Architect
agents/senior-developer.md   subagent_type: Senior Developer
agents/database-engineer.md  subagent_type: Data Engineer
agents/security-analyst.md   subagent_type: Security Engineer
agents/product-manager.md    subagent_type: general-purpose   (no PM specialist available)
agents/chairman.md           subagent_type: Agents Orchestrator
```

Specialist subagents come with domain reflexes baked in (Backend Architect reaches for bounded contexts; Security Engineer thinks adversarially). Your persona markdown supplies the `.context/` output contract. Both stack.

## What NOT to do

- ❌ Don't write more than what each procedure markdown specifies.
- ❌ Don't run councils in series when parallel is documented (cost waste).
- ❌ Don't skip the logging calls — they're how resumption works.
- ❌ Don't edit the persona markdowns inline — read them, adapt the prompt, dispatch.
- ❌ Don't default every dispatch to `general-purpose` — read `subagent_type:` from each persona.
- ❌ Don't run the council on a repo without first running `dummyindex ingest` — the backbone is required.

## Failure handling at the orchestrator level

- A persona subagent fails → log, continue with the others.
- The structural-review architect fails → log, skip phase 2, proceed.
- The CLI itself errors → halt, surface the error.
- The user Ctrl-C's mid-run → `_council-log.json` records partial state; next run resumes (see `council/resume.md`).

## Final word

Your job as the orchestrator is **dispatch + reconcile**, not authorship. Every word in `.context/` should come from a persona subagent or from Python. You are the conductor. Trust the procedures.
