---
name: dummyindex-equip
description: Render and EVOLVE a project-tuned Claude Code toolkit from this repo's `.context/` spine — stack implementer + tester + reviewer agents and a verify skill, grounded in the project's own conventions, plus a PostToolUse formatter hook wired into settings.json and registry/project specialists adopted to cover capability gaps. Hash-baselined lifecycle (status / refresh / reset / uninstall) and a sanctioned patch seam mean generated tools improve over time without ever clobbering a user edit. Triggers — `/dummyindex-equip`, "equip the project", "equip this repo", "build tooling for this repo".
allowed-tools: Read, Write, Bash
---

# /dummyindex-equip — equip the project with a tuned, evolving toolkit

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, re-run `dummyindex install --scope user`.

You turn this repo's generated `.context/` spine into a small set of Claude Code
tools tuned to *this* project, each grounded in the repo's real conventions so
they consult the spine at runtime instead of inventing patterns:

- a **`<stack>-implementer`** agent and a **`<stack>-tester`** agent,
- a **`<proj>-reviewer`** agent (grounded in `.context/conventions/` + feature `concerns.md`),
- a **`<proj>-verify`** skill (embeds the project's test/lint/typecheck commands),
- a **PostToolUse format hook** wired into `.claude/settings.json` when a formatter is detected,
- plus any **adopted specialists** (project agents under `.claude/agents/`, or
  known-registry agents like *Data Engineer*) that cover capability gaps —
  recorded in the manifest only, never written as files.

All of this is **codified policy**, not free-form generation: deterministic Python
decides what to detect, generate, adopt, and wire. You drive the CLI and present
the result; you do not hand-author agents here.

## Safety framing (state this to the user)

- **Never clobber.** A pre-existing **user** file at a target path is **skipped,
  not overwritten** (and the skip is reported). Generated files carry a
  `<!-- dummyindex:generated -->` marker, but the **origin-hash is the
  authority**: once you hand-edit a generated file it becomes **USER_MODIFIED**
  and is **preserved forever** — `refresh` skips it, re-apply preserves it,
  `uninstall` keeps it.
- **Settings are preserve-or-refuse.** The format hook is added additively under
  our `DUMMYINDEX_EQUIP` sentinel; your other hooks (including dummyindex's own
  `DUMMYINDEX_AUTO_REFRESH` SessionStart entry) are untouched. An unparseable
  `settings.json` is **left alone** — the hook is skipped and reported, files
  still land.
- **Status / dry-run FIRST.** Never run `refresh`, `patch`, or `uninstall`
  without first showing the user what it will touch (`equip status`, then the
  `--dry-run` of the verb). Show patch intent (the old→new diff) before applying.

## The lifecycle (verbs)

**Always start read-only**, then act:

1. **Preview & apply.**
   ```bash
   dummyindex context equip --dry-run     # prints the plan; writes nothing
   dummyindex context equip               # apply: files + settings hook + manifest
   ```
   Scope to a planned change with `--for-proposal <slug>` — equip reads that
   proposal's `plan.md`/`checklist.md` and adopts a covering specialist
   (database / security / frontend / performance / docs) *before* falling back
   to the generic implementer. Add `--json` to parse the result.

2. **Inspect what you own.**
   ```bash
   dummyindex context equip status [--json]
   ```
   Classifies every generated item: **pristine** (ours, safe to evolve),
   **user-modified** (yours now, skipped forever), **missing**. Run this before
   any mutating verb.

3. **Refresh — pull template improvements into PRISTINE items only.**
   ```bash
   dummyindex context equip refresh --dry-run   # show what would change
   dummyindex context equip refresh             # re-render PRISTINE-and-stale, minor-bump
   ```
   USER_MODIFIED items are never touched. Show the dry-run before applying.

4. **Reset — the escape hatch for one item.**
   ```bash
   dummyindex context equip reset <NAME>        # restore its pristine render, re-baseline
   ```
   Use when the user explicitly wants a hand-edited tool returned to the
   generated baseline. Confirm intent first — this overwrites their edit.

5. **Patch — sanctioned evolution (stays PRISTINE).**
   ```bash
   dummyindex context equip patch --item <NAME> --from-file patch.json
   ```
   `patch.json` is `{"old": "...", "new": "..."}`; `old` must match **exactly
   once**. Applying it re-baselines the origin-hash and patch-bumps the version,
   so the tool stays ours (unlike a hand edit). **Show the user the old→new
   intent before you apply it.**

6. **Uninstall — remove only what is ours.**
   ```bash
   dummyindex context equip uninstall --dry-run
   dummyindex context equip uninstall
   ```
   Deletes PRISTINE generated files + our `DUMMYINDEX_EQUIP` hook + the manifest.
   USER_MODIFIED files and user hooks are kept and reported.

## Discipline (spec-led)

- **Read `.context/HOW_TO_USE.md` first** — the generated tools are grounded in
  it and in `.context/conventions/`. If `.context/` is absent, tell the user to
  run `/dummyindex` first; equip has nothing to ground against without it.
- When `.context/` disagrees with the code, **the code wins** — flag the drift.
- Don't gold-plate. The catalog decides the set; a bigger toolkit is a separate
  ask, and adoption never invents a speculative template for an uncovered gap.

## Checklist (verify before claiming done)

- [ ] `dummyindex context equip --dry-run` (or `status`) was shown first.
- [ ] The implementer + tester + reviewer agents and the verify skill were
      written under `.claude/` additively (or a target was skipped because a
      user / USER_MODIFIED file sat there — reported).
- [ ] The format hook was wired under `DUMMYINDEX_EQUIP` (when a formatter was
      detected) without disturbing user hooks or the managed session-hook entries (`DUMMYINDEX_AUTO_REFRESH` sentinel).
- [ ] `.context/equipment.json` (schema v2) lists each tool with `capabilities`,
      `grounded_in`, and — for generated agents — `subagent_type` / `version` /
      `origin_hash`.
- [ ] Before any `refresh` / `patch` / `reset` / `uninstall`, the intent
      (dry-run output or the patch's old→new) was shown to the user.
