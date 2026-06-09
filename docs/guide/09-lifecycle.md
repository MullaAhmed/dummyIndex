# 09 — Lifecycle

How a repo moves from "no `.context/`" to "always-current, always-on" and stays there.

## Two modes (v0.15)

dummyindex runs in two modes per repo:

**1. Setup mode — one-time bootstrap.** `/dummyindex` (first run):
preflight inventory → ingest (AST index + `.context/` backbone) → onboarding
(config) → council enrichment (spec/plan/concerns per feature) + conventions →
source-docs catalog → CLAUDE.md managed block + SessionStart hooks → session-memory
store seeded. Setup builds `.context/` + hooks (+ the CLAUDE.md block); it does
**not** equip — the project-tuned toolkit in `.claude/` is generated later, at
plan time (see below) or on demand via standalone `/dummyindex-equip`. Physically
reorganising the repo's real docs stays opt-in (`--reorg-docs`, destructive, gated).

**2. Ongoing mode — every session after.** The spine plans, builds, and evolves:

- **Stay current (commit-anchored):** `.context/` records the commit it was last
  reconciled against (`meta.indexed_commit`). SessionStart injects a drift report
  + memory; when source has moved on, the running session runs the **reconcile
  procedure** (`council/65-reconcile.md`) — place new files, re-enrich drifted
  features, then `reconcile-stamp` to advance the anchor. `rebuild --changed` is
  the *quick deterministic refresh* of the backbone (maps/symbols/graph), now
  non-destructive — it preserves the curated taxonomy + enrichment and surfaces
  the same drift; it is **not** the genuine update (it would leave new files
  unassigned). The anchor moves only on `ingest` or `reconcile-stamp` — never
  from a hook.
- **Plan new work:** `/dummyindex-plan` → consistency-checked proposals
  (spec / plan / checklist) grounded in the index, then **auto-equips** the
  project-tuned toolkit for the proposal (`equip apply --for-proposal <slug>`,
  deterministic, idempotent) so build finds the agents ready.
- **Build:** `/dummyindex-build` drives the checklist through the equipped agents
  wave-by-wave — items in a `## Wave N` group dispatch in parallel, waves run in
  order (verify-before-tick per item) — then **reconciles** the new code into `.context/` (place +
  enrich + stamp) — not a bare rebuild, which would leave the built files
  unassigned. The loop compounds. If the repo isn't equipped at all (no
  `equipment.json`), build **warns and halts** rather than silently falling back
  to `general-purpose`.
- **Evolve the toolkit:** `equip status|refresh|patch` — build-run learnings are
  patched into the generated tooling (origin-hash baselined; user edits never
  stomped).
- **Deprecate:** `features-merge` / `flow-remove` consolidate the index;
  `equip uninstall|reset` retire or restore tooling; drift naturally retires prose
  for deleted code.
- **Remember:** `/dummyindex-remember` rolls session memory down its tiers.

The boundary is deliberately soft in one place: the toolkit is *created* at plan
time (auto-equipped per proposal) or on demand via standalone `/dummyindex-equip`,
and keeps *evolving* in ongoing mode (`equip status|refresh|patch`).

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

- dummyindex is **not invoked manually per task**. It's installed once per repo.
- After install, **every Claude Code session uses it** via the managed `CLAUDE.md` block + the SessionStart drift hook.
- **At session start**, drift is surfaced (stale docs + new files + features awaiting enrichment) and the session reconciles `.context/` with the code, advancing the commit anchor when it stamps.
- The agent and the human both start from a current, commit-anchored index, always.

## First-time install

1. User types `/dummyindex` in Claude Code (in a repo).
2. The skill runs `dummyindex ingest <path>` — Layer 1 backbone.
3. Python writes `.context/` + the 3-line managed block in `<repo>/CLAUDE.md`.
4. The skill installs **three** `.claude/settings.json` hooks, none of which rebuild the index:
   - **SessionStart** — runs `dummyindex context plan-update`, whose stdout drift report is fed to the session as `additionalContext`.
   - **Stop** — runs `dummyindex context memory nudge` (handoff-checkpoint CTA when a significant session is unsaved).
   - **PreCompact** — runs `dummyindex context memory breadcrumb` (writes a breadcrumb to `now.md` before compaction).
   - On upgrade, the installer scrubs any legacy `git post-commit` script and sentinel-bearing `PostToolUse` entry from prior versions (user-authored hooks are left untouched).
5. The skill enters the council phase (Layer 3 enrichment), then fills `tree.json` node abstracts (Phase 4.5 — mode-gated; see `council/52-tree-enrich.md`).
6. The skill runs `refresh-indexes` to reconcile.

After step 4, the session hooks are live. Steps 5 and 6 are the one-time deep enrichment.

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

- **mtime drift** (always on, off-git too): a source file newer than its
  feature's docs. **Heuristic decay** — when the agent edits a feature doc, its
  mtime advances past the source and the signal goes quiet, with no stamp. This
  is what keeps per-feature prose honest *without* forcing a council pass on a
  one-doc edit.
- **commit-anchored signals** (when an anchor exists): the two things mtime
  structurally can't see — **new files owned by no feature** and **features
  awaiting enrichment**. They come from `meta.indexed_commit`..HEAD and clear
  only on `reconcile-stamp`, so they nudge toward the reconcile procedure rather
  than a one-off doc edit. Off-git, `unassigned` is empty (it needs a git diff)
  but `awaiting_enrichment` still works (it scans committed markers).

- The shell **never rebuilds the backbone and never advances the anchor**. The
  report is advisory; the running session does the reconciliation (and the stamp
  is the session's job, never a hook's — a hook stamp would silently forget
  un-re-enriched drift).
- `plan-update` stays cheap: mtime stats plus, when anchored, one `git diff`.
- Council is **never** triggered by the hook. A large delta is the agent's cue
  to run `/dummyindex --recouncil` (the reconcile procedure).

## Manual deterministic rebuild — the quick refresh, not the update

`rebuild --changed` is the **deterministic backbone refresh**. It's a manual CLI
command (not hook-wired) and, since v0.15.x, **non-destructive** on a curated
index.

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
- It refreshes map / symbols / call graph but does **not** place new files,
  re-enrich prose, or advance the anchor — that's the reconcile procedure's job.
  So `rebuild --changed` is a *refresh*, **not** the genuine update; on its own it
  leaves new files unassigned. `--full` forces a destructive re-cluster (discards
  curated taxonomy) and is gated behind an explicit warning.

## Reconcile — the genuine update (v0.15.3)

The non-destructive update path the user-facing "keep `.context/` current" promise
actually rests on. `.context/` knows the commit it was last reconciled against;
when source moves on, the running session folds the delta in and re-anchors.

```
dummyindex context reconcile [--json]      # read-only: what drifted since the anchor
   │
   ▼ recover features awaiting enrichment (a prior, interrupted pass left them)
   ▼ place unassigned new files  → scaffold-feature (new) | assign-files (attach)
   ▼ re-enrich drifted + placed features  (/dummyindex --recouncil <id>, per id)
   │
   ▼ dummyindex context reconcile-stamp     # advance meta.indexed_commit to HEAD
```

- **`reconcile-stamp` is the transactional boundary.** It refuses while unassigned
  files or awaiting-enrichment features remain (advancing past them would silently
  forget them); it does **not** block on drift (only the stamp clears drift).
- **Restart-safe.** Every signal is reconstructed from disk (committed markers +
  the git diff), so an interrupted pass resumes exactly where it stopped — the
  stamp can't advance past unfinished work.
- The full procedure is `council/65-reconcile.md`. The session runs it; no hook
  ever does (no council in a shell, and an auto-stamp would lose drift).

## Re-running the council

- The council is **manual or on a schedule**, never on every edit.
- Triggers:
  - User types `/dummyindex --recouncil` to refresh the deep layer.
  - A cron-style schedule (weekly, configurable in `.context/config.json`).
  - The agent detects a major refactor (e.g., > 30% of files changed since last council) and surfaces a suggestion.
- Re-runs are **cached per feature**: a feature whose aggregate source hash hasn't changed is skipped.

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
- The viewer (`features/graph.json`, `features/graph.html`).
- Conventions (`conventions/naming.{md,json}`) — derived from current code.
- The deterministic stubs in `feature.json` (members, files, entry_points) — but the LLM-written name/summary survives if confidence is INFERRED and the hash matches.

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
- Per-session reconciliation: metered against the session's normal token budget —
  the agent edits a few feature docs or places/enriches a new feature; the only
  separate council cost is a targeted `--recouncil` on what actually drifted.
- Weekly council refresh: ~$5 (cache hits on most features).
- Big refactor + targeted re-council: ~$2–10.

The drift hook is the secret. It surfaces staleness (and now net-new code) without
ongoing token spend, and the session reconciles it as part of normal work.
