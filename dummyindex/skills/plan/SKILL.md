---
name: dummyindex-plan
description: Grounded planning for a new feature in a repo that already has a `.context/` index. Turns a natural-language feature request into a consistency-checked `.context/proposals/<slug>/` artifact — `proposal.json`, `spec.md` (intent + contracts + Acceptance), `plan.md` (ordered, file-path-naming tasks that cite reused symbols), and a flat `checklist.md`. After you draft the spec + plan, a LIGHTWEIGHT critique panel — a few specialist agents (reuse/architecture, risk/edge-cases, testability) dispatched in parallel via the Task tool for ONE round, not a deep debate — flags gaps, and you revise once before deriving the checklist. Then it auto-equips the project-tuned toolkit for the proposal (`equip apply --for-proposal <slug>`, deterministic) so build can dispatch tuned agents. Reuses the deterministic `query` retrieval to ground the plan in existing features + conventions; no guessing about what already exists. Triggers — `/dummyindex-plan`, "plan a feature", "plan this feature", "draft a spec and plan", "scaffold a proposal".
allowed-tools: Read, Write, Bash, Task
---

# /dummyindex-plan — Grounded planning

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, re-run `dummyindex install --scope user`.

You turn a natural-language feature request into a **consistency-checked proposal** under `.context/proposals/<slug>/`. The deterministic CLI scaffolds the artifact and grounds it against the existing index; **you** draft the prose, then a **lightweight critique panel** (a few specialist agents, one parallel round) pressure-tests your draft so you revise before locking the checklist. Python is the toolbox; the panel is the second pair of eyes.

## What you produce

A `.context/proposals/<slug>/` folder with four files:

| File | Owner | Contents |
|---|---|---|
| `proposal.json` | CLI | Structured head: `slug`, `title`, `status`, `related_features`, `conventions`, `reused_symbols`. |
| `spec.md` | You | Intent, contracts, and an `## Acceptance` checklist of `- [ ]` items. The CLI seeds a `## Consistency` block. |
| `plan.md` | You | Ordered tasks, each naming the file path(s) it touches, citing reused symbols. |
| `checklist.md` | You | A flat `- [ ]` list derived from the plan tasks **plus** the spec's Acceptance items. |

## The flow

1. **Resolve scope + slug.** Take the feature request as the `--title`. Derive a short `--slug` (lowercase, digits, `-`/`_` only — no spaces, no `/`). Confirm the repo has a `.context/` (run `dummyindex ingest <path>` first if not).

2. **Scaffold + ground (the CLI does this in one call):**

   ```bash
   dummyindex context propose --slug <slug> --title "<request>" [--root <repo>] [--force]
   ```

   This creates the four template files, runs the deterministic consistency scan (reusing `query` — **no LLM**), and writes the hits into `proposal.json` (`related_features` + `conventions`) and a `## Consistency` block in `spec.md`. It prints the proposal path + related features.

3. **Read the consistency hits first.** Open `proposal.json` and the `## Consistency` block in `spec.md`. For each related feature, read `.context/features/<id>/spec.md` to learn what already exists — so the new plan **reuses** rather than reinvents. Skim the listed `conventions/*.md`.

4. **Flesh out `spec.md`** — intent (problem + who), contracts (inputs/outputs/invariants/seams), and a real `## Acceptance` section: concrete, testable `- [ ]` criteria. Keep the CLI-seeded `## Consistency` block.

5. **Flesh out `plan.md`** — ordered tasks, each naming the exact file path(s) it touches. Where a task can reuse an existing symbol, cite it by name from `.context/map/symbols.json` (and the feature it lives in). Prefer reuse over net-new code.

6. **Critique panel — ONE parallel round, then revise once (this is the multi-agent step).** Your draft is a first draft; before it hardens into a checklist, dispatch a small panel to pressure-test it. This is deliberately **light** — one round, no rebuttals, no debate, the panel only files findings; **you** are the sole reviser.

   Dispatch the three critics below as **parallel `Task` subagents — one message, three Task calls**. For each: set the `subagent_type` shown (fall back to `general-purpose` if that agent type isn't available — the inlined mandate still steers it), and **paste the mandate text into the prompt** (a fresh subagent can't resolve this skill's path — but it *can* Read the proposal + `.context/` files by their repo paths, so tell it to). Hand each critic the paths `.context/proposals/<slug>/spec.md` + `plan.md` and tell it to ground in `.context/HOW_TO_USE.md`, `.context/PROJECT.md`, the related features' `spec.md`, and `.context/conventions/`.

   | Critic | `subagent_type` | Mandate (inline this into the prompt) |
   |---|---|---|
   | **Reuse & architecture** | `Software Architect` | Read the draft spec.md + plan.md and the `.context/` grounding. Flag, with the exact spec/plan location: (a) net-new code that duplicates an existing symbol/feature the plan should reuse — cite it from `.context/map/symbols.json`; (b) a wrong seam/layer or scope creep beyond the stated intent; (c) a task that contradicts a recorded decision or a `conventions/*.md` rule. Findings only — do **not** rewrite the plan. |
   | **Risk & edge-cases** | `Code Reviewer` | Read the draft + grounding. Flag: unhandled failure modes, missing edge cases, error-handling/validation gaps, security / data-exposure / migration risks, ordering hazards between tasks, and anything the plan assumes but never establishes. Each finding: the location + the concrete risk + the minimal mitigating task. Findings only. |
   | **Testability & acceptance** | `Test Results Analyzer` | Read the draft spec.md `## Acceptance` + plan.md. Flag: acceptance criteria that aren't concrete/observable/testable, plan tasks with no way to verify them, and coverage gaps. For each, propose the testable rewording or the missing verification. Findings only. |

   Each critic returns concise findings tagged **BLOCK / HIGH / MEDIUM / LOW** with the location + minimal fix. **Then you revise once:** read all three sets, fold the BLOCK/HIGH findings (and any MEDIUM you agree with) into `spec.md` + `plan.md`, and note in one line what you changed and what you deliberately left. Don't re-dispatch; don't invent changes when the panel found nothing material. (Skip the panel only for a trivial, single-file change whose plan is self-evidently correct — say so if you do.)

7. **Derive `checklist.md`** — *after* the revision — flatten the revised plan tasks and the spec's Acceptance items into one top-to-bottom `- [ ]` list. This is the execution surface a later step works through.

8. **Auto-equip the toolkit for this proposal (deterministic CLI — no Task dispatch).** Once the proposal is fully scaffolded, equip the project-tuned toolkit, scoped to it, so it exists by build time:

   ```bash
   dummyindex context equip apply --for-proposal <slug> [--root <repo>]
   ```

   Equip rendering is non-LLM (detect → catalog → render). `equip apply` is **additive, never-clobber, and origin-hash baselined**, so running it on an already-equipped repo is safe and idempotent — it only fills gaps, never stomps user edits. This means `/dummyindex-build` finds `.context/equipment.json` already in place and dispatches project-tuned agents rather than `general-purpose`. You no longer need to ask the user to run `/dummyindex-equip` separately; it now happens automatically here. (Standalone `/dummyindex-equip` remains the way to re-equip or evolve the toolkit later.)

## Checklist + spec-led discipline (embed this in how you work)

- **Read `spec.md` first.** It is the source of truth for *what* and *why*. The plan serves the spec; the checklist serves both.
- **Work `checklist.md` top-to-bottom.** One item at a time, in order.
- **Tick only after verifying.** Flip `- [ ]` → `- [x]` for an item *only* once you've confirmed it (its test passes / the behavior is observed). Never tick on intent.
- **Stop and report if blocked.** If an item can't be completed (missing dependency, contradictory requirement, ambiguous scope), stop, leave it unticked, and report the blocker with a concrete next step — don't paper over it or skip ahead.

## Done

Report: the proposal path, the related features the scan surfaced, a one-line summary of the plan's shape (how many tasks, which existing symbols it reuses), **the critique panel outcome** (which critics ran, what BLOCK/HIGH findings you folded in, what you deliberately left), and confirmation that the toolkit was auto-equipped for the proposal (so `/dummyindex-build` can dispatch project-tuned agents).
