# 09 — Lifecycle

How a repo moves from "no `.context/`" to "always-current, always-on" and stays there.

## Two modes (v0.15)

dummyindex runs in two modes per repo:

**1. Setup mode — one-time bootstrap.** `/dummyindex` on Claude Code or `$dummyindex` on Codex runs it (first run). The pipeline runs preflight inventory → ingest (AST index + `.context/` backbone) → onboarding (config) → council enrichment (spec/plan/concerns per feature) + conventions. It then runs source-docs catalog → host guidance → session-memory store seeded.

Claude gets `.claude/CLAUDE.md` plus managed hooks. Codex gets its active project instruction file (`AGENTS.override.md`, `AGENTS.md`, or a configured fallback) and no dummyindex-installed hook. Setup does **not** equip. Claude equipment may be generated later at plan time or through `/dummyindex-equip`. Codex never needs that equipment.

Physically reorganising the repo's real docs runs as a normal pipeline phase. This phase is destructive and still gated: clean tree, backup-first, per-file confirm. `--reorg-docs` runs that phase alone.

**2. Ongoing mode — every session after.** The spine plans, builds, and evolves:

- **Stay current (commit-anchored):** `.context/` records the commit it was last reconciled against (`meta.indexed_commit`). On Claude, SessionStart injects a drift report + memory. On Codex, the active project instruction file and explicit skill use carry the lifecycle. When source has moved on, the running session runs the **reconcile procedure** in the installed dummyindex skill. The procedure places new files and re-enriches drifted features. Then `reconcile-stamp` advances the anchor.

  On Claude, the **Stop reconcile-gate** is the exit-side enforcement. If `.context/` is still stale after a substantial session, it blocks the session's exit *once* with a scoped reconcile directive. Codex installs no equivalent dummyindex hook and relies on its explicit workflow. The gate stamps nothing, so the anchor still only moves when the session runs the procedure.

  `rebuild --changed` is the *quick deterministic refresh* of the backbone (maps/symbols/graph). It is now non-destructive. It preserves the curated taxonomy + enrichment and surfaces the same drift. It is **not** the genuine update (it would leave new files unassigned). The anchor moves only on `ingest` or `reconcile-stamp`. It never moves from a hook.
- **Keep planning docs in their homes:** on Claude, the **managed-doc-homes** guard (`guard-doc-write`, PreToolUse) denies creating a stray plan/spec/design/audit under `docs/`. It names the `.context/proposals|audits/` home it belongs in. `context migrate-docs` relocates docs that already leaked (git history preserved, dry-run by default, `--yes` to perform).
- **Plan new work:** the plan skill creates consistency-checked proposals
  (spec / plan / checklist) grounded in the index. Both hosts prepare the shared
  capabilities with `equip apply --for-proposal <slug>`. Claude may add native
  discovery references with `--platform claude`.
- **Build:** the build skill drives the checklist through host subagents wave-by-wave. Items in a `## Wave N` group dispatch in parallel. Waves run in order (verify-before-tick per item). Then the skill **reconciles** the new code into `.context/` (place + enrich + stamp). This is not a bare rebuild, which would leave the built files unassigned.

  A missing manifest does not block either host's native delegation. Delegates read the selected canonical mandate and applicable policy instructions.
- **Evolve shared capabilities:** `equip status|refresh|patch` uses origin hashes to preserve owner edits. Both hosts can apply durable learning through this same lifecycle. Ordinary project checks verify outcomes. Equipment-eval suites and scorecards are no longer generated or required.
- **Deprecate:** `features-merge` / `flow-remove` consolidate the index. `equip uninstall|reset` retire or restore tooling. Drift naturally retires prose for deleted code. Stale *generated* docs (abandoned `proposals/`, done `audits/`) are swept by **context-hygiene GC**. `/dummyindex-gc` on Claude or `$dummyindex-gc` on Codex runs a commit-throttled council sweep. The sweep **deletes** (never archives) dead docs, and the user confirms every deletion.

  On Claude, a SessionStart nudge fires once a commit threshold (default 10) since the last GC anchor is crossed. Codex runs the GC skill or status explicitly. `context gc status` is the read-only sweep. `context gc delete` is the bounded, guarded removal (dry-run without `--yes`). It never touches source code.
- **Remember:** `/dummyindex-remember` on Claude or `$dummyindex-remember` on
  Codex rolls session memory down its tiers.
- **Correct recurring skill misses:** Claude SessionStart deterministically mines explicit human “use/invoke/apply/follow … skill” corrections across local profiles. It stores them in a bounded gitignored cache. UserPromptSubmit injects fixed policy text for qualifying skills and handles a direct correction or revocation on the same turn. No prompt text or event metadata is persisted. Codex relies on its durable guidance rather than these Claude hooks.

The host boundary is deliberate. Claude's toolkit is created at plan time or on demand and evolves through `equip status|refresh|patch`. Codex uses native subagents without creating or evolving Claude equipment.

## States

A `.context/` folder is always in one of these states:

| State | What's true | What's missing |
|---|---|---|
| **Absent** | No `.context/` folder | Everything |
| **Scaffolded** | Deterministic backbone written | LLM-derived content; flows may be noisy |
| **Enriched (light)** | Dev-authored `spec.md` + `plan.md` per feature | Architect reorganisation; critic concerns |
| **Enriched (standard)** | Dev + architect + 1 relevant critic | Cross-critic review; full risk surface |
| **Enriched (deep)** | Dev + architect + all relevant critics with cross-review | — |
| **Stale** | Code changed since last rebuild | Index out of sync |
| **Drift** | Index says X, code says Y | Reconciliation |

## The always-on principle

- dummyindex is **not invoked manually per task**. It is installed once per repo.
- After install, Claude uses `.claude/CLAUDE.md` plus managed hooks. Codex uses its active project instruction file plus the installed Agent Skills.
- On Claude, session start surfaces drift automatically. On Codex, the agent follows durable guidance and explicit `$dummyindex --recouncil` / reconcile workflows. But dummyindex does not claim a Codex hook is installed.
- The agent and the human both start from a current, commit-anchored index, always.

## Freshness statusline (wired by install)

The SessionStart `plan-update` path does more than print the drift report. It also writes a **freshness-badge cache**. `dummyindex context statusline` *reads that cache*. It never recomputes drift. It prints a compact badge, suitable for a shell prompt. The badge is `[ctx ✓]` when current and `[ctx: N drift]` when not.

The badge is an ability, not an opt-in. When **no** `statusLine` is configured in either settings scope, install writes this value for you:

```json
"statusLine": { "type": "command", "command": "dummyindex context statusline" }
```

A `statusLine` is an un-sentinelled scalar, so the write is deliberately narrow — **write-if-absent, never clobber.** Any existing value (yours, or ours from a previous install) is left byte-identical. This is what makes a re-install idempotent without a sentinel to key on.

Replace it with your own and dummyindex keeps its hands off. Delete it and the next install re-wires it. When `settings.json` exists but cannot be parsed, the badge is skipped. Install prints the snippet to add by hand, and it does not overwrite the file.

A missing `.context/`, a missing or malformed cache, or any error → empty output,
exit 0. So the badge stays cheap (a cache read) and the "hooks report, the session
does the work" invariant holds.

## First-time install — Claude Code hook path

1. User types `/dummyindex` in Claude Code (in a repo).
2. The skill runs `dummyindex ingest <path>` — Layer 1 backbone.
3. Python writes `.context/` + the managed pointer block in `<repo>/.claude/CLAUDE.md` (a sentinel-wrapped `## dummyIndex context engine` section). Surrounding content is preserved.
4. The skill installs `.claude/settings.json` hooks across **five** events. None of them rebuilds the index or advances an anchor. They *inject, report, gate, and nudge*. The running session does the work:
   - **UserPromptSubmit** — two independent commands. The first is the compact always-on output/skill-routing fallback. The second is `dummyindex context memory prompt-context`. It emits bounded validated recurring-skill feedback plus any same-turn correction/revocation.
   - **SessionStart** — four commands. `dummyindex context plan-update` sends the drift report → `additionalContext`, and it writes the freshness-badge cache. `dummyindex context memory session-start` injects the memory block. `dummyindex context gc signal` is silent unless the commit-throttle is over threshold. Over threshold, it prints a one-line "run `/dummyindex-gc`" nudge. Fully silent `dummyindex context memory mine` refreshes the local skill-feedback cache.
   - **Stop** — two commands. `dummyindex context memory nudge` gives a handoff-checkpoint CTA when a significant session is unsaved. `dummyindex context reconcile-gate` blocks the session's exit **once** when `.context/` is stale after a substantial session. It directs the agent to reconcile + stamp. It never stamps itself.
   - **PreCompact** — runs `dummyindex context memory breadcrumb` (writes a breadcrumb to `now.md` before compaction).
   - **PreToolUse** (matcher `Write`) — runs `dummyindex context guard-doc-write`, the **managed-doc-homes** guard. It denies a `Write` that would create an internal planning doc in an unmanaged location. It names the `.context/` home it belongs in. The guard is fail-open and config-gated by `doc_guard_enabled`. A `doc_guard_allow` glob exempts a path. The guard never blocks a normal session.
   - A **`statusLine`** is installed when none exists in either scope (write-if-absent — an existing value, yours or ours, is never clobbered). See [Freshness statusline](#freshness-statusline-wired-by-install).
   - On upgrade, the installer scrubs any legacy `git post-commit` script and legacy dummyindex-core `PostToolUse` entry from prior versions. User-authored hooks are left untouched. The `equip` toolkit installs its own live `PostToolUse` formatter under a separate sentinel (`DUMMYINDEX_EQUIP`) — that one stays.
5. The skill enters the council phase (Layer 3 enrichment). Then it fills `tree.json` node abstracts (Phase 4.5 — on by default, opt out with `--no-tree-enrich`). See `council/52-tree-enrich.md`.
6. The skill runs `refresh-indexes` to reconcile.

After step 4, the session hooks are live. Steps 5 and 6 are the one-time deep enrichment.

The Headroom-derived feedback refresh is deliberately narrower than the explicit tool-loop report. It reads only this repo's root main transcripts. It requires exact row-level `cwd` and external-human provenance. It stores at most 64 safe slugs/counts in `.context/cache/skill-feedback.json`.

Runtime validation rejects symlinks, malformed/oversized state, and unknown fields. Injected policy is capped at eight skills and 1,600 characters. `Stop` remains the two commands above and never performs historical mining.

On Codex, the corresponding first run uses `$dummyindex`. It writes its managed block to the active project instruction file. It runs the same enrichment pipeline through native subagents. A Codex-only run persists `model=current` with hooks off and skips step 4 entirely. No `.claude/settings.json` or Codex hook configuration is written. A both-host run retains the Claude managed-hook choice while still using `model=current`.

## Drift detection at session start (augmented in v0.15.3)

```
Claude Code opens a session
   │
   ▼ SessionStart hook → dummyindex context plan-update   (command string unchanged)
   │
   ├─ mtime signal (always on): source files newer than their feature docs
   │
   └─ commit-anchored signals (when meta.indexed_commit is set):
        ├─ unassigned new files  — added since the anchor, owned by no feature
        └─ awaiting enrichment   — features a reconcile placed but didn't enrich
   │
   ▼ print the combined report (empty stdout if all current)
   │
   ▼ stdout fed to the session as additionalContext
   │
   ▼ mtime drift  → the session updates features/<id>/*.md in place
   ▼ commit signals → the session runs the reconcile procedure (--recouncil)
```

Two signals, **augmented — neither replaces the other**:

- **mtime drift** (always on, off-git too): a source file newer than its feature's docs. **Heuristic decay** — when the agent edits a feature doc, its mtime advances past the source. The signal then goes quiet, with no stamp. This is what keeps per-feature prose honest *without* forcing a council pass on a one-doc edit.
- **commit-anchored signals** (when an anchor exists): the two things mtime structurally cannot see. These are **new files owned by no feature** and **features awaiting enrichment**. They come from `meta.indexed_commit`..HEAD and clear only on `reconcile-stamp`. So they nudge toward the reconcile procedure rather than a one-off doc edit. Off-git, `unassigned` is empty (it needs a git diff) but `awaiting_enrichment` still works (it scans committed markers).

- The shell **never rebuilds the backbone and never advances the anchor**. The report is advisory. The running session does the reconciliation. The stamp is the session's job, never a hook's. A hook stamp would silently forget un-re-enriched drift.
- `plan-update` stays cheap: mtime stats plus, when anchored, one `git diff`.
- Council is **never** triggered by the hook. A large delta is the agent's cue
  to run `/dummyindex --recouncil` (the reconcile procedure).

## Manual deterministic rebuild — the quick refresh, not the update

`rebuild --changed` is the **deterministic backbone refresh**. It is a manual CLI command (not hook-wired) and, since v0.15.x, **non-destructive** on a curated index.

```
dummyindex context rebuild --changed
   │
   ▼ detect changed files by content hash (manifest)
   │
   ▼ on a curated/enriched index: refresh ONLY the deterministic artefacts
   │   (map/, symbols, symbol-graph, naming) — preserve the taxonomy + enriched
   │   docs, never re-cluster, never advance meta.indexed_commit
   │
   ▼ compute + print the reconcile drift report (drifted / unassigned / awaiting)
   │
   ▼ done — usually < 5s
```

- Use it after a large mechanical change (mass rename, generated-code drop) when
  you want the map current immediately.
- It refreshes map / symbols / call graph but does **not** place new files, re-enrich prose, or advance the anchor. That is the reconcile procedure's job. So `rebuild --changed` is a *refresh*, **not** the genuine update. On its own, it leaves new files unassigned. `--full` forces a destructive re-cluster (discards curated taxonomy) and is gated behind an explicit warning.

## Update — `/dummyindex-update` (version layers and prose)

The update skill moves three layers to one version: the CLI, the skill family and
the repo stamp. It runs five steps:

1. Resolve the target version to one immutable commit.
2. Detect the install method and update the CLI at that commit.
3. Refresh the skills and the repo wiring with `dummyindex install`. In `.context/`, it refreshes the deterministic backbone only.
4. Verify every layer with `dummyindex context check --versions`.
5. Restyle curated prose with `dummyindex context restyle`. This step runs on a
   curated index only. It skips when `restyle plan` prints `already restyled` or `nothing to restyle`. When every layer already equals the target version, the update still runs this step, with the same skip rules.

Step 5 rewrites prose in place. It never changes the taxonomy.

It never runs the council, `reconcile` or a full re-ingest. Each unit passes a token
check. A failed unit stays failed until its tokens match. A refused unit does not undo
steps 1 to 4. Resume an unfinished run with `dummyindex context restyle status`.

## Reconcile — the genuine update (v0.15.3)

The non-destructive update path that the user-facing "keep `.context/` current" promise rests on. `.context/` knows the commit it was last reconciled against. When source moves on, the running session folds the delta in and re-anchors.

```
dummyindex context reconcile [--json]      # read-only: what drifted since the anchor
   │
   ▼ recover features awaiting enrichment (a prior, interrupted pass left them)
   ▼ place unassigned new files  → scaffold-feature (new) | assign-files (attach)
   ▼ re-enrich drifted + placed features  (/dummyindex --recouncil <id>, per id)
   │
   ▼ dummyindex context reconcile-stamp     # advance meta.indexed_commit to HEAD
```

- **`reconcile-stamp` is the transactional boundary.** It refuses while unassigned files or awaiting-enrichment features remain. An advance past them would silently forget them. `reconcile-stamp` does **not** block on drift (only the stamp clears drift).
- **Restart-safe.** Every signal is reconstructed from disk (committed markers + the git diff). So an interrupted pass resumes exactly where it stopped. The stamp cannot advance past unfinished work.
- The full procedure is `council/65-reconcile.md`. The session runs it. No hook ever does (no council in a shell, and an auto-stamp would lose drift).

## Re-running the council

- The council is **manual or on a schedule**, never on every edit.
- Triggers:
  - User types `/dummyindex --recouncil` to refresh the deep layer.
  - A cron-style schedule (weekly, configurable in `.context/config.json`).
  - The agent detects a major refactor (e.g., > 30% of files changed since last council) and surfaces a suggestion.
- Re-runs are **cached per feature**: a feature whose aggregate source hash has not changed is skipped.

## Steady-state day in the life

```
09:00  User opens Claude Code session
       └─ SessionStart hook: plan-update prints nothing — index current at the anchor
09:30  Claude edits two files in the auth feature + updates auth/plan.md
       └─ mtime drift clears for auth as the doc is saved (no stamp needed)
11:00  Claude adds a new file payments/webhook.py for a feature that didn't exist
       └─ mtime can't see it (no feature owns it yet) — but it's net-new code
13:30  User opens a fresh Claude Code session
       └─ SessionStart: plan-update reports "1 new file not in any feature: payments/webhook.py"
       └─ the session runs the reconcile procedure: scaffolds a `payments` feature
          (or attaches webhook.py to an existing one), enriches it, reconcile-stamp
       └─ anchor advances; next session starts clean
14:00  Big refactor touched 6 features + added 2 files
       └─ plan-update reports drift on 6 + 2 unassigned; agent runs /dummyindex --recouncil
       └─ council re-enriches the 6 (cached for the other 8) + places the 2, ~3 min, $2
```

## Cache behavior

- Per-file content hash determines whether AST re-extraction runs.
- Per-feature aggregate hash (sum of file hashes) determines whether the council re-runs.
- Cache survives rebuilds. Cache is path-independent (machine-portable).
- Cache lives at `.context/cache/`. Gitignored automatically.

## What never gets regenerated

- The council audit trail (`features/<id>/council/`) persists across rebuilds unless the feature's aggregate hash changed.
- Hand-edited prose OUTSIDE managed markers (e.g., your existing `CLAUDE.md`) stays untouched.
- The cache.

## What always gets regenerated on rebuild

- Every JSON artifact (`tree.json`, `map/*.json`, `features/INDEX.json`).
- Every derived markdown (`INDEX.md`, `features/INDEX.md`).
- The viewer (`features/graph.html`) — always, and `features/graph.json` **only while it is still the deterministic seed**. Once the codebase-scan stage has authored it (`confidence: INFERRED`), a rebuild preserves it verbatim, exactly like an enriched `spec.md`. The rebuild only re-renders the viewer around it.
- Conventions (`conventions/naming.{md,json}`) — derived from current code.
- The deterministic stubs in `feature.json` (members, files, entry_points). But the LLM-written name/summary survives if confidence is INFERRED and the hash matches.

## Failure modes + recovery

| Failure | Recovery |
|---|---|
| AST extraction fails for one file | That file's symbols are missing; rest of `.context/` still writes |
| Graph build fails | `features/` is skipped; everything else still writes |
| SessionStart hook fails silently | Next session's `plan-update` re-surfaces the same drift; nothing is lost |
| Pipeline subagent fails | `_council-log.json` records failure; resume from that stage on next run |
| Architect stage fails after dev draft | `01-dev-draft.md` is on disk; re-run from `/plan` alone |
| Critic stage fails | `plan.md` is finalised; re-run `/critique` alone, mode-gated |
| User Ctrl-C mid-council | Resume from `_council-log.json` on next run |
| Hook not installed (e.g., user cloned a repo on a fresh machine) | First `/dummyindex` re-installs it |

## Costs over a year

- First-time install + ingest + deep council on a 14-feature repo: ~$25 one-time.
- SessionStart drift check (`plan-update`): **no LLM** — mtime stats plus, when
  anchored, one `git diff`. Cheap, not literally free, but nowhere near a token cost.
- Manual `rebuild --changed` and `reconcile` (the report): **no LLM**.
- Per-session reconciliation: metered against the session's normal token budget. The agent edits a few feature docs or places/enriches a new feature. The only separate council cost is a targeted `--recouncil` on what drifted.
- Weekly council refresh: ~$5 (cache hits on most features).
- Big refactor + targeted re-council: ~$2–10.

The drift hook is the secret. It surfaces staleness (and now net-new code) without ongoing token spend. The session reconciles it as part of normal work.
