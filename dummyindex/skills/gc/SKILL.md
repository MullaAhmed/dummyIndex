---
name: dummyindex-gc
description: "Run context-hygiene garbage collection for stale, superseded, or dead generated proposals and audits, with carefully bounded routing for trivially dead or broader dead code. Combines deterministic candidate signals and commit-throttle state with parallel agents that inspect `.context/` and current work, classify each candidate as keep, stale, superseded, or dead, and distinguish disposable docs from code requiring tests or a proposal. Requires explicit user confirmation before every deletion; docs are deleted through guarded CLI operations, trivial private code only when implementer and tester keep the suite green, and broader code goes to planning. Use for `/dummyindex-gc`, `$dummyindex-gc`, garbage-collect context, sweep stale docs, clean up dead context, or a hygiene-sweep nudge."
---

# /dummyindex-gc / $dummyindex-gc — context-hygiene GC council sweep

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, diagnose with `dummyindex context check --versions` (it reports which layer is stale), then run `/dummyindex-update` on Claude or `$dummyindex-update` on Codex to bring the CLI, skills, and this repo's wiring back into sync — the update skill is non-destructive on a curated `.context/`. Don't reach for a blunt `dummyindex install` to "fix" a version skew.

You are the **GC conductor**. dummyindex generates per-task workspaces under `.context/` — `proposals/<slug>/` (plan artifacts) and `audits/<slug>/` (argue-and-audit panels) — but nothing ever *retires* them. They accumulate: orphan scaffolds never fleshed out, superseded plans a later proposal replaced, done audits whose findings were long since fixed, and a stale `_archive/` convention. To an AI agent navigating `.context/` as canonical context, a superseded `plan.md` reads as *current intent* — so it plans against a retired design, "resumes" a dead checklist, or treats fixed findings as open. The disposition is **delete, not archive**: distill nothing, delete decisively, shrink the footprint.

## The deterministic / LLM split (read this first)

This mirrors the repo's own idiom — **deterministic CLI + LLM skill** — exactly how `audit-panel` (plumbing) + `/dummyindex-audit` (council) is split:

- **`dummyindex context gc` is deterministic plumbing.** It enumerates candidate generated docs (skipping `_`-prefixed sentinels), gathers *objective signals* (status, checklist completion, report-written, orphan-empty, git-tracked, age), computes the commit-throttle state, and — when handed an explicit, confirmed target + `--yes` — executes one *bounded, guarded* deletion of a whole doc workspace. It supplies signals; it never decides what is dead, never picks a panel, never confirms. **It never touches source code.**
- **THIS skill is the judgment + the gate.** "Stale / superseded / dead" is an LLM determination about whether an old artifact still matches the code and the work in flight — *not* a blind age rule. You fan out a council, synthesize a delete-list, **confirm with the user**, and only then invoke the CLI's delete verb (or route code through the right path). Detection is reasoning; the destructive act is bounded Python gated behind explicit confirmation.

## The orchestration contract (run it in THIS order)

The seven steps below run **in order**. Do not reorder them, do not skip the confirm gate, and never invoke a delete before the user has confirmed it.

> **`gc status` → PageIndex walk → user-confirm → `gc delete` (docs) / implementer+tester (trivial code) / new proposal (broad code) → `gc stamp` → reconcile-if-code.**

### 1. `gc status` — the deterministic candidate report

```bash
dummyindex context gc status --json
```

Read the JSON: the **candidate list** (each `{kind, slug, rel_path, status, signals, tracked, age_days}`), plus the **commit-throttle state** (`anchor`, `commits_since`, `threshold`, `should_signal`, `anchor_orphaned`). The `signals` are objective tags only — e.g. `orphan-empty`, `status:done`, `checklist-partial`, `report-written`, `untracked`, `age-<n>d`, `ARCHIVED` — **not** verdicts. If `anchor_orphaned` is true, the recorded anchor is unknown to the repo after a history rewrite; note it and plan to re-baseline with `gc stamp --to HEAD` in step 6. This report drives the skill on both hosts; on Claude it also powers the SessionStart "N commits since last hygiene sweep" nudge. Codex installs no dummyindex GC hook.

### 2. Fan out the PARALLEL council walk (dispatchable subagents)

Dispatch **one host-native subagent per candidate (or per small cluster), all in a single message** so they run concurrently. On Claude use `Task`; on Codex use `explorer` for these read-only walks, falling back to `default`. Each subagent:

- Grounds in `.context/HOW_TO_USE.md` first, then reads **the candidate's own files** (`spec.md`/`plan.md`/`checklist.md` for a proposal, `report.md`/`findings/` for an audit).
- Walks the docs **PageIndex-style** to find what supersedes or still depends on this candidate:
  ```bash
  dummyindex context query "<the candidate's topic / feature area>" --top-k 8 --json
  ```
- **Reads the current session's work** — the conversation context and any code changed this session — because "superseded" is session-contextual: a plan the work in flight just replaced is superseded *now*.
- Returns a **per-candidate verdict** — one of `keep` / `stale` / `superseded` / `dead` — with **evidence** (a `path:range`, a superseding proposal slug, a fixed-findings citation). An unsupported verdict ("looks old") is noise — drop it; cite the code/docs.

These walks are read-only research — they are the right thing to dispatch.

### 3. Synthesize the delete-list — three categories

Consolidate the verdicts into a delete-list, **separating** three kinds of disposition (they take different paths in step 5):

- **Dead docs** — a candidate the council judged `stale` / `superseded` / `dead` (an orphan scaffold, a superseded `plan.md`, a done audit whose findings are fixed, an `_archive/*` child). These are deleted directly through the CLI after confirm.
- **Trivially-dead code** — a **0-caller leading-`_` PRIVATE symbol** that passes **EVERY** exclusion guard below. Evidence the 0-caller claim from `.context/features/symbol-graph.json` (`calls` edges). A symbol is **never** "trivially dead" — route it to a proposal instead — if it is any of:
  1. a CLI verb handler / `run(args)` reachable from `cli/__init__.py`'s dispatch table;
  2. a hook entry point in the `hooks.py` / `claude_settings.py` command set (e.g. `signal`, `decide_nudge`);
  3. named in any `__all__` / re-exported public surface;
  4. a serialization round-trip member (`to_dict` / `from_dict` / `__init__`);
  5. referenced anywhere under `tests/` (first confirm `symbol-graph.json` even includes `tests/` — if it does not, "0 callers" is **blind to all test usage**, which by itself bars relying on the graph alone);
  6. reachable by dynamic dispatch.
  Only a leading-`_` private symbol with 0 callers that passes ALL of (1)–(6) is eligible — and even then removal must be **proven**, not asserted from the graph.
- **Broader / riskier dead code** — anything that is not a guard-passing trivially-dead private symbol (a public symbol, a multi-caller-but-all-dead cluster, anything you are unsure of). This is **never auto-removed**: it is routed to a new proposal.

### 4. CONFIRM WITH THE USER — **non-dispatchable / human-decision**

> **This step is NOT dispatchable to a subagent.** The conductor (you, in this session) presents the delete-list to the user and STOPS for an explicit "yes". A subagent must never decide or confirm a deletion — confirmation is a human decision the conductor/user owns. This is the gate that the CLI's `--yes` flag enforces and that this skill enforces above it.

Present the full delete-list with its evidence, grouped by category, and STOP for explicit confirmation. Spell out, per item: what it is, why it is dead (the evidence), how it will be removed, and any irreversible risk — in particular, a `untracked` doc deletion is **permanent** (not in git, no recovery) and needs the user's explicit okay on *that specific risk* before you add `--allow-untracked`; an `in_progress` / `checklist-partial` proposal is delete-blocked unless the user explicitly okays `--force-partial`. Confirmation always gates deletion — no artifact, doc or code, is removed without the user's explicit go-ahead surfaced here.

### 5. Execute, per category (only the user-confirmed items)

- **Dead docs → bounded CLI delete.** For each confirmed doc, gated behind the step-4 confirmation:
  ```bash
  dummyindex context gc delete --kind proposal --slug <slug> --yes
  dummyindex context gc delete --kind audit    --slug <slug> --yes
  ```
  **Every `gc delete` you run carries `--yes` and is gated behind the confirm step** — running `gc delete` *without* `--yes` is only ever a dry-run (it prints the target and removes nothing). Add `--allow-untracked` **only** when the user explicitly okayed permanently deleting that specific untracked workspace, and `--force-partial` **only** when the user explicitly okayed deleting that specific `in_progress` / `checklist-partial` proposal. Never add either flag speculatively. Re-deleting an already-gone target is an idempotent no-op (exit 0).
- **Trivially-dead code → implementer+tester (PROVE it green).** Dispatch the implementer to remove the symbol, then the tester to **prove the full suite stays green after the deletion**. Remove it **only if** the suite is green; if anything goes red, the symbol was not dead — revert and route it to a proposal instead. The graph signal proposes; the green suite disposes. GC never edits source directly — this path does.
- **Broader dead code → a new proposal (never auto-removed).** Invoke
  `/dummyindex-plan "remove dead code: <short description>"` on Claude or
  `$dummyindex-plan "remove dead code: <short description>"` on Codex so it
  goes through the normal grounded proposal, review, and build cycle.

### 6. `gc stamp` — advance the GC anchor

```bash
dummyindex context gc stamp
```

This advances the committed GC anchor to HEAD (or pass `--to <sha>`), which **resets the commit-throttle counter**. On Claude, that keeps the SessionStart nudge quiet until `threshold` new commits land; on Codex, it resets the same state reported by explicit GC status/skill runs. If step 1 flagged `anchor_orphaned`, re-baseline explicitly with `dummyindex context gc stamp --to HEAD`. Off-git, `stamp` is a graceful no-op.

### 7. Reconcile `.context/` if code changed

If the trivially-dead-code path in step 5 changed source, close the loop by reconciling the change into `.context/` — per this repo's selected host guidance (`.claude/CLAUDE.md` or the active Codex project instruction file), **do not** stop at a deterministic rebuild:

```bash
dummyindex context reconcile          # read-only — reports the delta, writes nothing
```

`reconcile` is read-only and non-destructive — it only *reports* drift + unassigned files. Then follow the reconcile procedure (place / enrich each touched feature doc) and advance the anchor:

```bash
dummyindex context reconcile-stamp
```

If no code changed (docs-only sweep), there is nothing to reconcile — `gc delete` already updated the on-disk docs and step 6 stamped the GC anchor. Skip this step.

## Dogfooding this repo (GATE) — **non-dispatchable / human-decision**

> Running `/dummyindex-gc` against **this** repo to delete *its own* current orphan / superseded docs is a **user-confirmed GATE, never automatic**. Read the live candidates from a fresh `gc status` run (never a hard-coded slug list — the repo's contents shift), present them, and STOP for the user's explicit confirm exactly as in step 4. This GATE is **not dispatchable to a subagent** — deleting this repo's docs is the conductor's/user's decision, never a subagent's.

## Discipline (non-negotiable)

- **Confirmation always gates deletion.** No artifact — doc or code — is ever removed without explicit user confirmation surfaced by step 4. The CLI refuses to delete without an explicit target + `--yes`, and needs a *second* explicit flag (`--allow-untracked`) to remove a git-untracked workspace; this skill gates above that.
- **Step 4 (user-confirm) and the dogfood GATE are NOT dispatchable.** They are human decisions the conductor/user owns — never handed to a subagent. Only the read-only PageIndex walks (step 2) and the trivially-dead-code implementer+tester (step 5) are dispatched.
- **Never show a bare `gc delete`.** Every shown `gc delete` carries `--yes` and is gated behind the confirm step. A `gc delete` without `--yes` is a dry-run, never an auto-action.
- **Delete only the genuinely dead.** Stale / superseded / dead / no-longer-useful — **not** every `done` proposal. A `done`-but-still-relevant plan stays until it is actually superseded.
- **Evidence over assertion.** Every verdict cites a `path:range`, a superseding slug, or a fixed-findings reference. "Looks old" is not evidence — drop it.
- **GC never edits source code directly.** Trivially-dead code goes through implementer+tester (removed only if the full suite stays green); broader dead code goes to a proposal. The CLI never touches code.
- **The code wins.** Conventions and feature docs are context, not authority — when a doc and the code disagree, cite the code (and the doc is itself a GC candidate).

## CLI reference (deterministic state only)

```
dummyindex context gc status [--json] [--root DIR]
    → read-only sweep report: candidate list + signals + commit-throttle state
      (anchor, commits_since, threshold, should_signal, anchor_orphaned). Exit 0.
      THIS is the report the skill and Claude's SessionStart hook consume;
      Codex invokes it explicitly through the skill.
dummyindex context gc delete --kind proposal|audit (--slug S | --path P) --yes \
    [--allow-untracked] [--force-partial] [--root DIR]
    → delete ONE generated-doc workspace dir, atomically, after the user confirm.
      Without --yes: prints the dry-run target and deletes NOTHING (exit 0).
      Guards (in order): slug-charset → sentinel-reject (_archive / leading-_ /
      . / .. / empty) → realpath containment → liveness (refuse in_progress /
      checklist-partial without --force-partial) → recoverability (refuse
      untracked without --allow-untracked). Re-delete of a gone dir = no-op.
      NEVER deletes source code.
dummyindex context gc stamp [--to SHA] [--root DIR]
    → advance the committed GC anchor to HEAD (or --to SHA); resets the
      commit-throttle counter. Off-git = no-op.
dummyindex context gc signal [--json] [--root DIR]
    → Claude's SessionStart throttle probe: prints the one-line nudge iff over
      threshold and not already signalled this session. Always exit 0; silent
      under threshold / off-git / already-signalled. (The Claude hook runs
      this; on either host, you run `gc status` instead.)

dummyindex context query "<topic>" [--top-k N] [--json]
    → PageIndex-style retrieval the council walk uses to find what supersedes or
      still depends on a candidate. No LLM in the loop.
```
