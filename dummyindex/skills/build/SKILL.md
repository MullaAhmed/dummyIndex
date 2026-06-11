---
name: dummyindex-build
description: Drive a dummyindex proposal to completion — grounded execution of its checklist.md, one WAVE at a time. Reads the proposal's spec.md first, then loops the checklist wave-by-wave: it asks the CLI for the next wave (every unchecked item in the earliest incomplete `## Wave N` group — mutually independent by construction), dispatches ALL of them concurrently via parallel Task calls in one message (each agent grounded in .context/ + the proposal's spec/plan), VERIFIES each result independently, and only then ticks each box. A flat checklist (no wave headings) degrades to one item per wave — the old strictly-serial behaviour. If the repo has no `.context/equipment.json` at all (not equipped), it STOPS and warns the user to run `/dummyindex-equip` instead of silently dispatching general-purpose; on an equipped repo, an item that maps to no specialist uses general-purpose silently (that's normal). Stops and reports when blocked. When every item is checked, closes the loop by reconciling the new code into `.context/` (the reconcile procedure — `dummyindex context reconcile` → place/enrich → `reconcile-stamp`), not just a deterministic rebuild. Triggers — "build the proposal", "/dummyindex-build", "execute the plan", "work the checklist". Expects a proposal at `.context/proposals/<slug>/` (produced by the plan step, which auto-equips) and a `.context/equipment.json`.
allowed-tools: Read, Write, Bash, Task
---

# /dummyindex-build — grounded execution of a proposal

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, re-run `dummyindex install --scope user`.

You are the build conductor. The `dummyindex context build` CLI is deterministic checklist STATE — it tells you the next **wave** of items (a `## Wave N` group whose items are mutually independent), the agent that fits each one, and the files to ground those agents in. **You** do the actual work: dispatch the wave's agents **in parallel**, **verify** each result, then tell the CLI to tick each box. The CLI never runs an agent and never verifies — that discipline is yours.

**Waves.** The plan step groups `checklist.md` items under `## Wave N — <label>` headings; items in one wave touch disjoint files and share no dependencies, so they dispatch concurrently. Waves themselves run strictly in order — wave N+1 never starts until every wave-N box is ticked. A flat checklist (no wave headings) is just N single-item waves: the loop below degrades to the old serial behaviour with zero changes.

## Inputs

- A **proposal** at `.context/proposals/<slug>/` with `spec.md`, `plan.md`, `checklist.md` (a flat `- [ ]` list), `proposal.json`. The `<slug>` is what the user is building; if they didn't name it, list `.context/proposals/` and ask.
- A **`.context/equipment.json`** (the equipment manifest). `/dummyindex-plan` auto-equips at plan time, so a planned proposal normally already has one. If it is missing, the repo is **not equipped** — see step 0; do **not** silently dispatch `general-purpose` for the whole build.

## The loop (run it literally)

0. **Check the repo is equipped — STOP if not.** Run the first `--next-wave` with `--json` and read the **`equipped`** field (it is `true` iff `.context/equipment.json` exists and holds ≥1 item). The CLI also prints an `⚠ no .context/equipment.json` warning to stderr in the non-json case. If `equipped` is **false**, the repo isn't equipped: **STOP** and tell the user the toolkit is missing — every dispatch would fall back to `general-purpose`, which defeats the point. Recommend they run `/dummyindex-equip`, or offer to equip it for them with `dummyindex context equip apply --for-proposal <slug>`. Only proceed with `general-purpose` if the user **explicitly confirms** they want to build unequipped. Do **not** silently dispatch `general-purpose` for an unequipped repo. (When `equipped` is true, skip straight to step 1 — a *per-item* `general-purpose` fallback later is normal and needs no warning.)

1. **Read the spec first.** Open `.context/proposals/<slug>/spec.md` and `plan.md` end to end before touching any checklist item. This is the contract; everything downstream must conform to it. Do **not** start flipping boxes before you've read the spec.

2. **Ask the CLI for the next wave:**
   ```bash
   dummyindex context build --proposal <slug> --next-wave
   ```
   It prints **every unchecked item in the earliest incomplete wave** — for each: the matched **equipment item** (`agent`) and the **`subagent_type`** (the actual Task-tool agent to launch) — plus the shared **grounding paths** (the spec, the plan, and the repo's `.context/conventions/`). Add `--json` if you want to parse it. On a flat checklist the wave is exactly one item.

   If it prints "all items checked", jump to step 6.

3. **Dispatch the whole wave in parallel through the Task tool.** Launch **one Task call per wave item, all in a single message**, so they run concurrently. For each call set `subagent_type` to the value the CLI emitted for that item (it is `general-purpose` when the matched item declared none, or when nothing matched — that is the correct fallback, dispatch it as-is). In each agent's prompt, **ground it explicitly**: tell it to read the grounding paths first (`spec.md`, `plan.md`, `.context/conventions/`), then implement *exactly* its one checklist item — no more. Quote the item text verbatim, and tell it which sibling items are being built concurrently so it does **not** touch their files. The wave's items are mutually independent by construction (the plan grouped them that way) — if, mid-dispatch, you realize two items actually collide on a file, fall back to dispatching those two serially and say so in the report.

   **Honor `— via <tool>` tags.** A checklist item may carry a trailing `— via <tool>` tag the plan step added (`— via <plugin>:<command>` for a plugin slash-command, `— via /<skill>` for a skill). When it does, that tag is a **directive, not a hint**: route the item through that tool. For a **skill**, tell the dispatched subagent to invoke it via the Skill tool as the way it does the work. For a **slash-command** a subagent can't run itself, run it from the main session around the dispatch (e.g. dispatch the build, then run the command on the result). The CLI's `agent`/`subagent_type` mapping is unchanged — the tag layers an execution instruction on top of it, it does not replace the matched agent.

4. **VERIFY each item before you tick — independently, one verdict per item.** This is the load-bearing step. Do not trust any agent's self-report. After the whole wave returns, confirm each item against the spec:
   - run the relevant tests / build / linter **once for the whole wave** (e.g. `uv run pytest` for this repo) — then attribute any failure to the item(s) that caused it,
   - read the files each agent claimed to change,
   - check each change satisfies the *spec's* intent for its item, not just "something happened".

   Tick the items that pass (step 5). If **any** item fails or is blocked (ambiguous spec, missing dependency, failing tests you can't resolve, a decision the user must make) — tick only the verified siblings, then **STOP**. Do **not** tick the failing item, and do **not** start the next wave: waves gate on full completion. Report what's blocking, what you tried, and the smallest decision/input you need to proceed. A half-done item left unchecked is correct; a ticked box over unverified work is a lie the next session will trust.

5. **Tick each verified box — only now:**
   ```bash
   dummyindex context build --proposal <slug> --check "<item text or index>"
   ```
   One call per verified item — this atomically flips exactly that `- [ ]` → `- [x]` (idempotent — re-running is harmless). Pass either a unique substring of the item text or its index from `--next-wave`.

6. **Check status and decide:**
   ```bash
   dummyindex context build --proposal <slug> --status
   ```
   - Not all done → go back to step 2 for the next wave.
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
- **One wave at a time, waves in order.** Within a wave, dispatch everything in parallel; across waves, never start wave N+1 while wave N has an unticked box. Don't reorder waves, don't pull an item forward out of a later wave — the wave order encodes dependencies.
- **Verify before tick.** Every single box, individually — a wave that "mostly worked" is N separate verdicts, not one. Evidence (a passing test, a read of the diff) before each `--check`.
- **Stop on block.** When you can't verify an item or you hit a decision point, tick only the verified siblings, stop, and report — never tick to "keep moving", never start the next wave over an incomplete one.
- **Stay in scope.** Each dispatched agent implements one item, inside existing conventions, without touching its wave-siblings' files. New abstractions need their own proposal.

## CLI reference (deterministic state only)

```
dummyindex context build --proposal <slug> --next-wave [--json]
    → ALL unchecked items in the earliest incomplete wave (## Wave N group),
      each with its matched equipment (agent) + subagent_type (the Task-tool
      dispatch target; general-purpose fallback) + shared grounding paths.
      Flat checklist → exactly one item. THIS is the loop's driver.
dummyindex context build --proposal <slug> --next [--json]
    → the single first unchecked item, same mapping (serial fallback for
      debugging / one-at-a-time runs)
dummyindex context build --proposal <slug> --check "<item text or index>"
    → atomically flip that item to - [x] (idempotent; one call per item)
dummyindex context build --proposal <slug> --status [--json]
    → done/total; when complete, prints `dummyindex context reconcile`
      (close the loop via the reconcile procedure, council/65-reconcile.md)

dummyindex context equip patch --item <NAME> --from-file <F>
    → (learning step) apply a sanctioned old→new patch to a generated tool;
      re-baselines + version-bumps so it stays PRISTINE. F is {"old","new"}.
```
