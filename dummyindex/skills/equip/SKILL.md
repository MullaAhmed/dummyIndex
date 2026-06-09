---
name: dummyindex-equip
description: Render and EVOLVE a project-tuned Claude Code toolkit from this repo's `.context/` spine — stack implementer + tester + reviewer agents and a verify skill, grounded in the project's own conventions, plus generated capability SPECIALISTS (db / security / performance / docs / search), a PostToolUse formatter hook wired into settings.json, and registry/project specialists adopted to cover gaps a template doesn't. Hash-baselined lifecycle (status / refresh / reset / uninstall) and a sanctioned patch seam mean generated tools improve over time without ever clobbering a user edit. Triggers — `/dummyindex-equip`, "equip the project", "equip this repo", "build tooling for this repo", "add a database/security specialist".
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
- on demand, a **generated capability specialist** — `<proj>-db-specialist`,
  `<proj>-security-specialist`, `<proj>-performance-specialist`,
  `<proj>-docs-specialist`, `<proj>-search-specialist` — a real, editable,
  hash-tracked file grounded in the matching `.context/` docs,
- plus any **adopted specialists** (project agents under `.claude/agents/`, or
  known-registry agents like *Frontend Developer*) that cover a capability **no
  template backs** — recorded in the manifest only, never written as files.

All of this is **codified policy**, not free-form generation: deterministic Python
decides what to detect, generate, adopt, and wire. You drive the CLI and present
the result; you do not hand-author agents here.

## Generated vs adopted (the distinction that matters)

Two ways equip can cover a capability — know which you're getting:

- **GENERATED specialist** — a `.claude/agents/<proj>-<cap>-specialist.md` file
  equip writes, carrying the `<!-- dummyindex:generated -->` marker and a
  `version` + `origin_hash` + `grounded_in` record in the manifest. It is
  **editable, refreshable, and fully lifecycle-managed** — exactly like the four
  core tools. Produced for capabilities a template backs: **db / security /
  performance / docs / search**.
- **ADOPTED specialist** — a manifest-only pointer (`"path": ""`,
  `"source": "installed"`, no `origin_hash`) at a project agent you already have
  or a built-in registry agent (e.g. *Frontend Developer*). **No file is
  written**; equip just records the dispatch target. Produced for a capability
  **no template backs** (frontend, or anything outside the template family).

A capability you already cover with a project agent is **adopted, not
regenerated** (it's not a gap). An explicit `add-specialist` request always
**generates** — that's how you turn a manifest pointer into a real, editable
file.

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
   proposal's `plan.md`/`checklist.md` and covers each demanded capability: it
   **generates** a specialist file when a template backs the capability
   (db / security / performance / docs / search — including RLS / tenant-isolation
   signals that map to security), or **adopts** one (manifest-only) when no
   template exists (e.g. frontend → *Frontend Developer*). Add `--json` to parse
   the result.

2. **Add a specialist on demand.**
   ```bash
   dummyindex context equip add-specialist <capability>   # db|security|performance|docs|search
   dummyindex context equip --specialist <capability>     # same, as a flag on apply
   ```
   Writes a grounded, editable `<proj>-<capability>-specialist` agent and tracks
   it like the core four. Idempotent and additive — a plain `equip` re-run
   afterward **preserves** it (never silently drops a specialist you added). An
   unknown capability (no template, e.g. `frontend`) is rejected with the list of
   valid ones — that capability is covered by adoption on a `--for-proposal` run
   instead.

3. **Inspect what you own.**
   ```bash
   dummyindex context equip status [--json]
   ```
   Classifies every generated item — core four **and** any generated specialist:
   **pristine** (ours, safe to evolve), **user-modified** (yours now, skipped
   forever), **missing**. Run this before any mutating verb.

4. **Refresh — pull template improvements into PRISTINE items only.**
   ```bash
   dummyindex context equip refresh --dry-run   # show what would change
   dummyindex context equip refresh             # re-render PRISTINE-and-stale, minor-bump
   ```
   USER_MODIFIED items are never touched. Show the dry-run before applying.

5. **Reset — the escape hatch for one item.**
   ```bash
   dummyindex context equip reset <NAME>        # restore its pristine render, re-baseline
   ```
   Use when the user explicitly wants a hand-edited tool returned to the
   generated baseline. Confirm intent first — this overwrites their edit.

6. **Patch — sanctioned evolution (stays PRISTINE).**
   ```bash
   dummyindex context equip patch --item <NAME> --from-file patch.json
   ```
   `patch.json` is `{"old": "...", "new": "..."}`; `old` must match **exactly
   once**. Applying it re-baselines the origin-hash and patch-bumps the version,
   so the tool stays ours (unlike a hand edit). **Show the user the old→new
   intent before you apply it.**

7. **Uninstall — remove only what is ours.**
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
  ask. A generated specialist backed by a real, grounded `.context/` capability
  template is **not** speculative — it is the right answer for db / security /
  performance / docs / search. What stays forbidden is **un-grounded, no-evidence
  generation**: equip never invents a template for a capability with no template
  and no `.context/` grounding — that gap falls to a manifest-only adoption or the
  generic implementer.

## Checklist (verify before claiming done)

- [ ] `dummyindex context equip --dry-run` (or `status`) was shown first.
- [ ] The implementer + tester + reviewer agents and the verify skill were
      written under `.claude/` additively (or a target was skipped because a
      user / USER_MODIFIED file sat there — reported).
- [ ] The format hook was wired under `DUMMYINDEX_EQUIP` (when a formatter was
      detected) without disturbing user hooks or the managed session-hook entries (`DUMMYINDEX_AUTO_REFRESH` sentinel).
- [ ] Any requested specialist was **generated** (a file with the marker +
      `version`/`origin_hash`/`grounded_in`) when a template backs it, or
      **adopted** (manifest-only, `"path": ""`) when none does — and you told the
      user which.
- [ ] `.context/equipment.json` (schema v2) lists each tool with `capabilities`,
      `grounded_in`, and — for generated agents (core four **and** specialists) —
      `subagent_type` / `version` / `origin_hash`.
- [ ] Before any `refresh` / `patch` / `reset` / `uninstall`, the intent
      (dry-run output or the patch's old→new) was shown to the user.
