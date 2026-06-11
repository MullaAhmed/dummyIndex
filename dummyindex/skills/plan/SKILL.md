---
name: dummyindex-plan
description: Grounded planning for a new feature in a repo that already has a `.context/` index. Turns a natural-language feature request into a consistency-checked `.context/proposals/<slug>/` artifact — `proposal.json`, `spec.md` (intent + contracts + Acceptance), `plan.md` (ordered, file-path-naming tasks that cite reused symbols), and a wave-grouped `checklist.md` (`## Wave N` headings group mutually independent items so build can dispatch them in parallel). After you draft the spec + plan, a LIGHTWEIGHT critique panel — a few specialist agents (reuse/architecture, risk/edge-cases, testability) dispatched in parallel via the Task tool for ONE round, not a deep debate — flags gaps, and you revise once before deriving the checklist. Then it auto-equips the project-tuned toolkit for the proposal (`equip apply --for-proposal <slug>`, deterministic) so build can dispatch tuned agents. Annotates each task with the installed plugin command/skill that will execute it (`— via <tool>`), and for any capability no installed plugin or generated specialist covers it auto-runs `equip discover` and (with your approval) installs one. Reuses the deterministic `query` retrieval to ground the plan in existing features + conventions; no guessing about what already exists. Triggers — `/dummyindex-plan`, "plan a feature", "plan this feature", "draft a spec and plan", "scaffold a proposal".
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
| `plan.md` | You | Ordered tasks, each naming the file path(s) it touches, citing reused symbols, and — where an installed plugin/skill executes the task — tagged `— via <tool>` (see step 6). |
| `checklist.md` | You | `- [ ]` items derived from the plan tasks **plus** the spec's Acceptance items, grouped into `## Wave N` parallel groups (mutually independent items per wave; waves ordered by dependency); each item carries the same `— via <tool>` tag its plan task had. |

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

6. **Map tasks to installed tooling (read installed plugins, annotate, fill gaps).** Before the plan hardens, decide *how each task gets executed* with the project's installed plugins — don't leave that to build-time improvisation.

   1. **Read what's installed.** Open `.context/equipment.json` (installed plugins + their commands + origin) and every `.context/equipment/<plugin>.md` usage doc (Purpose / When to use / When NOT to use / Constraints). This is the ground truth — don't guess from plugin names. If neither exists, there are no installed plugins; skip annotation and go straight to gap discovery only for tasks that clearly need an external capability.

   2. **Annotate the plan tasks.** For each `plan.md` task, if an installed plugin command or skill is the right executor **per its usage doc's _When to use_**, append a `— via <tool>` tag to that task line: `— via <plugin>:<command>` for a plugin slash-command, `— via /<skill>` for a skill. Respect _When NOT to use_ — never tag a task the playbook excludes. Leave a task **untagged** when a generated/adopted agent already covers it (build's keyword mapping routes those — a tag would be redundant). The tag names the *tool*, never the agent.

   3. **Discover gaps, propose installs (auto-run; install only on approval).** For a task whose capability **no** installed plugin and **no** generated specialist covers, run `dummyindex context equip discover "<capability>"` and surface the ranked candidates **with their blast radius + trust tier** (equip prints these). Then, **one plugin at a time**, ask the user before installing — honour equip's trust gate (`--yes` required for an untrusted code-runner) and capture the usage doc via equip's interview, then install:

      ```bash
      dummyindex context equip install <plugin>@<marketplace> --scope project \
        --usage-doc .context/equipment/<plugin>.md
      ```

      Annotate the task with the now-installed tool. If the user **declines**, leave the task untagged and record the gap in the Done report. Discovery is automatic; **installation is never silent.**

7. **Critique panel — ONE parallel round, then revise once (this is the multi-agent step).** Your draft is a first draft; before it hardens into a checklist, dispatch a small panel to pressure-test it. This is deliberately **light** — one round, no rebuttals, no debate, the panel only files findings; **you** are the sole reviser.

   Dispatch the three critics below as **parallel `Task` subagents — one message, three Task calls**. For each: set the `subagent_type` shown (fall back to `general-purpose` if that agent type isn't available — the inlined mandate still steers it), and **paste the mandate text into the prompt** (a fresh subagent can't resolve this skill's path — but it *can* Read the proposal + `.context/` files by their repo paths, so tell it to). Hand each critic the paths `.context/proposals/<slug>/spec.md` + `plan.md` and tell it to ground in `.context/HOW_TO_USE.md`, `.context/PROJECT.md`, the related features' `spec.md`, and `.context/conventions/`.

   | Critic | `subagent_type` | Mandate (inline this into the prompt) |
   |---|---|---|
   | **Reuse & architecture** | `Software Architect` | Read the draft spec.md + plan.md and the `.context/` grounding. Flag, with the exact spec/plan location: (a) net-new code that duplicates an existing symbol/feature the plan should reuse — cite it from `.context/map/symbols.json`; (b) a wrong seam/layer or scope creep beyond the stated intent; (c) a task that contradicts a recorded decision or a `conventions/*.md` rule. Findings only — do **not** rewrite the plan. |
   | **Risk & edge-cases** | `Code Reviewer` | Read the draft + grounding. Flag: unhandled failure modes, missing edge cases, error-handling/validation gaps, security / data-exposure / migration risks, ordering hazards between tasks, and anything the plan assumes but never establishes. Each finding: the location + the concrete risk + the minimal mitigating task. Findings only. |
   | **Testability & acceptance** | `Test Results Analyzer` | Read the draft spec.md `## Acceptance` + plan.md. Flag: acceptance criteria that aren't concrete/observable/testable, plan tasks with no way to verify them, coverage gaps, and any `— via <tool>` tag that contradicts the named plugin's _When NOT to use_ (or a task left untagged despite an obvious installed-plugin fit). For each, propose the testable rewording or the missing verification. Findings only. |

   Each critic returns concise findings tagged **BLOCK / HIGH / MEDIUM / LOW** with the location + minimal fix. **Then you revise once:** read all three sets, fold the BLOCK/HIGH findings (and any MEDIUM you agree with) into `spec.md` + `plan.md`, and note in one line what you changed and what you deliberately left. Don't re-dispatch; don't invent changes when the panel found nothing material. (Skip the panel only for a trivial, single-file change whose plan is self-evidently correct — say so if you do.)

8. **Derive `checklist.md` as ordered waves** — *after* the revision — turn the revised plan tasks plus the spec's Acceptance items into `- [ ]` items grouped under `## Wave N — <label>` headings. This is the execution surface a later step works through, and the wave structure is what lets `/dummyindex-build` dispatch items **in parallel**:

   - **Items inside one wave must be mutually independent**: they touch **disjoint files** and neither needs the other's output. The build step dispatches a whole wave concurrently — a hidden dependency inside a wave is a race.
   - **Waves run strictly in order** — put a task in the earliest wave whose prerequisites are all in earlier waves. Typical shape: wave 1 = shared scaffolding (models, schema, fixtures), middle waves = independent features/modules fanned out wide, last wave = integration + the spec's Acceptance items (they verify the whole, so they come last).
   - **When unsure whether two tasks are independent, put them in separate waves.** Serial is always correct; parallel is an optimization. A checklist of singleton waves (or no wave headings at all — plain flat list) is valid and simply builds serially.
   - Use any other heading (like the `# Checklist` title) freely — only headings starting with `Wave`/`Group` open a parallel group.

   Example:
   ```markdown
   # Checklist — <slug>

   ## Wave 1 — schema + scaffolding
   - [ ] Add widgets table migration (db/migrations/...)
   - [ ] Define Widget dataclass (app/models/widget.py)

   ## Wave 2 — independent surfaces
   - [ ] Widget CRUD endpoints (app/api/widgets.py)
   - [ ] Widget list UI component (ui/components/WidgetList.tsx) — via /frontend-design
   - [ ] Deploy a preview build (vercel) — via vercel:deploy

   ## Wave 3 — integration + acceptance
   - [ ] Wire UI to the endpoints (ui/api/client.ts)
   - [ ] Review the generated diff — via /code-review
   - [ ] Acceptance: creating a widget shows it in the list
   ```

9. **Auto-equip the toolkit for this proposal (deterministic CLI — no Task dispatch).** Once the proposal is fully scaffolded, equip the project-tuned toolkit, scoped to it, so it exists by build time:

   ```bash
   dummyindex context equip apply --for-proposal <slug> [--root <repo>]
   ```

   Equip rendering is non-LLM (detect → catalog → render). `equip apply` is **additive, never-clobber, and origin-hash baselined**, so running it on an already-equipped repo is safe and idempotent — it only fills gaps, never stomps user edits. This means `/dummyindex-build` finds `.context/equipment.json` already in place and dispatches project-tuned agents rather than `general-purpose`. You no longer need to ask the user to run `/dummyindex-equip` separately; it now happens automatically here. (Standalone `/dummyindex-equip` remains the way to re-equip or evolve the toolkit later.)

## Checklist + spec-led discipline (embed this in how you work)

- **Read `spec.md` first.** It is the source of truth for *what* and *why*. The plan serves the spec; the checklist serves both.
- **Work `checklist.md` wave-by-wave, top-to-bottom.** Items within a wave may run in parallel; a wave starts only when every earlier wave is fully ticked.
- **Tick only after verifying.** Flip `- [ ]` → `- [x]` for an item *only* once you've confirmed it (its test passes / the behavior is observed). Never tick on intent.
- **Stop and report if blocked.** If an item can't be completed (missing dependency, contradictory requirement, ambiguous scope), stop, leave it unticked, and report the blocker with a concrete next step — don't paper over it or skip ahead.

## Done

Report: the proposal path, the related features the scan surfaced, a one-line summary of the plan's shape (how many tasks, which existing symbols it reuses), **the tooling map** (which tasks were tagged `— via <tool>`, which capability gaps triggered `equip discover`, and what was installed versus declined), **the critique panel outcome** (which critics ran, what BLOCK/HIGH findings you folded in, what you deliberately left), and confirmation that the toolkit was auto-equipped for the proposal (so `/dummyindex-build` can dispatch project-tuned agents).
