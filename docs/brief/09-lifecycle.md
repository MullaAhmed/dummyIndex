# 09 — Lifecycle

How a repo moves from "no `.context/`" to "always-current, always-on" and stays there.

## States

A `.context/` folder is always in one of these states:

| State | What's true | What's missing |
|---|---|---|
| **Absent** | No `.context/` folder | Everything |
| **Scaffolded** | Deterministic backbone written | LLM-derived content; flows may be noisy |
| **Enriched (light)** | Chairman synthesized READMEs | Multi-perspective depth |
| **Enriched (standard)** | Architect + relevant specialist + chairman | Cross-review breadth |
| **Enriched (deep)** | Full 5-persona council, cross-reviewed, synthesized | — |
| **Stale** | Code changed since last rebuild | Index out of sync |
| **Drift** | Index says X, code says Y | Reconciliation |

## The always-on principle

- dummyindex is **not invoked manually per task**. It's installed once per repo.
- After install, **every Claude Code session uses it** via the managed `CLAUDE.md` block + the SessionStart hook.
- **Every edit triggers a refresh** via the PostToolUse hook.
- **Every commit triggers a refresh** via the post-commit git hook.
- The agent and the human both work against a fresh index, always.

## First-time install

1. User types `/dummyindex` in Claude Code (in a repo).
2. The skill runs `dummyindex ingest <path>` — Layer 1 backbone.
3. Python writes `.context/` + the 3-line managed block in `<repo>/CLAUDE.md`.
4. The skill installs hooks:
   - **post-commit** git hook: `.git/hooks/post-commit` → runs `rebuild --changed`.
   - **PostToolUse** hook in `.claude/settings.json`: matches `Edit|Write|Bash(mv|rm|cp)` → runs `rebuild --changed`.
   - **SessionStart** hook in `.claude/settings.json`: runs `context check --auto-refresh`.
5. The skill enters the council phase (Layer 3 enrichment).
6. The skill runs `refresh-indexes` to reconcile.

After step 4, the auto-refresh loop is live. Steps 5 and 6 are the one-time deep enrichment.

## Auto-refresh on commit

```
git commit
   │
   ▼ post-commit hook
   │
   ▼ dummyindex context rebuild --changed
   │
   ▼ detect changed files by content hash
   │
   ▼ re-extract changed files only
   │
   ▼ recompute affected tree.json subtrees, map/, features/symbol-graph.json
   │
   ▼ refresh-indexes  (regenerate INDEX.md, features/INDEX.md, features/graph.json+html)
   │
   ▼ done — usually < 5s
```

- Council is **NOT triggered** here. Only the deterministic backbone refreshes.
- The agent gets a current map + current symbols + current call graph — but the rich prose (architecture.md, security.md, …) stays from the last council run.
- That's deliberate: deterministic refresh is cheap; council refresh is metered.

## Auto-refresh on edit

- Triggered by Claude Code's PostToolUse hook after Edit/Write/Bash(mv|rm|cp).
- Same code path as post-commit, but scoped to the touched files.
- Throttled: if multiple edits happen rapidly, the hook coalesces (last edit + 2s debounce).
- If `rebuild --changed` would take > 3 seconds, the hook backgrounds it and the session continues.

## Session start

```
Claude Code opens a session
   │
   ▼ SessionStart hook
   │
   ▼ dummyindex context check --auto-refresh
   │
   ▼ compare current source file hashes to .context/meta.json
   │
   ▼ if any drift: run rebuild --changed quietly before the session prompt
   │
   ▼ session begins with a current .context/
```

- The agent **never sees a stale index**.
- The check is fast (~100ms on a 200-file repo) — just hashes + a diff.

## Drift detection

- A check that runs on demand AND on session start.
- Compares: each file's current SHA-256 vs. its stored hash in `.context/cache/manifest.json`.
- Reports: added / modified / removed.
- If anything changed: auto-refresh (Layer 1 only) by default; or surface a prompt to recommend a full council re-run if many features were touched.

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
       └─ SessionStart hook: .context/ is fresh, no work needed
09:30  Claude edits two files via Edit tool
       └─ PostToolUse hook: rebuild --changed on the two files
09:45  User commits
       └─ post-commit hook: rebuild --changed (now includes the commit's diff)
12:00  User refactors the auth feature
       └─ rebuild --changed runs after each step (transparent)
       └─ agent now reads stale council prose (architect's doc was written before refactor)
       └─ agent notes the discrepancy: "code says X, .context/ says Y"
12:30  User types /dummyindex --recouncil auth
       └─ council re-runs for auth only (cached for the other 13 features)
       └─ ~3 min, $1
13:00  All current. Loop continues.
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
| Hook fails silently | A session-start drift check catches it and rebuilds |
| Council subagent fails | `_council-log.json` records failure; resume from that point |
| Chairman synthesis fails | The 5 perspectives stay on disk; re-run chairman alone |
| User Ctrl-C mid-council | Resume from `_council-log.json` on next run |
| Hooks not installed (e.g., user cloned a repo on a fresh machine) | First `/dummyindex` re-installs them |

## Costs over a year

- First-time install + ingest + deep council on a 14-feature repo: ~$25 one-time.
- Auto-refresh per commit / per edit: **free** (no LLM).
- Auto-refresh on session start: **free**.
- Weekly council refresh: ~$5 (cache hits on most features).
- Big refactor + targeted re-council: ~$2–10.

The auto-refresh loop is the secret. It guarantees current state without ongoing token spend.
