# Plan-time plugin annotation — design

**Date:** 2026-06-12
**Status:** approved (brainstorm)
**Surface:** `dummyindex/skills/plan/SKILL.md` (primary), `dummyindex/skills/build/SKILL.md` (one honoring note). No Python / CLI change.

## Problem

The `plan → build` path is **plugin-blind**. `equip` installs plugins (recording
them in `.context/equipment.json` with an origin, and a usage playbook at
`.context/equipment/<plugin>.md`), but:

- `plan.md` / `checklist.md` never reference those plugins, and
- build's item→agent mapping (`buildloop/mapping.py`) only matches **generated /
  adopted agents** by capability keywords — it has no notion of "execute this
  task with plugin X's `/command`."

So a repo can have, say, `vercel` and `code-review` plugins installed, and the
plan that drives the build says nothing about *when or how* they should be used.
The plan must capture **how installed plugins and their commands are used for
execution**.

## Approach (chosen)

A **skill-only** change. The annotation travels as plain text inside the
`plan.md` task and `checklist.md` item, so build's existing
`dummyindex context build --next-wave` already emits it verbatim to the
dispatched agent — no `mapping.py` or CLI change is needed. The
agent/`subagent_type` routing is untouched; the tag is an *additional* execution
directive layered on top.

Earlier-considered alternatives, rejected:

- *CLI surfaces installed plugins into `proposal.json`* — more deterministic but
  adds Python surface; the skill-reads-files path is lighter and sufficient.
- *Dedicated `## Tooling` section in spec.md* — chosen output is per-task
  annotations, not a separate table.

## The annotation convention

A task / checklist item that a plugin command or skill should execute gets a
trailing tag:

```markdown
- [ ] Deploy preview build — via vercel:deploy
- [ ] Review the generated diff — via /code-review
- [ ] Add widgets table migration (db/migrations/0007.sql)   ← no tag
```

- `— via <plugin>:<command>` — a plugin slash-command.
- `— via /<skill>` — a skill invoked through the Skill tool.
- **No tag** for work an already-mapped **generated/adopted agent** covers
  (build's `mapping.py` routes those by capability keywords; a tag would be
  redundant). The tag names the *tool*, never the agent.

## Plan flow change — new step "Map tasks to installed tooling"

Slots in **after** plan.md is fleshed out (current step 5) and **before** the
critique panel (step 6). Three sub-steps:

1. **Read what's installed (grounding, no guessing).** Read
   `.context/equipment.json` (installed plugins + their commands + origin) and
   each `.context/equipment/<plugin>.md` usage doc (Purpose / When to use /
   When NOT to use / Constraints). If neither exists, there are no installed
   plugins yet — skip annotation, fall through to gap discovery only if a task
   clearly needs an external capability.

2. **Annotate.** For each plan task, if an installed plugin command or skill is
   the right executor **per its usage doc's _When to use_**, append the
   `— via <tool>` tag. Respect _When NOT to use_ — do not tag a task the
   playbook excludes.

3. **Discover gaps + propose installs (auto-run, ask before install).** For a
   task whose capability **no** installed plugin and **no** generated specialist
   covers, run:

   ```bash
   dummyindex context equip discover "<capability>"
   ```

   Surface the ranked candidates **with blast radius + trust tier** (equip
   already prints these). Then, **one plugin at a time, with explicit user
   approval**, install the chosen one — honouring equip's existing trust gate
   (`--yes` required for an untrusted code-runner) and capturing its usage doc:

   ```bash
   dummyindex context equip install <plugin>@<marketplace> --scope project \
     --usage-doc .context/equipment/<plugin>.md
   ```

   (Follow equip's usage interview to write that doc before installing.) Then
   annotate the task with the now-installed tool. If the user **declines**, the
   task stays un-annotated and the gap is recorded in the Done report. Discovery
   is automatic; **installation is never silent.**

Then:

- **Step 7 (derive checklist)** carries the same `— via` tags onto the checklist
  items.
- **Step 8 (auto-equip apply)** is unchanged.
- The critique panel's **testability critic** gains a sentence: flag a `— via`
  tag that contradicts the named plugin's _When NOT to use_, or a task left
  un-annotated despite an obvious installed fit.

## Build honoring note (`build/SKILL.md`, dispatch step 3)

One paragraph: when a wave item carries a `— via <tool>` tag, the build
conductor routes it through that tool — invoking a plugin **skill** via the
Skill tool inside the dispatched subagent, or, for a **slash-command** the
subagent can't run itself, executing it from the main session around the
dispatch. The tag is a **directive, not a hint.** No `mapping.py` change — the
`subagent_type` mapping is untouched; the tag is an additional execution
instruction.

## Discoverability

- The plan skill's frontmatter `description` gains a clause: "...annotates tasks
  with the installed plugin command/skill that will execute them, discovering
  and (with approval) installing a plugin for any uncovered capability..."
- The closing **Done** report gains a line: which tasks were tagged `— via`,
  which gaps triggered discovery, and what was installed vs. declined.

## Out of scope

- No change to `buildloop/mapping.py`, `proposals/*`, or any CLI command.
- No new annotation parser — the tag is human/agent-read prose, not machine-parsed.
- Vendored-collection discovery (loose agents/skills) remains future work, as in
  the equip plugin-manager spec.

## Acceptance

- [ ] `plan/SKILL.md` has a new "Map tasks to installed tooling" step between
      flesh-plan and the critique panel, covering read → annotate → discover-gaps.
- [ ] The `— via <tool>` convention is defined once and used in the checklist
      example.
- [ ] Gap discovery is auto-run; install is gated on per-plugin user approval +
      equip's trust rules + a captured usage doc.
- [ ] Step 7 (checklist derivation) and the testability critic reference the tags.
- [ ] `plan/SKILL.md` frontmatter `description` and the Done report mention plugin
      annotation.
- [ ] `build/SKILL.md` dispatch step honors a `— via` tag as a directive.
- [ ] No Python file changes; `git diff --name-only` touches only the two SKILL.md
      files (+ this spec).
