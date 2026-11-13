---
name: dummyindex-fleet
description: "Babysit a checkpointed fleet run: sweep a host-side tracker into intake JSON, group tickets into file-disjoint proposal-sized units, and drive them in parallel through the deterministic `context fleet` CLI — worktree-isolated orchestrators, spend metering under a budget circuit-breaker, gate-and-skip anti-stall rules, dormant-agent probes, and resume-from-state recovery. All run state lives in committed CLI artifacts (RUN-MANIFEST.md + state.json), never transcripts. The merge/landing phase is opt-in. Use for /dummyindex-fleet, $dummyindex-fleet, run the fleet, overnight run, multi-proposal sweep, or resume a fleet run."
---

# /dummyindex-fleet / $dummyindex-fleet — fleet-run babysitter

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm that the CLI matches. If they differ, diagnose with `dummyindex context check --versions`, which reports which layer is stale. Then run `/dummyindex-update` on Claude or `$dummyindex-update` on Codex. This brings the CLI, the skills, and the wiring of this repo back into sync.

You are the fleet conductor. You never touch run state by hand: **every** read
or write goes through the `dummyindex context fleet` verbs (`init | next |
checkpoint | spend | merge-order | status`). The CLI owns the order, the file-disjointness, the gates, and the budget breaker. It acts on the committed artifacts
under `.context/fleet/run-<id>/` (`RUN-MANIFEST.md` written first,
`state.json` last).

Your judgment lives in four places. These are what becomes a unit, who runs it, whether an agent is alive, and when to merge. No LLM runs inside the CLI.

Resolve the active host first. On Claude Code, this workflow uses native Task delegation vocabulary. On any other host, take the **portable host path**. Invoke this skill through your own skill mechanism. Delegate each orchestrator to the named or generic subagents of your host. Inline the ground-rules block (section 5) into the delegated prompt instead of a search for a named Claude subagent type.

## 1. Intake (host-side) — produce `intake.json`

Tracker access (MCP connectors, REST, whatever the host has) stays **outside**
the CLI. Produce a file:

```json
{"units": [
  {"ticket": "<id>", "title": "<one line>", "paths": ["src/a.py", "src/a_test.py"]}
]}
```

- `paths` = repo-relative files the unit may ever touch. This freezes the file-disjointness for the whole run. Be deliberate.
- You may add extra keys (`repo_hint`, `size`, ...). The CLI ignores them.

## 2. Grouping rules

- **Small + disjoint** tickets may share one unit. Keep every unit proposal-sized. A spec + plan + checklist can describe it. Scaffold with `context propose` when you use `--plans` mode.
- **Big or risky** tickets run solo.
- **Subset-dedupe:** if the path set of ticket A is inside the path set of ticket B, do not create both. Fold A into B, or accept that they serialize. An intersection never co-dispatches.
- The CLI refuses duplicate slugs and zero-unit batches at `init`. Fix intake instead of an argument with the CLI.

## 3. Init

```bash
dummyindex context fleet init --intake intake.json \
  --budget-usd <cap> --max-parallel <n> \
  [--branch-template "{run}/{id}-{slug}"] [--ruling key=value]...
```

Pass the branch template that the host repo wants. The default `{run}/{id}-{slug}` is deliberately neutral. Then **commit the run dir** (`.context/fleet/run-<id>/`). These artifacts are the memory of the run. Read the printed warnings. A unit without known paths schedules conservatively and serially.

## 4. Dispatch loop

```bash
dummyindex context fleet next [--run DIR] --json
```

For each returned unit, create an isolated worktree on the branch of the unit. Spawn an orchestrator there. Hand it its ground-rules block (section 5) and its proposal path. Record the wave with
`fleet checkpoint --unit <id> --status building --wave N`.

The envelope is always valid and exits 0:

- `skipped: gated` — a parked question exists. Do **not** stall the fleet. Surface the question out-of-band. Then answer it with `fleet checkpoint --unit <id> --status planning --note "<the answer>"`.
- An **empty-but-valid** envelope with nothing left = every lane done/blocked. Proceed to section 7. A fleet never waits on a question.
- `BUDGET-HALT` (`"halt": true`) — stop the dispatch. Correct the meter only via the printed resume path (`fleet spend --est-usd -X --adjust` against the unit that ran over), then re-run `next`. Never resume silently.

## 5. Orchestrator ground rules (paste verbatim into every dispatch)

```text
You are ONE fleet unit's orchestrator, isolated in your own worktree.
1. Invoke the /dummyindex-build (or $dummyindex-build) procedure on the
   proposal you were assigned; drive its checklist wave-by-wave.
2. Commit policy — conventional types only (feat/fix/test/docs/refactor/chore).
3. Stage ONLY files in your assigned paths[] — a file another unit owns is
   never yours to stage, even if your edit touched it incidentally.
4. Verify in the FOREGROUND before reporting: run the repo's own test/lint
   commands and paste real output. Never report unverified success.
5. Your FINAL message is the report the conductor will checkpoint. End it
   with exactly one magic word:
   DONE    - complete, verified in the foreground, ready to merge
   BLOCKED - cannot proceed; say why and what you tried
   GATED   - parked on an open question; state the question precisely
6. Estimate tokens/dollars honestly when asked for a spend figure.
```

## 6. Metering, liveness, resume

- After each report of an orchestrator, record its status/wave/note with `fleet checkpoint`. Then run `fleet spend --unit <id> --est-usd <estimate>` so the breaker tracks reality. A unit that crosses the cap trips `BUDGET-HALT` for everyone. That is the point.
- **Dormant-agent probe:** if an orchestrator has not reported within the probe interval, probe it once. If there is no response, checkpoint it `blocked` with a note. Let the fleet advance. A stalled lane must never stall the run.
- **Resume-from-state only.** A fresh session reads `RUN-MANIFEST.md` and runs `fleet status` and `fleet next` to resume. Never resume from transcripts or chat history. They are not the run. If `state.json` is absent or corrupt, the CLI fails loud and prints repair or re-init instructions. Follow them exactly instead of a manual edit around them.

## 7. Merge phase (opt-in)

Never merge without the explicit go-ahead of the user for the phase. When the user gives it:

```bash
dummyindex context fleet merge-order [--run DIR]
```

Land branches top-down in the printed order. Each row already cites the earlier unit it must land after (shared member paths) or marks itself parallel-safe. As each unit lands, checkpoint it `merging`, then `done`. Commit the updated run dir with the landing commits.

## Non-negotiables

- All state goes through the CLI verbs. Never hand-edit `state.json`.
- The CLI is deterministic and the judgment lives in this skill. No LLM calls occur inside the tool.
- Prefer committed artifacts over memory. Commit the init dir and the landing commits. Resume from files only.

