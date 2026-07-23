---
name: dummyindex-plan
description: "Grounded planning for a new feature in a repo with a `.context/` index. Turns a natural-language request into `.context/proposals/{slug}/proposal.json`, `spec.md` with intent and contracts, an ordered `plan.md` naming files and reused symbols, and a wave-grouped `checklist.md` for parallel execution. Runs one lightweight parallel critique round for reuse, risk, and testability, then revises once. Claude Code can auto-equip its project toolkit and discover approved plugins; Codex stays native and non-mutating, using built-in subagents without requiring Claude equipment. Uses deterministic query retrieval and project conventions instead of guessing. Use for `/dummyindex-plan`, `$dummyindex-plan`, plan a feature, draft a spec and plan, scaffold a proposal, or pressure-test an implementation plan."
---

# /dummyindex-plan / $dummyindex-plan — Grounded planning

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, diagnose with `dummyindex context check --versions` (it reports which layer is stale), then run `/dummyindex-update` on Claude or `$dummyindex-update` on Codex to bring the CLI, skills, and this repo's wiring back into sync — the update skill is non-destructive on a curated `.context/`. Don't reach for a blunt `dummyindex install` to "fix" a version skew.

You turn a natural-language feature request into a **consistency-checked proposal** under `.context/proposals/<slug>/`. The deterministic CLI scaffolds the artifact and grounds it against the existing index; **you** draft the prose, then a **lightweight critique panel** (a few specialist agents, one parallel round) pressure-tests your draft so you revise before locking the checklist. Python is the toolbox; the panel is the second pair of eyes.

Resolve the active host before step 6. An installed non-Claude copy carries the
**Portable host compatibility** preamble and is invoked through that host's own
skill mechanism (`$dummyindex-plan` on Codex); the Claude copy is invoked as
`/dummyindex-plan`. If the host is uncertain, take the portable host path: it
is read-only with respect to host tooling. **Never run a command that writes
`.claude/**` from the portable host path.**

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

4. **Flesh out `spec.md`** — intent (problem + who), contracts (inputs/outputs/invariants/seams), and a real `## Acceptance` section: concrete, testable `- [ ]` criteria. Keep the CLI-seeded `## Consistency` block. **Read each CLI-scaffolded file (`spec.md`/`plan.md`/`checklist.md`) before editing it** — never replace unread content blindly, and preserve the structure the scaffold already seeded (especially `## Consistency`).

5. **Flesh out `plan.md`** — ordered tasks, each naming the exact file path(s) it touches. Where a task can reuse an existing symbol, cite it by name from `.context/map/symbols.json` (and the feature it lives in). Prefer reuse over net-new code.

6. **Map tasks to tooling using the active-host branch.** Before the plan
   hardens, decide how each task gets executed. A `— via` tag is reserved for a
   tool that is actually installed and callable on the active host; native
   subagent routing does not need a tag.

   **Claude Code:**

   1. Open `.context/equipment.json` and every
      `.context/equipment/<plugin>.md` usage doc. This is the ground truth for
      installed Claude plugins, generated/adopted agents, their commands, and
      their _When to use_ / _When NOT to use_ constraints.
   2. Tag a matching task `— via <plugin>:<command>` or `— via /<skill>`.
      Leave it untagged when a generated/adopted agent already covers it.
   3. For a real uncovered capability, run
      `dummyindex context equip discover "<capability>"`, show trust and blast
      radius, and install at most one candidate only after explicit approval:

      ```bash
      dummyindex context equip install <plugin>@<marketplace> --scope project \
        --usage-doc .context/equipment/<plugin>.md
      ```

      Respect the `--yes` trust gate for untrusted code-running plugins. If the
      user declines, leave the task untagged and report the gap.

   **Portable host path** (skill-native hosts — Codex, Cursor, and similar):

   1. Inspect only skills, plugins, MCP tools, and custom agents that the
      current session exposes on this host. A leftover `.context/equipment.json`
      or `.claude/` tree may describe a Claude setup; it is not proof that this
      host can invoke those tools.
   2. Tag an available skill as `— via $<skill>` (or another exact host-native
      tool name) only when it is binding. Leave ordinary implementation and
      review tasks untagged so build routes them to the host's native `worker`,
      `explorer`, or `default` subagents with the mandate inlined.
   3. **Do not run `dummyindex context equip discover`, `install`, `apply`,
      `add-specialist`, or any other Claude equipment mutation. Do not create
      `.context/equipment.json` or write `.claude/**`.** Record an uncovered
      external capability as a gap; it does not block native subagent execution.

7. **Critique panel — ONE parallel round, then revise once (this is the multi-agent step).** Your draft is a first draft; before it hardens into a checklist, dispatch a small panel to pressure-test it. This is deliberately **light** — one round, no rebuttals, no debate, the panel only files findings; **you** are the sole reviser.

   Use the active host's native delegation mechanism and paste the full mandate
   into every prompt. On Claude, use the preferred named `subagent_type` when it
   is available and otherwise `general-purpose`. On the portable host path
   (e.g. Codex), these are read-only reviews, so use three parallel built-in `explorer` subagents; if `explorer` is unavailable, use `default`. Do not inspect or create `.claude/agents/` to make a critic available on that host.

   Hand each critic `.context/proposals/<slug>/spec.md` and `plan.md`; tell it to
   ground in `.context/HOW_TO_USE.md`, `.context/PROJECT.md`, the related feature
   specs, and `.context/conventions/`.

   | Critic | Claude preferred type | Mandate (inline this into the prompt) |
   |---|---|---|
   | **Reuse & architecture** | `Software Architect` → `general-purpose` | Read the draft spec.md + plan.md and the `.context/` grounding. Flag, with the exact spec/plan location: (a) net-new code that duplicates an existing symbol/feature the plan should reuse — cite it from `.context/map/symbols.json`; (b) a wrong seam/layer or scope creep beyond the stated intent; (c) a task that contradicts a recorded decision or a `conventions/*.md` rule. Findings only — do **not** rewrite the plan. |
   | **Risk & edge-cases** | `Code Reviewer` → `general-purpose` | Read the draft + grounding. Flag: unhandled failure modes, missing edge cases, error-handling/validation gaps, security / data-exposure / migration risks, ordering hazards between tasks, and anything the plan assumes but never establishes. Each finding: the location + the concrete risk + the minimal mitigating task. Findings only. |
   | **Testability & acceptance** | `Test Results Analyzer` → `general-purpose` | Read the draft spec.md `## Acceptance` + plan.md. Flag: acceptance criteria that aren't concrete/observable/testable, plan tasks with no way to verify them, coverage gaps, and any `— via <tool>` tag that contradicts the named plugin's _When NOT to use_ (or a task left untagged despite an obvious installed-plugin fit). For each, propose the testable rewording or the missing verification. Findings only. |

   Each critic returns concise findings tagged **BLOCK / HIGH / MEDIUM / LOW** with the location + minimal fix. **Then you revise once:** read all three sets, fold the BLOCK/HIGH findings (and any MEDIUM you agree with) into `spec.md` + `plan.md`, and note in one line what you changed and what you deliberately left. Don't re-dispatch; don't invent changes when the panel found nothing material. (Skip the panel only for a trivial, single-file change whose plan is self-evidently correct — say so if you do.)

8. **Derive `checklist.md` as ordered waves** — *after* the revision — turn the revised plan tasks plus the spec's Acceptance items into `- [ ]` items grouped under `## Wave N — <label>` headings. This is the execution surface a later step works through, and the wave structure is what lets `/dummyindex-build` dispatch items **in parallel**:

   - **Items inside one wave must be mutually independent**: they touch **disjoint files** and neither needs the other's output. The build step dispatches a whole wave concurrently — a hidden dependency inside a wave is a race.
   - **Waves run strictly in order** — put a task in the earliest wave whose prerequisites are all in earlier waves. Typical shape: wave 1 = shared scaffolding (models, schema, fixtures), middle waves = independent features/modules fanned out wide, last wave = integration + the spec's Acceptance items (they verify the whole, so they come last).
   - **When unsure whether two tasks are independent, put them in separate waves.** Serial is always correct; parallel is an optimization. A checklist of singleton waves (or no wave headings at all — plain flat list) is valid and simply builds serially.
   - Use any other heading (like the `# Checklist` title) freely — only headings starting with `Wave`/`Group` open a parallel group.
   - **Open decisions never become plain checklist items.** An unresolved design/approval question (settle the RLS / tenant-isolation model, resolve a `DECISIONS.md` open question, pick between two approaches) is **not** implementable code — if it ships as an ordinary `- [ ]` item, build will try to dispatch the decision to a subagent. Resolve it *before* deriving the checklist: put it in an `## Open questions` block in `spec.md` and ask the user. If a decision is genuinely deferred to build time, mark its item with a leading `**GATE**` so build treats it as a main-session item and escalates to the user instead of dispatching it. Likewise, an item that can only run with tools the **main session** has (a hosted/MCP server a subagent can't reach) should carry a `— via <tool>` tag — the build CLI classifies both `**GATE**` and `— via` items as `dispatch: main-session`, so the conductor handles them itself.

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

9. **Finish with the active-host routing policy.**

   **Claude Code:** auto-equip the project-tuned toolkit for this proposal:

   ```bash
   dummyindex context equip apply --for-proposal <slug> [--root <repo>]
   ```

   The render is deterministic, additive, origin-hash baselined, and
   idempotent. It creates or updates the Claude equipment manifest and only
   fills safe gaps; user edits remain untouched.

   **Portable host path:** do not run `equip apply` (or any other equip
   mutation), and do not create `.claude/**`. The proposal is build-ready
   without `.context/equipment.json`: `$dummyindex-build` (or the equivalent
   build invocation on that host) routes untagged work to native built-in
   subagents and inlines the grounding and mandate.

## Checklist + spec-led discipline (embed this in how you work)

- **Read `spec.md` first.** It is the source of truth for *what* and *why*. The plan serves the spec; the checklist serves both.
- **Work `checklist.md` wave-by-wave, top-to-bottom.** Items within a wave may run in parallel; a wave starts only when every earlier wave is fully ticked.
- **Tick only after verifying.** Flip `- [ ]` → `- [x]` for an item *only* once you've confirmed it (its test passes / the behavior is observed). Never tick on intent.
- **Stop and report if blocked.** If an item can't be completed (missing dependency, contradictory requirement, ambiguous scope), stop, leave it unticked, and report the blocker with a concrete next step — don't paper over it or skip ahead.

## Done

Report: the proposal path, related features, task/reuse summary, **tooling map**
(tags and gaps; on Claude, discoveries and approved installs), and **critique
outcome** (critics, BLOCK/HIGH fixes, deliberate omissions). On Claude, confirm
that the toolkit was auto-equipped. On the portable host path, confirm that no
Claude equipment was created and that native subagent routing will be used at
build time.
