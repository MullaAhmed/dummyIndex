---
name: dummyindex-verify
description: Verifies a change in this python repo against the project's own conventions and test/lint commands, grounded in `.context/`. Use after implementing a change, before claiming it works.
metadata:
  version: 1.0.0
---
<!-- dummyindex:generated -->

# dummyindex-verify

You verify that a change to this **python** repository actually works and
conforms to the project's conventions — before anyone claims it is done.
Evidence before assertions: run the commands, read the output, then report.

## Ground yourself first

This repo carries a generated context spine. Consult it so you verify against
the project's *real* expectations, not generic ones:

1. `.context/HOW_TO_USE.md` — how to navigate the spine.
2. The project's conventions — the checks below must honor these:
- `.context/conventions/coding-practices.md`
- `.context/conventions/data-access.md`
- `.context/conventions/folder-organization.md`
- `.context/conventions/naming.md`
- `.context/conventions/testing.md`
3. The relevant `.context/features/<id>/` docs for the touched area, so
   you verify the behaviour the feature actually promises.

When `.context/` disagrees with the code, **the code wins** — flag the
drift in your report rather than failing the change for it.

## Verification checklist

Run the project's own commands (detected from its manifests). If a command
below reads as "(no command detected …)", discover the project's real one from
the conventions/manifests and run that — do not invent or skip.

1. **Tests.** Use `uv run pytest -q` to run declared acceptance and affected tests
   first. Broaden for required checks or concrete unresolved risks within the
   remaining budget. Report commands and summaries; missing coverage is a finding.
2. **Lint.** Run: `uv run ruff check .`. Do not invent a linter the project lacks.
3. **Types.** Run: `(no command detected — discover the project's own and run it)`.
4. **Scope.** Confirm the diff matches the planned change and touches nothing
   unrelated.
5. **Conventions.** Spot-check the change against the convention docs above
   (naming, immutability, error handling, file size).

Preserve the current deliverable: never stash, reset, clean or switch its
working tree for baseline investigation. Use a separate worktree or copy;
if unfinished, retain the edits and report uncertainty. Confirm the final
files and diff still contain the validated change.
An unfinished required check leaves verification incomplete; report it as such.

## Reporting

State exactly what you ran and what it printed. If anything failed or you could
not run a check, say so plainly — never claim "passing" without the command
output to back it.
