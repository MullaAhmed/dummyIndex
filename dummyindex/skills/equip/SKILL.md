---
name: dummyindex-equip
description: Render a SMALL, project-tuned toolkit into `.claude/` from this repo's `.context/` spine — a stack implementer agent and a verify skill, grounded in the project's own conventions, plus a formatter hook recorded for review. Additive and never-clobber. Triggers — `/dummyindex-equip`, "equip the project", "equip this repo", "build tooling for this repo".
allowed-tools: Read, Write, Bash
---

# /dummyindex-equip — equip the project with a tuned toolkit

You turn this repo's generated `.context/` spine into a small set of Claude Code
tools tuned to *this* project: a stack-aware implementer agent and a verify
skill, each grounded in the repo's real conventions so they consult the spine at
runtime instead of inventing patterns. A detected formatter (ruff/black/
prettier) is recorded for a PostToolUse format hook you present for the user to
apply.

This is **templates-first**: the tools are rendered from fixed templates with
project values filled in. You do not free-form or AI-generate agents here.

## Safety framing (state this to the user)

- **Additive + never-clobber.** Every write target is checked first. A
  pre-existing **user** file at a target path is **skipped, not overwritten**,
  and the skip is reported. Generated files carry a `<!-- dummyindex:generated -->`
  sentinel so a re-run can safely regenerate its own output.
- **No settings.json edit in this step.** The formatter hook is *recorded* in
  `.context/equipment.json` only; applying it to `.claude/settings.json` is a
  separate, user-confirmed action.

## What you do

1. **Preflight (read-only).** The command runs `dummyindex context preflight`
   internally so it knows what already exists under `.claude/`. Nothing is
   written before this.
2. **Run equip.**
   - Preview first: `dummyindex context equip --dry-run` — prints the plan and
     writes nothing. Show it to the user.
   - Apply: `dummyindex context equip` — renders the toolkit additively and
     writes `.context/equipment.json`.
   - Scope a proposal with `--for-proposal <id>` if the user is equipping for a
     specific planned change (the rendered set is the same; the flag documents
     intent).
3. **Present the proposed toolkit** with the safety framing above: the
   implementer agent (`.claude/agents/<stack>-implementer.md`), the verify skill
   (`.claude/skills/<proj>-verify/SKILL.md`), and any recorded format hook.
4. **Report** what was written, what was skipped (and why), and the manifest
   path. If a format hook was recorded, point the user at INTEGRATION-style
   guidance to apply it to `settings.json` only if they want it.

## Discipline (spec-led)

- **Read `.context/HOW_TO_USE.md` first** — the generated tools are grounded in
  it and in `.context/conventions/`. If `.context/` is absent, tell the user to
  run `/dummyindex` first; equip has nothing to ground against without it.
- When `.context/` disagrees with the code, **the code wins** — flag the drift.
- Do not gold-plate. The MVP renders exactly two tools plus the optional hook
  record. A bigger toolkit is a separate ask.

## Checklist (verify before claiming done)

- [ ] `dummyindex context equip --dry-run` was shown and wrote nothing.
- [ ] The implementer agent + verify skill were written under `.claude/`
      additively (or skipped because a user file already sat there — reported).
- [ ] `.context/equipment.json` exists with one item per tool, each carrying
      `capabilities` and `grounded_in` (the `.context/` docs it cites).
- [ ] Generated tool prompts reference `.context/` (grounding present).
- [ ] The user was told what was written vs skipped, with the safety framing.
