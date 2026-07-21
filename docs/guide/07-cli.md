# 07 — CLI surface

Every command. What it does. Why it exists.

> **The CLI is the agent's backbone — you don't run it by hand.** The skill and
> council invoke these commands to move bytes around atomically; everything that
> needs judgment stays in markdown (see [the closing rule](#what-is-not-a-cli-command)).
> A human's interface is **slash commands** in Claude Code or `$skill` mentions
> in Codex. The lone
> exception is the one-time **Installation** bootstrap below — `pip install dummyindex`
> + `dummyindex install` — which a human runs in a terminal to put the skill in place.

## Installation — the human bootstrap (run once)

The one place a human touches the terminal. Every section after this is agent-invoked.

### `dummyindex install [--platform claude|codex|both] [--scope user|project] [--dir PATH] [--skill-only] [--no-onboarding] [--defaults] [--no-default-plugins] [--no-superpowers]`

- Copies all eight skills into `.claude/skills/` for Claude Code,
  `.agents/skills/` for Codex, or both. The default remains `claude` for
  backward compatibility.
- `--scope user` (default) installs under the user's home; `--scope project`
  installs under `<PATH>`.
- Claude uses `/dummyindex*`; Codex discovers the same family through `/skills`
  and invokes it as `$dummyindex*`.
- Claude's `/tokens` remains a host-specific command because its reporter reads
  Claude transcript files. Codex uses native `/status` for current
  context/session tokens and `/usage` for account usage.
- **Auto-init**: on a git repo, builds `.context/` and writes the selected host
  guidance. Claude receives `.claude/CLAUDE.md` plus hooks; Codex receives its
  active project instruction file and no Claude settings. Pass `--skill-only`
  to copy skills alone.
- **Installs four managed Claude hook events** as part of auto-init — SessionStart (`plan-update`, `memory session-start`, `gc signal`), Stop (`memory nudge`, `reconcile-gate`), PreCompact (`memory breadcrumb`), and PreToolUse Write (`guard-doc-write`). None rebuild the index or stamp the anchor (unlike the legacy pre-v0.13.5 shell-rebuild hooks).
- **When Claude is selected, refreshes equip-generated tools** to the current
  templates as part of auto-init, so `/dummyindex-update` carries that Claude
  toolkit forward. A Codex-only install neither creates nor refreshes Claude
  equipment.
- `--defaults` / `--no-onboarding` writes config non-interactively. Claude-only
  defaults to `sonnet-4.6` with hooks on; Codex-only to `current` with hooks off;
  `both` to portable `current` with Claude hooks on.
- `--no-default-plugins` skips every native default plugin for this run.
  `--no-superpowers` is retained as a compatibility alias with identical
  behavior. The flags do not persist an opt-out or remove the always-on project
  output policy described below.

#### Reviewed default plugins and always-on behavior

When `claude` or `both` is selected, install/auto-init declares the selected
defaults in project `.claude/settings.json` and makes one best-effort
materialization pass:

1. `superpowers@claude-plugins-official` from the official marketplace.
2. `caveman@caveman`, with marketplace source pinned to
   `JuliusBrussee/caveman@0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0`.
   The reviewed plugin exposes skills and commands plus `SessionStart` and
   `UserPromptSubmit` Node command hooks, so `runs_code=true`.
3. `i-have-adhd@i-have-adhd`, with marketplace source pinned to
   `ayghri/i-have-adhd@0241185d6c7f2d0763a988ce52eceb13ea9f5c1f`.
   The reviewed plugin exposes one inert skill and no executable plugin hook,
   so `runs_code=false`.

The two third-party entries are a narrow, reviewed built-in exception. Their
immutable SHAs and blast radii are disclosed before settings or runner action;
a ref change requires another source review and release. This does **not**
relax `context equip`'s approval requirement for any other third-party source.
Marketplace declaration is preserved even when the Claude CLI is unavailable,
so Claude Code can resolve the target later. Failures are reported per target
and do not fail indexing or prevent later independent defaults from being
attempted.

A Codex-only install writes no `.claude/**` files and invokes no Claude runner.
It receives the behavior through the active managed **project** instruction
file instead. Claude's managed project block carries the same policy: apply the
combined `caveman`/`i-have-adhd` behavior on every reply without waiting for an
invocation; lead with the outcome or next action, keep prose compact, number
multi-step work, suppress tangents, restate current state, and preserve
technical and safety detail. Explicit user formatting requests and safety
requirements win. The policy is not written to Codex's global guidance.

There are three distinct opt-out layers for the native defaults:

- **One run, all three:** pass `--no-default-plugins`, or its legacy
  `--no-superpowers` alias. The gate runs before config reconciliation,
  marketplace/settings changes, runner probes, or code execution; a current
  config remains byte-identical.
- **Durable, all three:** set `.context/config.json` field
  `default_plugins_enabled` to `false`. Reinstall/update does not backfill
  missing defaults while this explicit state remains disabled.
- **Durable, one target:** set its project or local `enabledPlugins` value to
  `false`. That tombstone wins over project/local precedence, remains `false`,
  and is never materialized by dummyindex.

Malformed config fails closed. Install/init warns and performs no default
marketplace declaration, enabled-plugin write, runner action, backfill, or
config mutation instead of falling back to the built-in tuple.

### `dummyindex uninstall [--platform claude|codex|both] [--scope user|project] [--dir PATH]`

- Removes the selected host's skill family and version stamp; Claude command
  aliases owned by dummyindex are removed with a Claude selection.
- Project-scope Codex removal cleans that project's managed guidance. User
  scope cleans global guidance plus only a current/`--dir` project block
  stamped as that user install's auto-init; explicit project/ingest and legacy
  unowned blocks are preserved. Claude guidance and project hooks have separate
  lifecycle commands and are left intact.
- Best-effort cleanup of now-empty skill/command parent directories.

## Backbone

### `dummyindex ingest [path] [--root DIR] [--platform claude|codex|both] [--no-hooks] [--no-default-plugins] [--no-superpowers] [--force] [--depth light|standard|deep] [--docs PATH]...`

- Primary entry point. Equivalent to `context init`.
- Runs the deterministic backbone on `path`.
- Writes `.context/` and host guidance. Codex uses its active project
  instruction file (`AGENTS.override.md`, `AGENTS.md`, or a configured
  fallback); Claude uses
  `.claude/CLAUDE.md` and installs hooks by default.
- Refuses to replace a curated/enriched index unless `--force` is explicit;
  use `rebuild --changed` for a non-destructive refresh. `--depth` is a one-run
  council-depth override. `--no-default-plugins` (or compatibility alias
  `--no-superpowers`) applies the one-run native-default gate above.
- Smart default: relative `path` under cwd → output to cwd; absolute path → output to that path.
- `--docs PATH` (repeatable) — adds external doc folders to the source-docs catalog. In-repo docs (`README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `SECURITY.md`, `BRIEF.md`, any root-level `*.md`, plus `docs/`, `doc/`, `documentation/`, `ADR/`, `RFC/`) are discovered automatically.

### `dummyindex context init [path] [--root DIR] [--platform claude|codex|both] [--no-hooks] [--no-default-plugins] [--no-superpowers] [--force] [--depth light|standard|deep] [--docs PATH]...`

- Same as `ingest`.

### `dummyindex context rebuild [--changed] [--full] [path] [--root DIR] [--docs PATH]...`

- Full or incremental rebuild.
- `--changed` re-extracts only files whose content hash changed (the manual incremental path). The manifest tracks both code and in-repo docs, so a README edit is detected. As of v0.13.5 this is run manually, not from a hook.
- **Non-destructive on an enriched index.** When `features/INDEX.json` carries a curated taxonomy (a feature renamed off `community-*`, or an `INFERRED` confidence), `--changed` no longer re-clusters or re-stubs. It refreshes only the deterministic, enrichment-free artefacts (`map/files.json`, `map/symbols.json`, `conventions/naming.{json,md}`, `source-docs/INDEX.{json,md}`, `features/symbol-graph.json`), preserves `tree.json` abstracts and every per-feature `spec.md`, and prints a reconcile report (drifted features + unassigned new files). It deliberately leaves `meta.indexed_commit` unchanged until the curated reconcile procedure finishes and runs `reconcile-stamp`. A fresh deterministic-only index (all `community-*` / `EXTRACTED`) still full-builds.
- `--full` forces the destructive full re-cluster regardless, printing a warning that it discards any curated taxonomy + enrichment. Use after an intentional from-scratch reset; otherwise pass `--changed` for the non-destructive path.
- `--docs PATH` accepts the same form as `ingest`. Pass it on every rebuild that should preserve the same external doc roots.
- Outputs `added / modified / removed` summary (or the reconcile report on the enriched path).

### `dummyindex context check [path] [--root DIR] [--auto-refresh] [--quiet] [--docs PATH]... [--versions]`

- Manifest-based drift detection. Compares current source + doc content hashes to the stored manifest; reports `added / modified / removed`.
- `--auto-refresh` runs `rebuild --changed` automatically when drift is detected.
- `--quiet` suppresses human-readable output; the exit code still reports clean
  (`0`), drift (`1`), or usage/setup failure (`2`).
- `--docs PATH` mirrors `ingest` so external doc roots aren't reported as `removed`.
- `--versions` is a separate read-only diagnostic. It compares the running CLI,
  `.context` stamp, and every repo/user × Claude/Codex skill stamp independently,
  reports PATH shadowing, never fixes anything, and always exits 0.
- A manual inspection command. **No longer auto-refreshes** and is **not** the SessionStart hook (that's `plan-update`, below).

### `dummyindex context plan-update [path] [--root DIR]`

- The SessionStart-hook command (v0.13.5).
- Prints a markdown drift report to stdout: one line per feature whose source-file mtime exceeds the max mtime of that feature's docs. Empty stdout when nothing is stale.
- Claude Code's `SessionStart` hook takes the plain stdout as `additionalContext` — no JSON wrapping.
- Advisory only: it does not rebuild or rewrite anything. The running session reconciles the named features' docs in place.

### `dummyindex context reconcile-gate [path] [--root DIR]`

- The Stop-hook reconcile gate (v0.23.0). Reads the Stop hook's JSON from stdin (`stop_hook_active`, `session_id`, `transcript_path`).
- Prints a Claude Code `{"decision":"block","reason":…}` payload — **blocking the session's exit once** — when `.context/` is stale (`compute_drift` reports drift) **after a substantial session** (subagents ran, or main-thread output ≥ the significance threshold). The `reason` is a scoped directive: re-run the council for the drifted features (`/dummyindex --recouncil <feature>`), place any new files, then `dummyindex context reconcile-stamp`.
- Silent (allows the stop) when the index is fresh, on the re-entrant stop (`stop_hook_active` true → **block-once**, never traps the session), on a trivial session, or when opted out via `"auto_council": false` in `.context/config.json`.
- **The hook never writes or stamps `.context/`** — the agent runs the council and advances the anchor, preserving the "no hook may stamp" invariant. Always exits 0 (a Stop hook must never fail the turn).

### `dummyindex context bootstrap [path] [--root DIR] [--platform claude|codex|both]`

- Regenerates selected host guidance without rebuilding `.context/`: Claude's
  managed block in `.claude/CLAUDE.md`, the active project-level Codex
  instruction file, or both. The default remains `claude` for backward
  compatibility.
- Useful when managed guidance text changes (e.g., schema bumps).

## Hooks (installed by `ingest` or `install --scope project`)

### `dummyindex context hooks install [path] [--root DIR]`

- Idempotent. Installs **four** `.claude/settings.json` hook events, none of which rebuild the index or stamp the anchor:
  - SessionStart — runs `dummyindex context plan-update` (drift report + freshness badge cache), `dummyindex context memory session-start` (memory block), and `dummyindex context gc signal` (commit-throttled `/dummyindex-gc` nudge).
  - Stop — runs `dummyindex context memory nudge` (handoff-checkpoint CTA) **and** `dummyindex context reconcile-gate` (the block-once reconcile gate).
  - PreCompact — runs `dummyindex context memory breadcrumb` (writes a breadcrumb to `now.md`).
  - PreToolUse (`Write`) — runs `dummyindex context guard-doc-write` (managed-doc-homes guard).
- `--global` writes `~/.claude/settings.json` instead, so the hooks fire in **every** repo (self-gating on `.context/` existing). A repo's own `--local` install overrides the global one — global hook bodies carry a `dummyindex context hooks defer-check` guard that yields when the repo has its own dummyindex hooks.
- **Upgrade scrub** (local scope): removes any legacy `git post-commit` script and sentinel-bearing `PostToolUse` entry installed by pre-v0.13.5 versions. User-authored hooks (no sentinel) are left untouched.

### `dummyindex context hooks defer-check [path] [--root DIR]`

- Silent exit-code probe used by the `--global` hook guard: exit 0 (defer) when the repo has its own `--local` dummyindex hooks, else exit 1.

### `dummyindex context hooks uninstall [path] [--root DIR]`

- Removes the managed hook entries (and scrubs any legacy entries). Leaves the rest of `.git/hooks` and `settings.json` untouched.

### `dummyindex context hooks status [path] [--root DIR]`

- Prints whether each managed hook is installed and whether it points at the current binary. (`HookStatus` carries `claude_session_start`, `claude_stop`, `claude_pre_compact`, and `claude_pre_tool_use`; `all_installed` requires all four.)

## Onboarding & preflight

### `dummyindex context preflight [path] [--root DIR] [--json]`

- Read-only inventory of the repo's existing `.claude/` setup before any write:
  actionable for a Claude run and informational for a Codex-only run.
- The skill runs it as Phase 0 on every invocation and surfaces the summary.

### `dummyindex context onboard [path] [--root DIR] --model current|opus-4.8|sonnet-4.6|haiku-4.5 [--scope repo|subdir|explicit] [--scope-path PATH] [--mode light|standard|deep] [--hook|--no-hook] [--doc PATH]... [--platform claude|codex|both] [--defaults]`

- Persists the first-run council preferences (scope, mode, model, session hooks, external docs) to `.context/config.json`.
- The model is never silently defaulted — `--model` (or `--defaults`) is required.
- `--defaults` uses an explicit `--platform` when supplied. Otherwise it
  infers dummyindex's managed Claude/Codex guidance markers and preserves the
  historical Claude baseline only when neither marker exists.
- Driven by the skill's platform-aware Phase 1.2 setup. Claude-only asks five
  questions. Codex-only asks only portable preferences and passes
  `--model current --no-hook`. A both-host run uses `current` and asks for or
  retains the Claude hook preference; re-run via the active host's
  `--reconfigure` skill invocation.

### `dummyindex context config show [path] [--root DIR]`

- Prints `.context/config.json`; exit 1 when no config exists yet (the skill's "needs onboarding" signal).
- `get`/`set` are reserved for a future release.

## Enrichment (called by the council)

### `dummyindex context enrich-plan [path] [--root DIR]`

- Emits `.context/cache/_enrich_plan.json` — work-list of `tree.json` stubs.
- Grouped into per-file batches.
- Used by the dev to enrich tree abstracts.

### `dummyindex context enrich-apply [path] [--root DIR] --from-json FILE`

- Merges `{node_id: abstract}` into `tree.json` atomically.
- Bumps `confidence: EXTRACTED → INFERRED` on each touched node.
- Warns + exits non-zero on unknown `node_id`.

## Features

### `dummyindex context features-rename [--root DIR] --from ID --to ID [--name "..."] [--summary "..."]`

- Atomic feature folder rename.
- Updates: folder name, `feature.json`, every nested `flows/*.json`, `INDEX.json`, `INDEX.md`, `graph.json`.
- Used by the architect agent during the structural regrouping pre-stage.
- Idempotent: `--from == --to` just refreshes metadata.

### `dummyindex context features-merge [--root DIR] --from ID --into ID [--as-section NAME] [--note "..."]`

- Absorbs a trivial feature into another as a section (architect consolidation of dangling features).
- Appends — never clobbers — into `features/<into>/<section>.md`; updates `INDEX.json` and the graph.

### `dummyindex context flow-remove [--root DIR] --feature X --flow Y`

- Drops a flow's JSON + MD.
- Updates: `feature.json` (remove from `flow_ids`), `INDEX.json` (decrement `flow_count`), `graph.json` (remove flow node + edges).
- Used by the dev when filtering trivial/false-positive flows.

### `dummyindex context scaffold-feature [--root DIR] --id ID --name "..." [--summary "..."] --file PATH [--file PATH]...`

- Atomic, deterministic placement of net-new files into a **brand-new** feature the council decided should stand on its own — folds source into the curated taxonomy **without** re-clustering.
- Creates `features/<id>/`: `feature.json` (`members` derived from `map/symbols.json` for the given files, `entry_points`/`flow_ids` empty, `confidence: EXTRACTED`), a deterministic `spec.md` stub (the same writer the scaffolder uses), and `docs.md` when the source-docs catalog matches.
- Appends the feature to `INDEX.json` and regenerates `INDEX.md` + `graph.{json,html}` (reuses the index writers; never re-clusters, never invents `community-N`).
- Errors (exit 2) on a duplicate `--id`, a reserved `community-*` id, no `--file`, or a `--file` that isn't a real file under the repo. All validation runs before any write.
- The council reconciliation phase (Phase 3) calls this to place a net-new cluster reported as unassigned.

### `dummyindex context assign-files [--root DIR] --feature ID --file PATH [--file PATH]...`

- Atomic, deterministic placement of net-new files into an **existing** feature — `files` ∪ new, `members` recomputed from `map/symbols.json`.
- Updates that feature's `INDEX.json` counts and regenerates `INDEX.md` + `graph.{json,html}`.
- **Preserves** the feature's enriched `spec.md` / `plan.md` / `concerns.md` — they are never touched.
- Idempotent on already-assigned files (silently skipped, not an error). Errors (exit 2) on a missing feature, no `--file`, or a `--file` missing/outside the repo. All validation runs before any write.

### `dummyindex context unassign-files [--root DIR] --feature ID --file PATH [--file PATH]...`

- The **subtractive inverse** of `assign-files` — removes files from an existing feature (`files` minus the given set), recomputes `members` from `map/symbols.json` over what remains, refreshes INDEX counts + `INDEX.md`/`graph`, and re-drops the `.pending-enrichment` marker (the feature's scope changed → it owes re-enrichment).
- **Does not require the files to exist on disk** — the point is they were *deleted* (or moved to another feature). Idempotent on a path the feature doesn't own.
- Preserves the enriched `spec.md`/`plan.md`/`concerns.md`. Errors (exit 2) on a missing feature, no `--file`, a path outside the repo, or a removal that would empty the feature (use `features-remove` instead of stranding it).
- The reconcile procedure calls this for `removed_files` when a feature loses *some* of its files.

### `dummyindex context features-remove [--root DIR] --feature ID [--force]`

- Atomically **deletes a feature whose code is gone**: drops `features/<id>/` (folder + enriched docs + flows), its `INDEX.json` entry (regenerating `INDEX.md` and decrementing the top-level `flow_count`), and its node + edges from `graph.json`.
- **Safety guard:** refuses (exit 2) when the feature still owns files that exist on disk — those are live, so unassign the dead paths or merge it instead. `--force` overrides.
- The reconcile procedure calls this for `removed_files` when a feature loses *all* of its files. The standalone deletion `features-merge` only does as a side effect of merging into a target.

## Reconcile — commit-anchored update (v0.15.3)

The non-destructive successor to a full re-cluster. `.context/` records the commit it was last reconciled against (`meta.indexed_commit`); these commands diff against it and let the council update only what changed, preserving the curated taxonomy + enrichment. See `skills/council/65-reconcile.md` for the procedure.

### `dummyindex context reconcile [path] [--root DIR] [--json]`

- **Read-only.** Diffs `meta.indexed_commit`..HEAD (+ the working tree, incl. untracked) and reports: **drifted features** (own a changed/removed file), **removed files**, **unassigned new files** (owned by no feature), and **features awaiting enrichment** (carry a `.pending-enrichment` marker).
- `--json` emits the report `{indexed_commit, drifted_features, removed_files, unassigned_new_files, awaiting_enrichment, has_drift}` for the council procedure to consume.
- Never writes; never decides taxonomy. Empty report when there's no anchor (non-git, or a pre-v0.15.3 index).

### `dummyindex context mark-enriched [--root DIR] --feature ID`

- Clears a feature's `.pending-enrichment` marker once the council has (re-)enriched it. The marker is set by `scaffold-feature` / `assign-files`; while set, `reconcile-stamp` refuses to advance the anchor past that feature (so a place-then-restart can't orphan an un-enriched stub).
- Idempotent: no marker → no-op (exit 0). Errors (exit 2) only on a missing feature folder.

### `dummyindex context reconcile-stamp [path] [--root DIR] [--force]`

- **The write boundary.** Advances `meta.indexed_commit` to HEAD — run *after* the council has placed every unassigned file and enriched every placed/drifted feature. This is the one command (besides a fresh `ingest`) that moves the anchor.
- **Refuses (exit 1)** while any **unassigned new files** or **awaiting-enrichment features** remain — advancing past them would silently forget them. Does **not** block on drifted features (only the stamp clears drift, so blocking on it could never advance).
- `--force` anchors anyway and prints what it skipped. Warns when uncommitted source remains outside `.context/` (it re-surfaces as drift next reconcile). Off-git is a graceful no-op (exit 0).

## Council (called by skill procedures)

### `dummyindex context section-write [--root DIR] --feature X --section NAME --from-file PATH`

- Atomic placement of a markdown into `features/<X>/<NAME>.md`.
- Sections: `spec`, `plan`, `concerns` (v0.14). Legacy: `README`, `architecture`, `implementation`, `data-model`, `security`, `product` (pre-v0.14, accepted for backwards compatibility).
- Temp-file + rename for atomicity. Idempotent.
- Used by the dev at stage 1, the architect at stage 2, and the critics at stage 3.

### `dummyindex context council-log [--root DIR] --feature X --stage N --agent NAME --status STATE [--note "..."]`

- Appends to `features/<X>/council/_council-log.json`.
- Status values: `started`, `complete`, `failed`, `skipped`.
- Used by every persona at start and end of work.
- Enables resumption: skill checks the log to know what's already done.

### `dummyindex context council-batch [--root DIR] --next [--feature ID]... [--force] [--mode light|standard|deep] [--cap N] [--tree-enrich] [--json]`

- Returns the next parallel batch of council dispatch-units: the earliest incomplete stage across all non-trivial features, up to `--cap` agents.
- `--feature ID` (repeatable) scopes the frontier to those features; `--force` re-councils already-complete scoped features (requires `--feature`).
- `--json` emits `{complete, stage, mode, cap, units[]}` — each unit carries `feature_id`, `stage`, `role`, `subagent_type`, `framework`.
- When `complete` is `true`, all features have finished every active stage for the given mode.
- The council twin of `build --next-wave`; the skill fans units out to parallel Task subagents, barriers, then re-runs `--next`.

### `dummyindex context conventions-write [--root DIR] --section NAME --from-file PATH`

- Atomic markdown placement into `.context/conventions/<section>.md` (agent-authored docs: folder-organization, coding-practices, testing, data-access).
- The Phase 1.5 convention authors place their output through this.

### `dummyindex context reality-check [--root DIR] --feature ID [--demote] [--json]`

- Post-synthesis fact-check (Phase 3.5): pulls concrete claims ("X calls Y", `file.py:42`) out of a feature's docs and verifies them against `map/symbols.json` + the symbol graph.
- `--demote` flips the feature's confidence to `AMBIGUOUS` when claims contradict the AST.

### `dummyindex context dev-pick [path] [--root DIR] --feature ID`

- Resolves which stack-specialist "dev" persona authors a feature's docs — first-match-wins over the feature's file list + dependency tokens.
- Prints JSON (`persona_id`, `subagent_type`, `framework`, `fallbacks`) — deterministic, no LLM.

## Refresh

### `dummyindex context refresh-indexes [path] [--root DIR]`

- Rebuilds `.context/INDEX.md` from disk.
- Rebuilds `features/INDEX.md` from `features/INDEX.json`.
- Rebuilds `features/graph.json` + `features/graph.html` from the per-feature data.
- Use after enrichment + renames to reconcile derived artifacts.
- **Also migrates** legacy layouts (moves `graph/` contents under `features/`, shrinks long CLAUDE.md blocks).

## Retrieval CLI

### `dummyindex context query "..." [--root DIR] [--top-k N] [--budget N] [--json]` ✅ shipped (v0.12)

- PageIndex-style tree search. Agent passes a natural-language question.
- Walks `features/INDEX.json` → relevant feature → relevant section.
- Returns the cited markdown + `path:range` references.
- Budget-capped (default 2000 tokens) for predictable cost in agent loops.
- Deterministic — no LLM in the loop; a view over the same JSON the agent walks manually.

### `dummyindex context debt [path] [--root DIR] [--write] [--json]`

- Technical-debt ledger over the repo's **Python** source: a per-file, path-sorted, repo-relative list of `# TODO:` / `# FIXME:` / `# HACK:` / `# DEBT:` markers.
- Each row is tagged with its declared upgrade trigger (`# DEBT: <ceiling>; upgrade: <trigger>`) or `no-trigger`; the body ends with the `N markers, M with no trigger.` tally.
- Prints to stdout by default; `--write` also persists `.context/debt.md`; `--json` emits the stable `DebtLedger` structure.
- Deterministic — no LLM; re-running on an unchanged tree is byte-identical. Rows are always repo-relative (no absolute path ever leaks).

## Session memory (v0.15)

### `dummyindex context memory session-start|roll|init [path] [--root DIR]`

- `session-start` — emits the SessionStart block (HANDOFF + MEMORY) into the session's `additionalContext`; silent if the `remember` plugin's `.remember/` is present (suppresses double-inject). Called by the hook folded into the existing sentinel entry.
- `roll` — relocates dated entries down the tiers: `now.md` → `recent.md` → `archive.md`, idempotent.
- `init` — creates the session-memory store stubs at `.context/session-memory/` if absent.
- Seeded by `ingest`; never regenerated; invisible to drift detection.

### `dummyindex context memory nudge [path] [--root DIR]`

- The **Stop**-hook command. Reads the hook's stdin JSON (`transcript_path`,
  `session_id`). When the session is significant (subagents used, or ≥40k
  main-thread output tokens) and not already nudged / not already saved /
  no `remember` plugin, prints a `hookSpecificOutput.additionalContext`
  payload that prompts the agent to offer a handoff CTA. Otherwise silent.
  Never auto-saves; never fails the turn.

### `dummyindex context memory breadcrumb [path] [--root DIR]`

- The **PreCompact**-hook command. Writes a deterministic, tagged breadcrumb
  entry (branch, `git diff --stat`, file list, subagent + turn counts) to the
  top of `now.md` so a session is never lost to compaction. Silent when the
  `remember` plugin is present. Never stamps the commit anchor.

## Build loop (v0.15)

The `context equip ...` commands in this section are the deterministic backend
for the **Claude Code** equipment workflow. Codex plan/build/equip skills do not
invoke them: `$dummyindex-equip` reports native routes without writing, and
`$dummyindex-build` uses built-in `worker`/`explorer`/`default` without requiring
`.context/equipment.json`.

### `dummyindex context propose --slug S --title "..." [--root DIR] [--force]`

- Build loop — grounded planning. Scaffolds `.context/proposals/<slug>/` (`proposal.json` + `spec.md` / `plan.md` / `checklist.md`).
- Runs a deterministic consistency scan (reuses `query`, no LLM) and records related features + conventions in `proposal.json` and a `## Consistency` block in `spec.md`.
- `--force` overwrites an existing proposal.
- Why: gives `/dummyindex-plan` a structured, index-grounded scaffold to fill rather than drafting into the void.

### `dummyindex context equip apply [path] [--root DIR] [--dry-run] [--for-proposal S] [--specialist C] [--json]`

- Build loop — render the project-tuned toolkit into `.claude/` from `.context/` + preflight data; records in `.context/equipment.json` (schema v4).
- **`apply` is an explicit verb.** A bare `dummyindex context equip` (no verb, no flags) is a help probe: it prints usage and **exits 2 without writing** — a discovery probe never mutates the repo. The only verbless form is the read-only `equip --dry-run` preview. `apply` also **refuses** (`exit 1`) on a repo with no `.context/` (equip renders *from* the index — run `dummyindex ingest` first).
- Generates: `<stack>-implementer` + `<stack>-tester` agent, `<proj>-reviewer` agent, `<proj>-verify` skill; wires the detected formatter's PostToolUse hook into `settings.json` under `DUMMYINDEX_EQUIP` sentinel.
- **Generated vs adopted.** A capability a template backs (**db / security / performance / docs / search**) is *generated* as a real, file-backed `<proj>-<cap>-specialist.md` (marker + `version`/`origin_hash`/`grounded_in`, lifecycle-managed like the core four). A capability with **no** template (e.g. frontend → *Frontend Developer*) is *adopted* manifest-only (`path: ""`, no file written).
- `--for-proposal S` covers the capabilities `S`'s `plan.md`/`checklist.md` demand (generating or adopting per the rule above; RLS / tenant-isolation map to `security`). `--specialist C` also generates capability `C`. Already-applied specialists are carried forward, so a plain re-apply never drops one.
- **Seeds a starter eval suite** per generated tool — a schema-valid placeholder `.context/equipment-evals/<tool>.suite.json` (never-clobber), giving `equip eval` something to grade.
- `--dry-run` writes nothing; additive + never-clobber on real runs.

### `dummyindex context equip add-specialist CAPABILITY [--root DIR] [--dry-run] [--json]`

- Generate one grounded specialist on demand (`db | security | performance | docs | search`) as a `<proj>-CAPABILITY-specialist` agent, on top of the existing toolkit. Idempotent + additive (a later plain `equip` preserves it).
- An unknown `CAPABILITY` (no template — e.g. `frontend`) exits `2` with the valid list; that capability is covered by manifest-only adoption on a `--for-proposal` run instead.
- The flag form is `dummyindex context equip apply --specialist CAPABILITY`.

### `dummyindex context equip discover [QUERY] [--repo OWNER/NAME] [--root DIR] [--json]`

- **Plugin manager (dry-run).** Fetch the seed marketplaces' `marketplace.json` (and, for a `QUERY`, GitHub code search) and print a ranked plan. With no `QUERY`, auto-matches the detected stack's capabilities; with one, ranks by query + capability overlap.
- `--repo OWNER/NAME` (also accepts a full GitHub URL) adds one extra collection repo to the search universe beyond the seed marketplaces — for a low-profile repo the marketplaces don't list.
- Each candidate shows its **blast radius**: the surfaces it declares (`hook` / `mcp` / `lsp` / `bin` run code; `agent` / `skill` / `command` are inert) and its trust tier (Anthropic-official = trusted). Writes nothing. Requires `gh` (warns + degrades when absent).

### `dummyindex context equip install <plugin>@<marketplace> [--yes] [--scope project|local|user] [--repo OWNER/NAME] [--usage-doc PATH|--skip-usage-doc] [--root DIR]`

- Install one approved plugin, in one of **two mechanisms** decided by the install plan:
  - **Native wiring** (a marketplace plugin): add it to `extraKnownMarketplaces` + `enabledPlugins` in `.claude/settings.json` (scope `project` by default — `local` → `settings.local.json`, `user` → `~/.claude/settings.json`), and record a `MARKETPLACE` item in the manifest.
  - **Vendor** (a loose-collection skill, `InstallMechanism.VENDOR`): resolve the source repo's HEAD to a **pinned commit sha**, fetch that skill's `SKILL.md` at the sha, stamp it, and copy it to `.claude/skills/<name>/SKILL.md` — no settings wiring. Records a `VENDORED` manifest item carrying the pinned ref. Never-clobber: an absent target or a prior dummyindex-vendored copy is (re-)written; a user file (or a hand-edited vendored copy that has gone USER_MODIFIED) is refused (`exit 1`) — `equip uninstall` first to re-vendor.
- A code-running plugin from an **untrusted** source is refused (`exit 1`) without `--yes`. Settings writes are preserve-or-refuse + atomic.
- **Usage playbook is mandatory:** pass exactly one of `--usage-doc <path>` (recorded in the item's `grounded_in`; a repo-relative path travels with the committed manifest, an out-of-repo absolute one is kept with a warning) or `--skip-usage-doc` to opt out. Neither, or both, is a usage error (`exit 2`) — the `/dummyindex-equip` council writes the playbook.
- `--repo OWNER/NAME` (or a full GitHub URL) names an extra collection repo to resolve the target from, when it isn't in the seed marketplaces.

### `dummyindex context equip status [--root DIR] [--json]`

- Classify every tracked item: generated + vendored by origin-hash (`pristine` / `user-modified` / `missing`), and marketplace items by whether their `enabledPlugins` key is still set (`pristine` = enabled, `missing` = not), with each item's version.
- Also flags each lifecycle-managed tool with no eval result yet as `unevaluated` (`StatusReport.unevaluated`) — prompting an `equip eval` run.

### `dummyindex context equip refresh [--root DIR] [--dry-run]`

- Re-render PRISTINE-and-stale items, re-baseline + minor-bump. USER_MODIFIED items are skipped forever.

### `dummyindex context equip reset NAME [--root DIR]`

- Restore one generated item to its pristine render (the escape hatch), re-baseline + bump.

### `dummyindex context equip uninstall [--root DIR] [--dry-run]`

- Remove PRISTINE generated files + the `DUMMYINDEX_EQUIP` hook + the manifest; USER_MODIFIED files are kept and reported. Also disables any equip-enabled plugins (and drops their marketplaces) from `settings.json`, and removes PRISTINE vendored files (user-edited vendored copies are kept).

### `dummyindex context equip patch --item NAME --from-file F [--root DIR]`

- Sanctioned evolution: apply an exact-once old→new patch (`F` is `{"old": "...", "new": "..."}`) to a generated item, re-baseline + patch-version bump.
- Why: lets build-run learnings flow back into generated tooling (`dummyindex-build` calls this post-build) without stomping user edits.

### `dummyindex context equip remove NAME [--root DIR] [--delete-file] [--keep-wiring]`

- Drop one item from the manifest and unwire it from `settings.json`. `--delete-file` also removes a PRISTINE generated/vendored file from disk (USER_MODIFIED is kept); `--keep-wiring` leaves the settings entry in place.

### `dummyindex context equip verify <plugin>@<marketplace> [--root DIR]`

- Read-only supply-chain check: re-resolve an installed plugin against its upstream and report whether the pinned commit sha still matches. Writes nothing.

### `dummyindex context equip eval <tool> --observations FILE [--suite FILE] [--run-label L] [--force] [--root DIR] [--json]`

- Score a generated/vendored tool's trigger-description suite (`.context/equipment-evals/<tool>.suite.json`) against a file of observed firing decisions, into precision / recall / accuracy. Writes `<tool>.result.json` (or `<tool>.run-<L>.result.json` with `--run-label`) and prints each misfire's `case_id` + outcome. Exit `2` = bad flags / unsafe tool name / missing suite / `--run-label` collision (pass `--force`); `1` = malformed suite or observations content; `0` = scored. The trigger judgments are produced by the `/dummyindex-equip` skill (LLM, out of code) and fed in as data.

### `dummyindex context equip benchmark <tool> [--root DIR] [--json]`

- Aggregate the repeated `<tool>.run-*.result.json` runs into a `<tool>.benchmark.json` report — mean accuracy, population variance, and the flaky `case_id`s (outcome not identical across runs). A **reporter, not a gate**: a missing evals dir or zero run files warns and exits `0` writing nothing; only a malformed run file fails loud (exit `1`).

### `dummyindex context build --proposal S (--next-wave | --next | --check "<item>" | --skip "<item>" --reason "<why>" | --status) [--json]`

- Build loop — deterministic state machine over a proposal's `checklist.md`. The `/dummyindex-build` skill orchestrates dispatch; this command drives the state.
- `checklist.md` may group items under `## Wave N — label` (or `## Group N`) headings: items in one wave are mutually independent and may be dispatched **in parallel**; waves run strictly in order. Any other heading (a plain title) keeps items serial, so legacy flat checklists are unchanged.
- `--next-wave` prints **every** unchecked item in the earliest incomplete wave
  with compatibility routing metadata and shared grounding paths. The active
  skill dispatches the wave through its host: Claude uses the equipment mapping;
  Codex maps by task to native built-ins.
- `--next` prints one item with the same metadata. Both verbs report an
  **`equipped`** flag (`--json`) and warn in text mode when no manifest exists.
  Claude's build skill stops on that signal; Codex treats it as the expected
  no-equipment state and continues natively.
- `--check "<item>"` flips an item to `- [x]`, idempotent — one call per verified item.
- `--skip "<item>" --reason "<why>"` closes an item as `- [~] … — skipped: <why>` (renegotiated scope); `--reason` is mandatory and an already-closed box is refused.
- `--status` reports `done/total`; when complete, prints `dummyindex context reconcile`.

## Managed doc homes — migrate strays + write-guard

Keep internal planning artifacts (plans / specs / design docs / audits) in their managed `.context/` homes (`proposals/<slug>/`, `audits/<slug>/`) instead of leaking into the user-facing `docs/` tree. One shared, location-gated classifier backs both a relocation command and a PreToolUse write-guard.

### `dummyindex context migrate-docs [--root DIR] [--yes] [--force] [--json]`

- Relocates stray planning-doc markdown that leaked under `docs/` (a `plans|specs|proposals|audits` segment — incl. `docs/internal/*` and `docs/superpowers/{plans,specs}` — or a `*-design.md` / `YYYY-MM-DD-<name>.md` filename under such a dir) into its managed home: `.context/proposals/<slug>/` (`spec.md`/`plan.md`) or `.context/audits/<slug>/` (`report.md`), minting a valid `proposal.json` (terminal status `done`, no template checklist so the GC won't read it as in-flight).
- Dry-run by default — lists every stray grouped by slug + target home in deterministic sorted order and moves nothing. `--yes` performs the moves; `--force` fills only *missing* files in an existing home (never clobbers a non-empty `spec.md`/`plan.md`/`proposal.json`); `--json` emits the stable `{dry_run, groups, skipped}` payload.
- Preserves git history: a tracked stray moves via `git mv` (rename in the index), an untracked one via `Path.replace` + `git add`, a non-git tree via `Path.replace` only. Transactional — the whole plan is realpath-validated (no `..`/symlink escape) before any move executes. Never touches source code or moves outside `docs/`. See the `playbooks/migrate-stray-docs.md` playbook (commit the move alone so `git log --follow` survives).

### `dummyindex context guard-doc-write [--root DIR]`

- The **PreToolUse `Write` guard** (reads the hook JSON on stdin). Denies a `Write` that would create an internal planning doc in an unmanaged location, with an interpolated reason naming the `.context/` home it belongs in; allows everything else.
- **Fail-open**: exits 0 on every path except an explicit JSON `deny` — malformed/empty stdin, a non-`Write` tool (`Edit`/`MultiEdit` can only maintain an existing file, never create a fresh leak), a missing or out-of-repo `file_path`, or any internal error all allow. It **never** `exit 2` (which would block the tool) and runs no git/subprocess on the hot path.
- Config-gated by `doc_guard_enabled` (default on everywhere, engages even before `.context/` exists); a `doc_guard_allow` glob (e.g. `docs/specs/**`) exempts a legitimately-published path. Wired as a managed PreToolUse hook by `hooks install`.

## Audit — argue-and-audit panel (`/dummyindex-audit` / `$dummyindex-audit`)

On-demand adversarial review: a free-text description spins up a
**task-dependent** panel of auditors that file findings, then argue them (up to
3 rebuttal rounds, stopping early on agreement) before synthesis writes a ranked
`report.md`. The CLI is deterministic plumbing; the active-host audit skill
orchestrates Claude Task subagents or Codex native `explorer`/`default`
subagents. It does **not** require a full `.context/` index.

### `dummyindex context audit start --describe "..." [--scope PATH]... [--mode light|standard|deep] [--model current|opus-4.8|sonnet-4.6|haiku-4.5] [--slug S] [--force] [--root DIR] [--json]`

- Scaffolds `.context/audits/<slug>/` (`audit.json`, `description.md`, `catalog.json`, `findings/`) and emits the persona catalog as JSON (`{slug, dir, mode, model, max_rounds, scope, catalog:[...]}`).
- `--describe` is required. `--slug` defaults to a slug derived from the description; `--force` overwrites an existing audit.
- `--model` is required unless config provides one. Claude uses a configured or
  user-selected Claude label. Codex passes `--model current` explicitly, even
  when a shared config contains a Claude label. `--mode` defaults to config,
  else `standard`.
- `--scope PATH` (repeatable) focuses the audit on specific paths.

### `dummyindex context audit show --slug S [--root DIR] [--json]`

- Reports an audit's state: its config, which rebuttal rounds are complete, and whether `report.md` has been written.

### `dummyindex context audit-log --slug S --round N --persona P --status STATE [--note "..."] [--root DIR]`

- Appends a row to `audits/<slug>/_debate-log.json` for debate resumption. `STATE` is `started|complete|failed|skipped`. The skill logs each persona per round so a re-run skips completed rounds.

## Context-hygiene GC (`/dummyindex-gc` / `$dummyindex-gc`)

Deterministic plumbing for the commit-throttled hygiene sweep. Generated docs are GC'd (deleted), never archived; `/dummyindex-gc` on Claude or `$dummyindex-gc` on Codex drives the council judgment + user confirmation, while these verbs are the bounded Python.

### `dummyindex context gc status [--json] [--root DIR]`

- Read-only sweep: every candidate generated-doc workspace under `proposals/` + `audits/` with its deterministic signals (`status:<v>`, `orphan-empty`, `checklist-complete`/`checklist-partial`, `report-written`, `untracked`, `age-<n>d`), plus the commit-throttle state (`commits_since`, `anchor`, `threshold`, `should_signal`, `anchor_orphaned`). `--json` emits the same payload. Surfaces a re-baseline hint when the recorded anchor is orphaned by a history rewrite. Exit 0.

### `dummyindex context gc delete --kind proposal|audit (--slug S | --path P) [--yes] [--allow-untracked] [--force-partial] [--root DIR]`

- Removes exactly one doc workspace dir, behind a guard ladder (slug-charset → sentinel-reject → realpath-containment → liveness → recoverability). Without `--yes` it is a dry-run that deletes nothing (exit 0); with `--yes` it performs the bounded delete. Refuses a sentinel (`_archive`, leading-`_`), an out-of-charset slug, or an escaping `--path` (exit 2), and an untracked workspace without `--allow-untracked`. An already-absent target is an exit-0 no-op. Never deletes source code.

### `dummyindex context gc stamp [--to <sha>] [--root DIR]`

- Advances the committed GC commit anchor in `.context/gc/state.json` to HEAD (or `--to <sha>`), resetting the commit-throttle counter. Off-git is a no-op.

### `dummyindex context gc signal [--json] [--root DIR]`

- The SessionStart throttle probe: prints the one-line nudge (`N commits since last hygiene sweep — run /dummyindex-gc`) iff `commits_since(anchor) >= threshold` and it has not already signalled this session (resolved from `CLAUDE_CODE_SESSION_ID`). Always exit 0; silent under threshold / off-git / already-signalled.

## Doc reorg (opt-in, destructive — `/dummyindex --reorg-docs`)

### `dummyindex context doc-reorg guard|list|backup|restore [path] [--root DIR] [--json] [--from DIR]`

- Safety net for the destructive in-place doc reorg; the rewrites themselves happen in the session via `Edit` with per-file confirm.
- `guard` — exit 0 if the working tree is clean, else 1 (the hard gate).
- `list` — the doc files in scope. `backup` — copy them to a timestamped backup dir. `restore --from <dir>` — put a backup back.

## Token usage

### `dummyindex usage [chat|daily|session|monthly|blocks]`

- Reads Claude Code transcripts to report token usage. No LLM cost.
- It is not a Codex session reporter. In Codex use native `/status` for the
  current context/session and `/usage` for account usage.
- `chat` (default) — the current session: context window now (main thread, matches `/context`) plus deduplicated cumulative totals, with a subagents column summing any Task/subagent transcripts. This is what the `/tokens` slash command runs.
- `daily` / `session` / `monthly` — token totals aggregated across every project, grouped by day / session / month.
- `blocks` — usage grouped into billing blocks across every project.

## Status — read-only overview

### `dummyindex context status [path] [--root DIR] [--json]`

- A single read-only glance, composed from the existing per-domain read helpers — it **never mutates**. Also available as the top-level alias `dummyindex status` (the spelling models reach for first).
- Reports: whether `.context/` is present and enriched; the `.context` version stamp vs the running CLI (flags skew); the commit-anchored drift one-liner (drifted / unassigned / awaiting-enrichment / removed); the equipment item count + schema version; each proposal's `done/total`; and session-memory presence.
- Exits `0` even on an un-indexed repo (it reports "not initialized" rather than erroring), so it is safe to run anywhere.

### `dummyindex context wire [path] [--root DIR] [--yes]`

- The **interactive escalation surface** for the `wired` config list. Where the headless reconciler (`install`/`ingest`) only **classifies and reports** needs-user entries, `wire` actually resolves them — by prompting.
- Re-classifies every `config.wired` entry **read-only** with the same shared helper `status` uses (satisfied / acted / needs-user), then resolves each entry that is not already satisfied: every declared-but-absent wireable plugin (the *acted* class) is **prompted** before wiring; a `kind: skill` entry is surfaced as a manual notice and **never** auto-wired (no skill-enable primitive exists); a malformed plugin target is reported and skipped.
- `--yes` auto-affirms every plugin prompt (the automation path, no `input` call). A non-TTY stdin without `--yes` never blocks — it prints the needs-user list and exits `0`. The headless reconciler stays non-interactive; this is the **only** surface that prompts.

### `dummyindex context statusline [path] [--root DIR]`

- Prints the cached `.context/` freshness badge (`[ctx ✓]` / `[ctx: N drift]`) for a shell `statusLine` — the **cold-path** fallback for the per-prompt hot path (the shipped `statusline.sh` / `statusline.ps1` `cat` the same gitignored cache directly).
- Reads the pre-computed badge cache written by the `plan-update` SessionStart path — it **never recomputes drift**.
- A missing `.context/`, a missing or malformed cache, or **any** error collapses to empty stdout and `exit 0`, so it can never crash a user's shell.

## What is NOT a CLI command

- "Run the council" — that's the **skill's** job. The CLI doesn't dispatch agents.
- "Enrich PROJECT.md" — that's a markdown procedure; the agent uses `Write`.
- "Decide if a flow is trivial" — that's the dev agent's call.

Rule of thumb: the CLI moves bytes around atomically. Everything that requires judgment is in markdown.

And the human never runs it: the CLI is the agent's deterministic backbone,
invoked by the skill and council. A human's interface is slash commands inside
Claude Code or `$skill` mentions in Codex — plus the one-time `install`
bootstrap.
