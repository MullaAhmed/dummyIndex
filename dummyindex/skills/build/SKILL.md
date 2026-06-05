---
name: dummyindex-build
description: Drive a dummyindex proposal to completion — grounded execution of its checklist.md. Reads the proposal's spec.md first, then loops the flat checklist top-to-bottom: for each unchecked item it asks the CLI which equipment agent fits (or general-purpose fallback), dispatches that agent via the Task tool grounded in .context/ + the proposal's spec/plan, VERIFIES the result, and only then ticks the box. Stops and reports when blocked. When every item is checked, closes the loop by re-indexing with `dummyindex context rebuild --changed`. Triggers — "build the proposal", "/dummyindex-build", "execute the plan", "work the checklist". Expects a proposal at `.context/proposals/<slug>/` (produced by the propose step) and an optional `.context/equipment.json`.
allowed-tools: Read, Write, Bash, Task
---

# /dummyindex-build — grounded execution of a proposal

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, re-run `dummyindex install --scope user`.

You are the build conductor. The `dummyindex context build` CLI is deterministic checklist STATE — it tells you the next item, the agent that fits it, and the files to ground that agent in. **You** do the actual work: dispatch the agent, **verify** the result, then tell the CLI to tick the box. The CLI never runs an agent and never verifies — that discipline is yours.

## Inputs

- A **proposal** at `.context/proposals/<slug>/` with `spec.md`, `plan.md`, `checklist.md` (a flat `- [ ]` list), `proposal.json`. The `<slug>` is what the user is building; if they didn't name it, list `.context/proposals/` and ask.
- Optionally `.context/equipment.json` (the equipment manifest). If absent, every item maps to the `general-purpose` agent — that's fine, the loop still runs.

## The loop (run it literally)

1. **Read the spec first.** Open `.context/proposals/<slug>/spec.md` and `plan.md` end to end before touching any checklist item. This is the contract; everything downstream must conform to it. Do **not** start flipping boxes before you've read the spec.

2. **Ask the CLI for the next item:**
   ```bash
   dummyindex context build --proposal <slug> --next
   ```
   It prints the first unchecked item, the **agent** that fits it (an equipment item by capability match, or `general-purpose` when nothing matches), and the **grounding paths** — the spec, the plan, and the repo's `.context/conventions/`. Add `--json` if you want to parse it.

   If it prints "all items checked", jump to step 6.

3. **Dispatch the mapped agent via the Task tool.** Launch the agent the CLI named (use `general-purpose` when it said fallback). In the agent's prompt, **ground it explicitly**: tell it to read the grounding paths first (`spec.md`, `plan.md`, `.context/conventions/`), then implement *exactly* the one checklist item — no more. Quote the item text verbatim. The agent works inside the existing conventions; it does not invent new structure.

4. **VERIFY before you tick.** This is the load-bearing step. Do not trust the agent's self-report. Independently confirm the item is actually done against the spec:
   - run the relevant tests / build / linter (e.g. `uv run pytest` for this repo),
   - read the files the agent claimed to change,
   - check the change satisfies the *spec's* intent for this item, not just "something happened".

   If verification **passes**, go to step 5. If it **fails** or you are blocked (ambiguous spec, missing dependency, failing tests you can't resolve, the item needs a decision the user must make) — **STOP**. Do **not** tick the box. Report what's blocking, what you tried, and the smallest decision/input you need to proceed. A half-done item left unchecked is correct; a ticked box over unverified work is a lie the next session will trust.

5. **Tick the box — only now:**
   ```bash
   dummyindex context build --proposal <slug> --check "<item text or index>"
   ```
   This atomically flips exactly that `- [ ]` → `- [x]` (idempotent — re-running is harmless). Pass either a unique substring of the item text or its index from `--next`.

6. **Check status and decide:**
   ```bash
   dummyindex context build --proposal <slug> --status
   ```
   - Not all done → go back to step 2 for the next item.
   - All done → the CLI prints the closing command. Run it to re-index:
     ```bash
     dummyindex context rebuild --changed
     ```
     This refreshes `.context/` so the work you just built is reflected in the index. The loop is closed.

7. **Report.** Summarise: items completed, what each agent built, anything you left unchecked and why, and confirm the re-index ran.

## Discipline (non-negotiable)

- **Spec-led.** The spec is the source of truth. Read it before the loop and re-check against it at every verify step. The checklist is the order of work; the spec is the definition of done.
- **One item at a time, top to bottom.** Don't batch, don't reorder, don't skip ahead. The checklist order encodes dependencies.
- **Verify before tick.** Every single box. No exceptions. Evidence (a passing test, a read of the diff) before the `--check`.
- **Stop on block.** When you can't verify or you hit a decision point, stop and report — never tick to "keep moving".
- **Stay in scope.** Each dispatched agent implements one item, inside existing conventions. New abstractions need their own proposal.

## CLI reference (deterministic state only)

```
dummyindex context build --proposal <slug> --next [--json]
    → next unchecked item + mapped agent (or general-purpose) + grounding paths
dummyindex context build --proposal <slug> --check "<item text or index>"
    → atomically flip that item to - [x] (idempotent)
dummyindex context build --proposal <slug> --status [--json]
    → done/total; when complete, prints `dummyindex context rebuild --changed`
```
