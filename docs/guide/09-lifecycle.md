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

- **Stay current:** SessionStart injects drift + memory; the session reconciles
  `.context/` with the code; `rebuild --changed` re-indexes.
- **Plan new work:** `/dummyindex-plan` → consistency-checked proposals
  (spec / plan / checklist) grounded in the index, then **auto-equips** the
  project-tuned toolkit for the proposal (`equip apply --for-proposal <slug>`,
  deterministic, idempotent) so build finds the agents ready.
- **Build:** `/dummyindex-build` drives the checklist through the equipped agents
  (verify-before-tick), then re-indexes — the loop compounds. If the repo isn't
  equipped at all (no `equipment.json`), build **warns and halts** rather than
  silently falling back to `general-purpose`.
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
- **At session start**, drift is surfaced and the session reconciles prose with code (Layer 5, v0.13.5 model).
- The agent and the human both start from a current index, always.

## First-time install

1. User types `/dummyindex` in Claude Code (in a repo).
2. The skill runs `dummyindex ingest <path>` — Layer 1 backbone.
3. Python writes `.context/` + the 3-line managed block in `<repo>/CLAUDE.md`.
4. The skill installs **one** hook (v0.13.5):
   - **SessionStart** hook in `.claude/settings.json`: runs `dummyindex context plan-update`, whose stdout drift report is fed to the session as `additionalContext`.
   - On upgrade, the installer scrubs any legacy `git post-commit` script and sentinel-bearing `PostToolUse` entry from prior versions (user-authored hooks are left untouched).
5. The skill enters the council phase (Layer 3 enrichment), then fills `tree.json` node abstracts (Phase 4.5 — mode-gated; see `council/52-tree-enrich.md`).
6. The skill runs `refresh-indexes` to reconcile.

After step 4, the drift hook is live. Steps 5 and 6 are the one-time deep enrichment.

## Drift detection at session start (v0.13.5)

```
Claude Code opens a session
   │
   ▼ SessionStart hook
   │
   ▼ dummyindex context plan-update
   │
   ▼ for each feature: compare source file mtimes to the feature's docs' mtimes
   │
   ▼ print one line per drifting feature (empty stdout if all current)
   │
   ▼ stdout fed to the session as additionalContext
   │
   ▼ the session updates features/<id>/*.md in place, with full context of the change
```

- The shell **never rebuilds the backbone**. The drift report is advisory; the agent does the reconciliation.
- `plan-update` is fast (mtime stats, no hashing) — sub-100ms on a 200-file repo.
- **Heuristic decay**: when the agent edits a feature doc, that doc's mtime advances past the source mtime and the drift signal naturally goes quiet. No explicit `mark-updated` command.
- Council is **never** triggered here. If many features drifted (a big refactor), the report is the agent's cue to suggest `/dummyindex --recouncil`.

## Manual deterministic rebuild

The full Layer 1 refresh still exists as a **manual** CLI command — it's just no longer wired to a hook.

```
dummyindex context rebuild --changed
   │
   ▼ detect changed files by content hash (manifest)
   │
   ▼ re-extract changed files only
   │
   ▼ recompute affected tree.json subtrees, map/, features/symbol-graph.json
   │
   ▼ refresh-indexes  (regenerate INDEX.md, features/INDEX.md, features/graph.json+html)
   │
   ▼ done — usually < 5s
```

- Use it after a large mechanical change (mass rename, generated-code drop) where you want the deterministic map current immediately rather than waiting for the next session.
- It refreshes the map / symbols / call graph but **not** the council prose (`spec.md` / `plan.md` / `concerns.md`) — that's the council's job, gated by content hash.

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
       └─ SessionStart hook: plan-update prints nothing — all features current
09:30  Claude edits two files in the auth feature via Edit tool
       └─ no hook fires on edit; the docs for auth are now older than the source
12:00  User refactors the auth feature further, commits
       └─ no shell rebuild; the working index is unchanged on disk
13:30  User opens a fresh Claude Code session
       └─ SessionStart hook: plan-update reports "auth: 3 source files newer than docs"
       └─ the session reads the drift line, opens auth/plan.md + the changed source
       └─ updates auth/plan.md + auth/concerns.md in place (mtimes advance, signal clears)
14:00  Big refactor touched 6 features
       └─ plan-update reports all 6; agent suggests /dummyindex --recouncil
       └─ user runs it; council re-runs those 6 (cached for the other 8), ~3 min, $2
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
- SessionStart drift check (`plan-update`): **free** (mtime stats, no LLM).
- Manual `rebuild --changed`: **free** (no LLM).
- Per-session doc reconciliation: metered against the session's normal token budget — the agent edits a few feature docs, no separate council cost.
- Weekly council refresh: ~$5 (cache hits on most features).
- Big refactor + targeted re-council: ~$2–10.

The drift hook is the secret. It surfaces staleness without ongoing token spend, and the session reconciles it as part of normal work.
