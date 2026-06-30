# Plan-time Plugin Annotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/dummyindex-plan` annotate each task/checklist item with the installed plugin command or skill that will execute it (`— via <tool>`), auto-discover and (with approval) install a plugin for any uncovered capability, and have `/dummyindex-build` honor the tag as a dispatch directive.

**Architecture:** Skill-only change. The `— via <tool>` tag rides as plain text inside the `plan.md` task and `checklist.md` item, so build's existing `dummyindex context build --next-wave` emits it verbatim — no `mapping.py`/CLI change. Two files edited: `dummyindex/skills/plan/SKILL.md` (new step + supporting edits) and `dummyindex/skills/build/SKILL.md` (one honoring paragraph).

**Tech Stack:** Markdown skill files. Verification is `grep`-based assertion (the "test"), plus a final guard that no `*.py` file changed.

**Spec:** `docs/specs/2026-06-12-plan-plugin-annotation-design.md`

---

## File Structure

- **Modify:** `dummyindex/skills/plan/SKILL.md` — frontmatter `description`; "What you produce" table note; new step 6 "Map tasks to installed tooling" (renumber old 6/7/8 → 7/8/9); testability-critic mandate; checklist example; Done report. This file owns the *planning* behavior.
- **Modify:** `dummyindex/skills/build/SKILL.md` — one paragraph in dispatch step 3. This file owns *honoring* the tag at execution.
- No other files. No Python.

Convention used throughout: `— via <plugin>:<command>` for a plugin slash-command, `— via /<skill>` for a skill, no tag for work a generated/adopted agent already covers.

---

## Task 1: Annotation convention + "What you produce" note (plan/SKILL.md)

**Files:**
- Modify: `dummyindex/skills/plan/SKILL.md` (the `## What you produce` table, ~line 17-22)

- [ ] **Step 1: Assertion — the note does not yet exist**

Run: `grep -c "via <tool>" dummyindex/skills/plan/SKILL.md`
Expected: `0`

- [ ] **Step 2: Edit the `plan.md` and `checklist.md` rows of the table**

In `## What you produce`, replace the `plan.md` and `checklist.md` table rows so they mention the tag. Find this exact block:

```markdown
| `plan.md` | You | Ordered tasks, each naming the file path(s) it touches, citing reused symbols. |
| `checklist.md` | You | `- [ ]` items derived from the plan tasks **plus** the spec's Acceptance items, grouped into `## Wave N` parallel groups (mutually independent items per wave; waves ordered by dependency). |
```

Replace with:

```markdown
| `plan.md` | You | Ordered tasks, each naming the file path(s) it touches, citing reused symbols, and — where an installed plugin/skill executes the task — tagged `— via <tool>` (see step 6). |
| `checklist.md` | You | `- [ ]` items derived from the plan tasks **plus** the spec's Acceptance items, grouped into `## Wave N` parallel groups (mutually independent items per wave; waves ordered by dependency); each item carries the same `— via <tool>` tag its plan task had. |
```

- [ ] **Step 3: Assertion — the note now exists**

Run: `grep -c "via <tool>" dummyindex/skills/plan/SKILL.md`
Expected: `2`

- [ ] **Step 4: Commit**

```bash
git add dummyindex/skills/plan/SKILL.md
git commit -m "docs(plan): note — via <tool> tag in the produced-files table"
```

---

## Task 2: Frontmatter description clause (plan/SKILL.md)

**Files:**
- Modify: `dummyindex/skills/plan/SKILL.md:3` (the `description:` line)

- [ ] **Step 1: Assertion — description has no plugin-annotation clause yet**

Run: `grep -c "annotates tasks with the installed plugin" dummyindex/skills/plan/SKILL.md`
Expected: `0`

- [ ] **Step 2: Edit the description**

In the frontmatter `description:`, find this exact sentence (mid-description):

```
Reuses the deterministic `query` retrieval to ground the plan in existing features + conventions; no guessing about what already exists.
```

Replace with:

```
Annotates each task with the installed plugin command/skill that will execute it (`— via <tool>`), and for any capability no installed plugin or generated specialist covers it auto-runs `equip discover` and (with your approval) installs one. Reuses the deterministic `query` retrieval to ground the plan in existing features + conventions; no guessing about what already exists.
```

- [ ] **Step 3: Assertion — clause present, file still has valid frontmatter**

Run: `grep -c "Annotates each task with the installed plugin" dummyindex/skills/plan/SKILL.md`
Expected: `1`

Run: `head -1 dummyindex/skills/plan/SKILL.md`
Expected: `---`

- [ ] **Step 4: Commit**

```bash
git add dummyindex/skills/plan/SKILL.md
git commit -m "docs(plan): surface plugin annotation in skill description"
```

---

## Task 3: New step 6 "Map tasks to installed tooling" + renumber 6/7/8 → 7/8/9 (plan/SKILL.md)

**Files:**
- Modify: `dummyindex/skills/plan/SKILL.md` (insert after current step 5, renumber the three following step headers)

This is the load-bearing task. Do the renumbering FIRST (so headers don't collide), then insert the new step.

- [ ] **Step 1: Assertion — current headers are 6/7/8, no step labelled "Map tasks to installed tooling"**

Run: `grep -nE "^[0-9]+\. \*\*" dummyindex/skills/plan/SKILL.md`
Expected: lines numbered `1.` through `8.` (eight numbered steps), none mentioning tooling.

- [ ] **Step 2: Renumber the auto-equip step header 8 → 9**

Find this exact header line:

```
8. **Auto-equip the toolkit for this proposal (deterministic CLI — no Task dispatch).** Once the proposal is fully scaffolded, equip the project-tuned toolkit, scoped to it, so it exists by build time:
```

Replace `8.` with `9.`:

```
9. **Auto-equip the toolkit for this proposal (deterministic CLI — no Task dispatch).** Once the proposal is fully scaffolded, equip the project-tuned toolkit, scoped to it, so it exists by build time:
```

- [ ] **Step 3: Renumber the derive-checklist step header 7 → 8**

Find this exact header line:

```
7. **Derive `checklist.md` as ordered waves** — *after* the revision — turn the revised plan tasks plus the spec's Acceptance items into `- [ ]` items grouped under `## Wave N — <label>` headings. This is the execution surface a later step works through, and the wave structure is what lets `/dummyindex-build` dispatch items **in parallel**:
```

Replace `7.` with `8.`:

```
8. **Derive `checklist.md` as ordered waves** — *after* the revision — turn the revised plan tasks plus the spec's Acceptance items into `- [ ]` items grouped under `## Wave N — <label>` headings. This is the execution surface a later step works through, and the wave structure is what lets `/dummyindex-build` dispatch items **in parallel**:
```

- [ ] **Step 4: Renumber the critique-panel step header 6 → 7**

Find this exact header line:

```
6. **Critique panel — ONE parallel round, then revise once (this is the multi-agent step).** Your draft is a first draft; before it hardens into a checklist, dispatch a small panel to pressure-test it. This is deliberately **light** — one round, no rebuttals, no debate, the panel only files findings; **you** are the sole reviser.
```

Replace `6.` with `7.`:

```
7. **Critique panel — ONE parallel round, then revise once (this is the multi-agent step).** Your draft is a first draft; before it hardens into a checklist, dispatch a small panel to pressure-test it. This is deliberately **light** — one round, no rebuttals, no debate, the panel only files findings; **you** are the sole reviser.
```

- [ ] **Step 5: Insert the new step 6 immediately before the (now) step 7 critique panel**

Insert this block on its own lines, directly before the `7. **Critique panel ...` line:

```markdown
6. **Map tasks to installed tooling (read installed plugins, annotate, fill gaps).** Before the plan hardens, decide *how each task gets executed* with the project's installed plugins — don't leave that to build-time improvisation.

   1. **Read what's installed.** Open `.context/equipment.json` (installed plugins + their commands + origin) and every `.context/equipment/<plugin>.md` usage doc (Purpose / When to use / When NOT to use / Constraints). This is the ground truth — don't guess from plugin names. If neither exists, there are no installed plugins; skip annotation and go straight to gap discovery only for tasks that clearly need an external capability.

   2. **Annotate the plan tasks.** For each `plan.md` task, if an installed plugin command or skill is the right executor **per its usage doc's _When to use_**, append a `— via <tool>` tag to that task line: `— via <plugin>:<command>` for a plugin slash-command, `— via /<skill>` for a skill. Respect _When NOT to use_ — never tag a task the playbook excludes. Leave a task **untagged** when a generated/adopted agent already covers it (build's keyword mapping routes those — a tag would be redundant). The tag names the *tool*, never the agent.

   3. **Discover gaps, propose installs (auto-run; install only on approval).** For a task whose capability **no** installed plugin and **no** generated specialist covers, run `dummyindex context equip discover "<capability>"` and surface the ranked candidates **with their blast radius + trust tier** (equip prints these). Then, **one plugin at a time**, ask the user before installing — honour equip's trust gate (`--yes` required for an untrusted code-runner) and capture the usage doc via equip's interview, then install:

      ```bash
      dummyindex context equip install <plugin>@<marketplace> --scope project \
        --usage-doc .context/equipment/<plugin>.md
      ```

      Annotate the task with the now-installed tool. If the user **declines**, leave the task untagged and record the gap in the Done report. Discovery is automatic; **installation is never silent.**

```

- [ ] **Step 6: Assertion — headers now run 1..9 and the new step exists**

Run: `grep -nE "^[0-9]+\. \*\*" dummyindex/skills/plan/SKILL.md`
Expected: nine numbered steps `1.`–`9.`, with `6.` reading "Map tasks to installed tooling..." and `9.` reading "Auto-equip the toolkit...".

Run: `grep -c "Map tasks to installed tooling" dummyindex/skills/plan/SKILL.md`
Expected: `1`

- [ ] **Step 7: Assertion — no duplicate step numbers**

Run: `grep -oE "^[0-9]+\. \*\*" dummyindex/skills/plan/SKILL.md | sort | uniq -d`
Expected: (empty output — no duplicates)

- [ ] **Step 8: Commit**

```bash
git add dummyindex/skills/plan/SKILL.md
git commit -m "feat(plan): add 'Map tasks to installed tooling' step (annotate + gap discover)"
```

---

## Task 4: Testability-critic mandate references the tags (plan/SKILL.md)

**Files:**
- Modify: `dummyindex/skills/plan/SKILL.md` (the **Testability & acceptance** critic row in the critique-panel table)

- [ ] **Step 1: Assertion — critic mandate has no tag check yet**

Run: `grep -c "via <tool>\` tag" dummyindex/skills/plan/SKILL.md`
Expected: `0`

- [ ] **Step 2: Edit the testability critic mandate**

Find this exact table-cell text (the Mandate column of the **Testability & acceptance** row):

```
Read the draft spec.md `## Acceptance` + plan.md. Flag: acceptance criteria that aren't concrete/observable/testable, plan tasks with no way to verify them, and coverage gaps. For each, propose the testable rewording or the missing verification. Findings only.
```

Replace with:

```
Read the draft spec.md `## Acceptance` + plan.md. Flag: acceptance criteria that aren't concrete/observable/testable, plan tasks with no way to verify them, coverage gaps, and any `— via <tool>` tag that contradicts the named plugin's _When NOT to use_ (or a task left untagged despite an obvious installed-plugin fit). For each, propose the testable rewording or the missing verification. Findings only.
```

- [ ] **Step 3: Assertion — tag check present**

Run: `grep -c "via <tool>\` tag that contradicts" dummyindex/skills/plan/SKILL.md`
Expected: `1`

- [ ] **Step 4: Commit**

```bash
git add dummyindex/skills/plan/SKILL.md
git commit -m "docs(plan): testability critic checks — via tags against usage docs"
```

---

## Task 5: Checklist example shows a `— via` tag (plan/SKILL.md)

**Files:**
- Modify: `dummyindex/skills/plan/SKILL.md` (the fenced checklist example under the derive-checklist step)

- [ ] **Step 1: Assertion — example has no tag yet**

Run: `grep -c "via vercel:deploy" dummyindex/skills/plan/SKILL.md`
Expected: `0`

- [ ] **Step 2: Edit the example's Wave 2 + Wave 3 lines**

Find this exact block inside the fenced ```markdown example:

```markdown
   ## Wave 2 — independent surfaces
   - [ ] Widget CRUD endpoints (app/api/widgets.py)
   - [ ] Widget list UI component (ui/components/WidgetList.tsx)

   ## Wave 3 — integration + acceptance
   - [ ] Wire UI to the endpoints (ui/api/client.ts)
   - [ ] Acceptance: creating a widget shows it in the list
```

Replace with (Wave 2 gains a UI build via an installed plugin; Wave 3 gains a review via an installed command):

```markdown
   ## Wave 2 — independent surfaces
   - [ ] Widget CRUD endpoints (app/api/widgets.py)
   - [ ] Widget list UI component (ui/components/WidgetList.tsx) — via frontend-design
   - [ ] Deploy a preview build (vercel) — via vercel:deploy

   ## Wave 3 — integration + acceptance
   - [ ] Wire UI to the endpoints (ui/api/client.ts)
   - [ ] Review the generated diff — via /code-review
   - [ ] Acceptance: creating a widget shows it in the list
```

- [ ] **Step 3: Assertion — tagged lines present**

Run: `grep -c "via vercel:deploy" dummyindex/skills/plan/SKILL.md`
Expected: `1`

Run: `grep -c "via /code-review" dummyindex/skills/plan/SKILL.md`
Expected: `1`

- [ ] **Step 4: Commit**

```bash
git add dummyindex/skills/plan/SKILL.md
git commit -m "docs(plan): show — via tags in the checklist example"
```

---

## Task 6: Done report mentions plugin annotation (plan/SKILL.md)

**Files:**
- Modify: `dummyindex/skills/plan/SKILL.md` (the `## Done` section, last paragraph)

- [ ] **Step 1: Assertion — Done report has no tooling line yet**

Run: `grep -c "which tasks were tagged" dummyindex/skills/plan/SKILL.md`
Expected: `0`

- [ ] **Step 2: Edit the Done report**

Find this exact sentence at the end of the `## Done` section:

```
Report: the proposal path, the related features the scan surfaced, a one-line summary of the plan's shape (how many tasks, which existing symbols it reuses), **the critique panel outcome** (which critics ran, what BLOCK/HIGH findings you folded in, what you deliberately left), and confirmation that the toolkit was auto-equipped for the proposal (so `/dummyindex-build` can dispatch project-tuned agents).
```

Replace with:

```
Report: the proposal path, the related features the scan surfaced, a one-line summary of the plan's shape (how many tasks, which existing symbols it reuses), **the tooling map** (which tasks were tagged `— via <tool>`, which capability gaps triggered `equip discover`, and what was installed versus declined), **the critique panel outcome** (which critics ran, what BLOCK/HIGH findings you folded in, what you deliberately left), and confirmation that the toolkit was auto-equipped for the proposal (so `/dummyindex-build` can dispatch project-tuned agents).
```

- [ ] **Step 3: Assertion — tooling line present**

Run: `grep -c "which tasks were tagged" dummyindex/skills/plan/SKILL.md`
Expected: `1`

- [ ] **Step 4: Commit**

```bash
git add dummyindex/skills/plan/SKILL.md
git commit -m "docs(plan): report the tooling map in the Done summary"
```

---

## Task 7: Build honors the `— via` tag (build/SKILL.md)

**Files:**
- Modify: `dummyindex/skills/build/SKILL.md` (dispatch step 3, ~line 34)

- [ ] **Step 1: Assertion — no honoring note yet**

Run: `grep -c "via <tool>" dummyindex/skills/build/SKILL.md`
Expected: `0`

- [ ] **Step 2: Append the honoring paragraph to dispatch step 3**

Find the end of dispatch step 3 — this exact sentence closes it:

```
The wave's items are mutually independent by construction (the plan grouped them that way) — if, mid-dispatch, you realize two items actually collide on a file, fall back to dispatching those two serially and say so in the report.
```

Replace with that sentence **plus** a new paragraph after it:

```
The wave's items are mutually independent by construction (the plan grouped them that way) — if, mid-dispatch, you realize two items actually collide on a file, fall back to dispatching those two serially and say so in the report.

   **Honor `— via <tool>` tags.** A checklist item may carry a trailing `— via <tool>` tag the plan step added (`— via <plugin>:<command>` for a plugin slash-command, `— via /<skill>` for a skill). When it does, that tag is a **directive, not a hint**: route the item through that tool. For a **skill**, tell the dispatched subagent to invoke it via the Skill tool as the way it does the work. For a **slash-command** a subagent can't run itself, run it from the main session around the dispatch (e.g. dispatch the build, then run the command on the result). The CLI's `agent`/`subagent_type` mapping is unchanged — the tag layers an execution instruction on top of it, it does not replace the matched agent.
```

- [ ] **Step 3: Assertion — note present**

Run: `grep -c "Honor \`— via <tool>\` tags" dummyindex/skills/build/SKILL.md`
Expected: `1`

- [ ] **Step 4: Commit**

```bash
git add dummyindex/skills/build/SKILL.md
git commit -m "feat(build): honor — via <tool> tags as dispatch directives"
```

---

## Task 8: Final guard — no Python changed, both skills consistent

**Files:**
- None (verification only)

- [ ] **Step 1: Assertion — only the two SKILL.md files (and the docs) changed across this branch**

Run: `git diff --name-only main...HEAD -- '*.py' | head`
Expected: (empty — no Python files changed)

Run: `git diff --name-only main...HEAD`
Expected: only `dummyindex/skills/plan/SKILL.md`, `dummyindex/skills/build/SKILL.md`, `docs/specs/2026-06-12-plan-plugin-annotation-design.md`, `docs/plans/2026-06-12-plan-plugin-annotation.md`.

- [ ] **Step 2: Assertion — plan step numbering is a clean 1..9 with no gaps/dupes**

Run: `grep -oE "^[0-9]+\. \*\*" dummyindex/skills/plan/SKILL.md`
Expected: exactly `1.`–`9.` in order, each once.

- [ ] **Step 3: Assertion — the convention is defined once and the example uses it**

Run: `grep -c "via <plugin>:<command>" dummyindex/skills/plan/SKILL.md`
Expected: `>=1` (the convention is stated in step 6).

- [ ] **Step 4: Run the repo's existing test suite as a regression guard (docs-only, should be unaffected)**

Run: `uv run pytest -q`
Expected: PASS (same count as before the branch — these edits touch no code).

- [ ] **Step 5: No commit** (verification task; nothing to commit).

---

## Self-Review

**Spec coverage** (against `docs/specs/2026-06-12-plan-plugin-annotation-design.md` Acceptance):
- New "Map tasks to installed tooling" step between flesh-plan and critique → **Task 3**.
- `— via <tool>` convention defined once + used in checklist example → **Task 3 (step 6 body) + Task 5**.
- Gap discovery auto-run; install gated on approval + trust + usage doc → **Task 3 sub-step 3**.
- Checklist derivation + testability critic reference the tags → **Task 1 (checklist row) + Task 4**.
- Frontmatter description + Done report mention annotation → **Task 2 + Task 6**.
- build/SKILL.md honors the tag → **Task 7**.
- No Python changes → **Task 8 step 1**.

All Acceptance items map to a task. No gaps.

**Placeholder scan:** every Edit step gives the exact find/replace text; no TBD/TODO. ✓

**Consistency:** the tag string `— via <tool>` and its two forms (`— via <plugin>:<command>`, `— via /<skill>`) are identical across Tasks 1, 3, 4, 5, 6, 7. The renumber (Task 3) does old-8→9, old-7→8, old-6→7 top-down so headers never collide mid-edit. ✓
