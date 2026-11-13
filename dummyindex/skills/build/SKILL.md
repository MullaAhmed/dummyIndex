---
name: dummyindex-build
description: "Drive a dummyindex proposal to completion through grounded checklist execution one dependency wave at a time. Reads the proposal spec and plan, asks the deterministic CLI for the earliest incomplete wave, dispatches independent items concurrently, verifies each result separately, and only then checks it off. Every host reads the same capability manifest and passes its selected mandates to native subagents, with generic delegation when native equipment is missing. Reconciles completed code into the curated `.context/` index rather than merely rebuilding it. Use for `/dummyindex-build`, `$dummyindex-build`, build the proposal, execute the plan, implement the checklist, or continue proposal work."
---

# /dummyindex-build / $dummyindex-build — grounded execution of a proposal

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, diagnose with `dummyindex context check --versions`, which reports the stale layer. Then run `/dummyindex-update` on Claude or `$dummyindex-update` on Codex to bring the CLI, skills, and this repo's wiring into sync. The update skill is non-destructive on a curated `.context/`. Do not use a blunt `dummyindex install` to "fix" a version skew.

You are the build conductor. The `dummyindex context build` CLI is deterministic checklist STATE. It tells you the next **wave** of items, the agent that fits each, and the files that ground those agents. A **wave** is a `## Wave N` group whose items are mutually independent. **You** do the work: dispatch the wave's agents **in parallel**, **verify** each result, then have the CLI tick each box. The CLI never runs an agent and never verifies — that discipline is yours.

Use the active host's native skill and delegation mechanism. The portable host path
and Claude share the preparation, verification and learning steps. Native
discovery references are optional. Do not infer availability from a manifest's
`subagent_type` alone.

**Waves.** The plan step groups `checklist.md` items under `## Wave N — <label>` headings. Items in one wave touch disjoint files and share no dependencies, so they dispatch concurrently. Waves run strictly in order — wave N+1 never starts until you tick every wave-N box. A flat checklist (no wave headings) is N single-item waves. The loop below degrades to the old serial behaviour with zero changes.

## Inputs

- A **proposal** at `.context/proposals/<slug>/` with `spec.md`, `plan.md`, `checklist.md` (a flat `- [ ]` list), `proposal.json`. The `<slug>` is what the user builds. If they do not name it, list `.context/proposals/` and ask.
- `.context/equipment.json`, when present, names the shared capabilities.
  A missing manifest or native adapter never blocks generic delegation.

The closing reconciliation procedure belongs to the installed main
`dummyindex` skill, not this sibling. Resolve it at
`<skills-root>/dummyindex/council/65-reconcile.md` — equivalently,
`../dummyindex/council/65-reconcile.md` relative to this installed `SKILL.md`.
That main skill ships the rest of the council companions the procedure may
reference.

## The loop (run it literally)

0. **Read shared routing state.** Run the first
   `--next-wave --json` and read `equipped` **and** `routing`.

   - **Print the effective-model disclosure before the first wave dispatches.**
     From the payload's `routing` map, print
     `models: implementer=<x> auditor=<y> decisions=<z>` (omit unset roles, and
     say nothing about models when `routing` is empty). This answers "what
     models would be used?" without being asked. Routing is proposal data: the
     optional `"routing"` block in `proposal.json`, written by
     `/dummyindex-plan --route k=v`. `dummyindex context build --route k=v`
     overrides it at run time. Precedence is invocation >
     proposal > unset.

   If `equipped` is false, continue with native subagents. You can prepare shared capabilities through `dummyindex context equip apply --for-proposal <slug>`. Claude may add `--platform claude` for native extras. Never stop solely because Claude equipment is missing.

1. **Read the spec first.** Open `.context/proposals/<slug>/spec.md` and `plan.md` end to end before you touch any checklist item. This is the contract. Everything downstream must conform to it. Do **not** flip any box before you read the spec.

2. **Ask the CLI for the next wave:**
   ```bash
   dummyindex context build --proposal <slug> --next-wave
   ```
   It prints **every unchecked item in the earliest incomplete wave** plus the
   shared **grounding paths** (spec, plan, and `.context/conventions/`). On
   every host, read `role_path` when supplied and include the full capability
   mandate in the delegated prompt. `subagent_type` is advisory until the host
   confirms that exact native agent is callable.

   A manifest path is not proof the file exists. If its body is missing or
   unreadable, report the gap. Use native generic dispatch with the task,
   grounding and selected policies. Prepare capabilities when the index is
   usable. Never invent a mandate or stop merely because a legacy file is absent.

   Add `--json` if you want to parse it. On a flat checklist the wave is one
   item.

   If it prints "all items checked", jump to step 6.

3. **Dispatch the whole wave in parallel through the active host.** Launch one
   subagent per dispatchable item concurrently. Read its `role_path` (or the
   selected manifest entry's `path`) and include the full capability mandate.
   Do this even for a preserved legacy `.claude/` file. This is data. It does
   not require a native Claude agent.

   Use an available exact-fit native agent or the host's implementation,
   exploration or general-purpose delegate (`worker`, `explorer`, `default` on
   Codex). On Claude, use `general-purpose` when no named adapter is callable.
   Include task scope, relevant grounding, verification expectations and the
   full instructions of policies actually selected in this session.

   Ponytail applies by default when exposed. When its Claude plugin hooks are
   active in this session, its `SubagentStart` hook already injects it into each
   subagent. Do not paste it again. Otherwise pass its loaded mandate unless
   the user turned it off this session. Never silently install it. Native tool
   syntax does not change the workflow.

   Pass the verification and working-tree preservation rules from step 4 to
   every delegate, including generic workers. When a time or spend limit is
   supplied, pass its remaining budget. Reserve time to verify and to return
   the final artifacts.

   Persist selected policy references in `proposal.json` as
   `"policies": [{"name": "ponytail", "path": "<loaded SKILL.md path>"}]`.
   The CLI's `handoff` binds each policy and capability to its current hash.
   Pass that compact task record plus the loaded mandates. Return the same
   `task_id`, an explicit state, artifact/evidence references, blocker and
   next action.

   Keep logs in artifacts and each handoff below 8,192 bytes. Dispatch batches
   contain at most eight items and 65,536 serialized bytes. Finish the offered
   batch, then request the next frontier.

   A **skill-only** plugin likewise is not an agent. On Claude, a
   `— via /<skill>` tag invokes that skill. On the portable host path (for
   example Codex), the equivalent is `— via $<skill>`. If a delegated subagent
   cannot invoke it, handle the tagged item in the main session. Only delegate
   items whose `dispatch` is **`subagent`**.

   **Honor `— via <tool>` tags — know the two tag classes first.** A checklist item may carry a trailing `— via <tool>` tag the plan step added, and the classes route differently:
   - **Agent tags dispatch as subagents.** An explicit `— via agent:<name>`, or a bare `— via <name>` that exactly matches an equipped kind-agent entry, makes the item a **`subagent`** unit. The tag pins the unit to that equipment entry when the entry carries a `subagent_type`, and it bypasses capability scoring. The CLI records why in each payload's `upgrade_note`. An unknown `agent:<name>` degrades safely: the CLI marks it `dispatch: main-session` with a warning `upgrade_note`. Handle it in-session or report the gap, and never launch the Task tool with an unequipped name.
   - **Genuine main-session tools take BINDING routing, not a hint.** For a real main-session tool (`— via <plugin>:<command>` slash-command, `— via /<skill>` / `$<skill>`, an MCP-bound tool), the tag is **BINDING**. The named tool *must* execute the item.
     - Route the item through that tool. For a **skill**, invoke it through the active host's native skill mechanism (`/<skill>` on Claude or `$<skill>` on Codex). For a **slash-command** that a subagent cannot run, run it from the main session around the dispatch.
     - **Substitution is a build failure** (binding tool tags only). If the tagged tool is unavailable, errors out, or cannot complete, leave the item **unticked**, **STOP**, and report. **Never** let an agent hand-write the output the tool was supposed to produce. A hand-implemented binding-tagged item is a **failed** item *even if its code works*. This rule does not apply to agent-tagged subagent units — those are ordinary dispatched work.

   The CLI's `agent`/`subagent_type` mapping is unchanged for plain items. The tag adds a routing instruction on top. It does not replace the matched agent.

4. **VERIFY each item before you tick — independently, one verdict per item.** This is the load-bearing step. Do not trust any agent's self-report. After the whole wave returns, confirm each item against the spec:
   - run the declared acceptance checks and affected tests / build / linter **once for the whole wave**. Broaden only for required checks or a concrete unresolved risk within the remaining budget. Then attribute failures to their causes.
   - read the files each agent claimed to change,
   - check that each change satisfies the *spec's* intent for its item, not merely that "something happened".
   - **For a binding tool-tagged item, confirm the tool actually ran and produced the result.** If the tool records run state or artifacts, read that evidence (its provenance). Then verify the output came from the tool. Output that bypassed the tagged tool **fails verification regardless of code quality**. Leave it unticked and report it as a substitution failure.

   Preserve the current deliverable during verification. Never stash, reset,
   clean or switch its working tree to investigate baseline failures. Use a
   separate temporary worktree or copy. If investigation cannot finish, retain
   the edits and report the failing command and uncertainty. Before you check
   an item, confirm its final files and diff still contain the validated change.
   An unfinished required check leaves verification incomplete and the item unticked.

   Tick the items that pass (step 5). If **any** item fails or is blocked, tick only the verified siblings, then **STOP**. Blockers include an ambiguous spec, a missing dependency, failing tests you cannot resolve, or a decision the user must make. Do **not** tick the failing item, and do **not** start the next wave: waves gate on full completion.

   Report what blocks the item, what you tried, and the smallest decision or input you need to proceed. A half-done item left unchecked is correct. A ticked box over unverified work is a lie the next session will trust.

5. **Tick each verified box — only now:**
   ```bash
   dummyindex context build --proposal <slug> --check "<task_id>" --receipt <verified-task-receipt.json>
   ```
   Use the stable `task_id` from the frontier. The receipt binds that ID and displayed text hash to the current source commit and the scoped artifact/outcome hashes. Keep `implemented`, `evaluated`, `applied` and `verified` distinct. Legacy substring/index checks remain available but do not supply verification evidence. See `docs/guide/closeout.md` in the source distribution for the small receipt schema.

6. **Check status and decide:**
   ```bash
   dummyindex context build --proposal <slug> --status
   ```
   - Not all done → go back to step 2 for the next wave.
   - All done → the CLI prints the closing command, **`dummyindex context reconcile`**.
     That is the closer the `--status` output names, so match it. Do **not**
     substitute a bare `rebuild --changed`, which would leave the new files
     unassigned. The build added new code, so **reconcile** it into `.context/`
     to close the loop. Commit the code you built. Then run the reconcile
     procedure in the main skill
     (`../dummyindex/council/65-reconcile.md`, resolved relative to this
     installed `SKILL.md`):
     ```bash
     dummyindex context reconcile          # what to fold in (drift + unassigned)
     ```
     **`reconcile` is read-only and non-destructive — it writes nothing and never
     re-clusters the curated taxonomy.** It only *reports* the delta. Do not skip
     it for fear of losing curated work. Then place each new file
     (`scaffold-feature` / `assign-files`), enrich it, and run
     `dummyindex context reconcile-stamp` to advance the anchor. The loop
     closes once `.context/` reflects — and is anchored to — the code you built.

     When you write `.context/` documents, follow the Writing standard in `../council/00-overview.md` (ASD-STE100). After you write, run `dummyindex context check --style`.

6b. **Scoped maintenance — auto-recouncil defaults ON.** Apply the closing
   phase to this task's recorded changed paths and their owning features.
   Read `dummyindex context reconcile`, then reconcile/enrich only that delta.

   Use the checkpointed maintain loop when its frontier belongs to this task.
   Do not drain another session's backlog or force a global stamp over unknown
   work. Pending unrelated drift stays advisory and does not keep an implemented
   proposal open. Preserve its count in the final report. An explicit
   `"build": {"auto_recouncil": false}` skips owned maintenance and must disclose
   what remains. It never turns unchecked implementation into completed work.

6c. **Close the disposable workspace.** Review accepted decisions/lessons and fixtures. Transfer them into existing durable homes with `dummyindex context build --proposal <slug> --closeout <manifest.json>`. Repair durable inbound references first.

   Keep live deployment/browser checks out of the implementation checklist. Move any existing named live-only item into the closeout manifest's independent `pending_verification`. Closeout records implementation completion without claiming live verification. Reconcile only this task's owned paths/features. Disclose unrelated drift separately rather than absorbing it into this build.

   After an accepted closeout, automatically handle at most one queued event with `dummyindex context evolve learning --next`. Supply one source-backed reflection through the evolve skill's ordinary exact-candidate gate, or record `NO_ENTRY`. Do not ask for another learning prompt, learn recursively from evolve/experiment output, or promote an unsupported rule.

7. **Report.** Summarise completed task IDs, exact implementation/verification state, the closeout receipt and pending live verification. Report the owned reconciliation work and unrelated advisory backlog separately.

8. **Learn (optional judgment step, on every host).** Fold a durable lesson
   into the selected generated capability through the same sanctioned patch
   seam. The manifest's `path` owns the body. Native discovery files are
   references. Trigger a learning patch in these cases:
   - **A complex task succeeded** via an approach the generated agent did not already encode. Examples are a sequencing rule, a project-specific gotcha, or a verification step that caught a real bug.
   - **An error → working-path discovery** — you hit a failure and found the fix. The fix is a general rule the agent should have known.
   - **A user correction** — the user redirected the approach, and that correction should persist.

   When one fires, draft the **minimal** old/new patch for the relevant generated tool. The tool is the implementer/tester/reviewer agent or the `<proj>-verify` skill. **Show the old→new intent to the user.** Never use a hand-edit: it makes the file USER_MODIFIED, and refresh will stop maintaining it. Then apply it through the sanctioned seam on every host:
   ```bash
   printf '%s' '{"old": "<exact unique snippet>", "new": "<snippet + the lesson>"}' > /tmp/equip-patch.json
   dummyindex context equip patch --item <NAME> --from-file /tmp/equip-patch.json
   ```
   `old` must match exactly once. The patch re-baselines the tool's origin-hash and patch-bumps its version, so it stays PRISTINE and `refresh`-able. Keep edits small and grounded — a learning patch teaches a rule, it does not rewrite the agent. If no trigger fired, skip this step. Speculative edits are worse than none.

## Discipline (non-negotiable)

- **Spec-led.** The spec is the source of truth. Read it before the loop and re-check against it at every verify step. The checklist is the order of work. The spec is the definition of done.
- **One wave at a time, waves in order.** Within a wave, dispatch everything in parallel. Across waves, never start wave N+1 while wave N has an unticked box. Do not reorder waves. Do not pull an item forward out of a later wave. The wave order encodes dependencies.
- **Verify before tick.** Every box, individually — a wave that "mostly worked" is N separate verdicts, not one. Evidence (a passing test, a read of the diff) before each `--check`.
- **Stop on block.** When you cannot verify an item or you hit a decision point, tick only the verified siblings, stop, and report. Never tick to "keep moving". Never start the next wave over an incomplete one.
- **Stay in scope.** Each dispatched agent implements one item, inside existing conventions, without touching its wave-siblings' files. New abstractions need their own proposal.
- **`— via` tags: two classes.** Genuine main-session tool tags are binding, and substitution is a failed item, never a fallback. Hand-writing the output the tool was supposed to produce is a build failure, even if the code works. Agent tags (`— via agent:<name>`, or a bare equipped-agent name) are the other class. They fan the item out as a pinned subagent unit. Unknown agent names degrade safely to `main-session` with a warning `upgrade_note`.
- **GATE / main-session items are not dispatchable.** The CLI marks items `dispatch: main-session`: a `**GATE**` human decision, or a tool only the main session can run. Handle these items in this session. Never hand them to a subagent.

## CLI reference (deterministic state only)

```
dummyindex context build --proposal <slug> --next-wave [--json] [--route K=V]...
    → ALL unchecked items in the earliest incomplete wave (## Wave N group),
      each with its `dispatch` (subagent | main-session), `gate`, `via`, its
      matched equipment (agent) + subagent_type (Claude dispatch metadata) +
      shared grounding paths, plus the payload-level `routing` map and a
      per-item `upgrade_note` (set when an agent tag was pinned/upgraded or
      failed safe), plus `role_path` for the selected capability body. Each
      host passes that mandate to its native delegate even without an adapter. A `main-session` item
      (GATE, a binding tool tag, or a failed-safe agent tag) carries an
      `instruction` instead of an agent — NEVER dispatch it. Flat checklist →
      exactly one item. THIS is the loop's driver.
dummyindex context build --proposal <slug> --next [--json] [--route K=V]...
    → the single first unchecked item, same mapping (serial fallback for
      debugging / one-at-a-time runs)
    → may also carry `missing_capability: [<cap>…]` — present ONLY when an item
      truly matched no equipped agent AND its text implies a specialist capability
      (security / database / performance / docs / search / frontend). It is a
      signal, not a command. On Claude, with user approval, you MAY pause for the
      gated discover→install flow and then re-run `--next`; installation is never
      silent. On Codex, do not run Claude equip discovery or installation: route
      the item to worker/explorer/default and report any external-tool gap.
dummyindex context build --proposal <slug> --check "<task_id>" [--receipt <task-receipt.json>]
    → atomically flip that item to - [x] (idempotent; one call per item)
dummyindex context build --proposal <slug> --status [--json]
    → done/total + the resolved model `routing` (`models:` line in text mode;
      `routing` key via --json; precedence invocation --route > proposal.json >
      unset); when complete, prints `dummyindex context reconcile`
      (close the loop via the main skill's reconcile procedure at
      ../dummyindex/council/65-reconcile.md, relative to this SKILL.md).
      `reconcile` is read-only/non-destructive — run it, don't substitute rebuild.
      --json additionally carries the resolved `auto_recouncil` build policy
      (config schema v5 `build.auto_recouncil`, default true).

--route K=V (repeatable; keys: implementer|auditor|decisions; values:
current|opus|sonnet|haiku|fable) overrides the proposal's "routing" block for
this invocation — print the `models:` disclosure from step 0 with it.

dummyindex context equip patch --item <NAME> --from-file <F>   # shared body
    → (Claude learning step) apply a sanctioned old→new patch to a generated tool;
      re-baselines + version-bumps so it stays PRISTINE. F is {"old","new"}.
```
