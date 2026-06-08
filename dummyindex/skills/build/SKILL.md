---
name: dummyindex-build
description: Drive a dummyindex proposal to completion — grounded execution of its checklist.md. Reads the proposal's spec.md first, then loops the flat checklist top-to-bottom: for each unchecked item it asks the CLI which equipment agent fits, dispatches that agent via the Task tool grounded in .context/ + the proposal's spec/plan, VERIFIES the result, and only then ticks the box. If the repo has no `.context/equipment.json` at all (not equipped), it STOPS and warns the user to run `/dummyindex-equip` instead of silently dispatching general-purpose; on an equipped repo, an item that maps to no specialist uses general-purpose silently (that's normal). Stops and reports when blocked. When every item is checked, closes the loop by reconciling the new code into `.context/` (the reconcile procedure — `dummyindex context reconcile` → place/enrich → `reconcile-stamp`), not just a deterministic rebuild. Triggers — "build the proposal", "/dummyindex-build", "execute the plan", "work the checklist". Expects a proposal at `.context/proposals/<slug>/` (produced by the plan step, which auto-equips) and a `.context/equipment.json`.
allowed-tools: Read, Write, Bash, Task
---

# /dummyindex-build — grounded execution of a proposal

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, re-run `dummyindex install --scope user`.

You are the build conductor. The `dummyindex context build` CLI is deterministic checklist STATE — it tells you the next item, the agent that fits it, and the files to ground that agent in. **You** do the actual work: dispatch the agent, **verify** the result, then tell the CLI to tick the box. The CLI never runs an agent and never verifies — that discipline is yours.

## Inputs

- A **proposal** at `.context/proposals/<slug>/` with `spec.md`, `plan.md`, `checklist.md` (a flat `- [ ]` list), `proposal.json`. The `<slug>` is what the user is building; if they didn't name it, list `.context/proposals/` and ask.
- A **`.context/equipment.json`** (the equipment manifest). `/dummyindex-plan` auto-equips at plan time, so a planned proposal normally already has one. If it is missing, the repo is **not equipped** — see step 0; do **not** silently dispatch `general-purpose` for the whole build.

## The loop (run it literally)

0. **Check the repo is equipped — STOP if not.** Run the first `--next` with `--json` and read the **`equipped`** field (it is `true` iff `.context/equipment.json` exists and holds ≥1 item). The CLI also prints an `⚠ no .context/equipment.json` warning to stderr in the non-json case. If `equipped` is **false**, the repo isn't equipped: **STOP** and tell the user the toolkit is missing — every dispatch would fall back to `general-purpose`, which defeats the point. Recommend they run `/dummyindex-equip`, or offer to equip it for them with `dummyindex context equip apply --for-proposal <slug>`. Only proceed with `general-purpose` if the user **explicitly confirms** they want to build unequipped. Do **not** silently dispatch `general-purpose` for an unequipped repo. (When `equipped` is true, skip straight to step 1 — a *per-item* `general-purpose` fallback later is normal and needs no warning.)

1. **Read the spec first.** Open `.context/proposals/<slug>/spec.md` and `plan.md` end to end before touching any checklist item. This is the contract; everything downstream must conform to it. Do **not** start flipping boxes before you've read the spec.

2. **Ask the CLI for the next item:**
   ```bash
   dummyindex context build --proposal <slug> --next
   ```
   It prints the first unchecked item, the matched **equipment item** (`agent`), the **`subagent_type`** — the actual Task-tool agent to launch — and the **grounding paths** (the spec, the plan, and the repo's `.context/conventions/`). Add `--json` if you want to parse it.

   If it prints "all items checked", jump to step 6.

3. **Dispatch via `subagent_type` through the Task tool.** Launch the Task tool with `subagent_type` set to the value the CLI emitted (it is `general-purpose` when the matched item declared none, or when nothing matched — that is the correct fallback, dispatch it as-is). In the agent's prompt, **ground it explicitly**: tell it to read the grounding paths first (`spec.md`, `plan.md`, `.context/conventions/`), then implement *exactly* the one checklist item — no more. Quote the item text verbatim. The agent works inside the existing conventions; it does not invent new structure.

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
   - All done → the CLI prints the closing command. The build added new code, so
     closing the loop means **reconciling** it into `.context/`, not just a
     deterministic rebuild (which would leave the new files unassigned). Commit
     the code you built, then run the reconcile procedure (`council/65-reconcile.md`):
     ```bash
     dummyindex context reconcile          # what to fold in (drift + unassigned)
     ```
     then place each new file (`scaffold-feature` / `assign-files`), enrich it,
     and `dummyindex context reconcile-stamp` to advance the anchor. The loop is
     closed once `.context/` reflects — and is anchored to — the code you built.

7. **Report.** Summarise: items completed, what each agent built, anything you left unchecked and why, and confirm the reconcile ran (anchor advanced).

8. **Learn — evolve the generated tooling (optional, judgment step).** After the loop, consider whether anything you learned should be folded back into a generated agent or the verify skill so the *next* build starts smarter. Trigger a learning patch in exactly these three cases (and only when the lesson is durable, not task-specific):
   - **A complex task succeeded** via an approach the generated agent didn't already encode (a sequencing rule, a project-specific gotcha, a verification step that caught a real bug).
   - **An error → working-path discovery** — you hit a failure, found the fix, and the fix is a general rule the agent should have known.
   - **A user correction** — the user redirected the approach, and that correction should persist.

   When one fires, draft the **minimal** old/new patch for the relevant generated tool (the implementer/tester/reviewer agent, or the `<proj>-verify` skill), **show the old→new intent to the user**, then apply it through the sanctioned seam (never a hand-edit — a hand-edit makes the file USER_MODIFIED and refresh will stop maintaining it):
   ```bash
   printf '%s' '{"old": "<exact unique snippet>", "new": "<snippet + the lesson>"}' > /tmp/equip-patch.json
   dummyindex context equip patch --item <NAME> --from-file /tmp/equip-patch.json
   ```
   `old` must match exactly once. The patch re-baselines the tool's origin-hash and patch-bumps its version, so it stays PRISTINE and `refresh`-able. Keep edits small and grounded — a learning patch teaches a rule, it does not rewrite the agent. If no trigger fired, skip this step; speculative edits are worse than none.

## Discipline (non-negotiable)

- **Spec-led.** The spec is the source of truth. Read it before the loop and re-check against it at every verify step. The checklist is the order of work; the spec is the definition of done.
- **One item at a time, top to bottom.** Don't batch, don't reorder, don't skip ahead. The checklist order encodes dependencies.
- **Verify before tick.** Every single box. No exceptions. Evidence (a passing test, a read of the diff) before the `--check`.
- **Stop on block.** When you can't verify or you hit a decision point, stop and report — never tick to "keep moving".
- **Stay in scope.** Each dispatched agent implements one item, inside existing conventions. New abstractions need their own proposal.

## CLI reference (deterministic state only)

```
dummyindex context build --proposal <slug> --next [--json]
    → next unchecked item + matched equipment (agent) + subagent_type
      (the Task-tool dispatch target; general-purpose fallback) + grounding paths
dummyindex context build --proposal <slug> --check "<item text or index>"
    → atomically flip that item to - [x] (idempotent)
dummyindex context build --proposal <slug> --status [--json]
    → done/total; when complete, prints `dummyindex context reconcile`
      (close the loop via the reconcile procedure, council/65-reconcile.md)

dummyindex context equip patch --item <NAME> --from-file <F>
    → (learning step) apply a sanctioned old→new patch to a generated tool;
      re-baselines + version-bumps so it stays PRISTINE. F is {"old","new"}.
```
