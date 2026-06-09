# 07 — CLI surface

Every command. What it does. Why it exists.

> **The CLI is the agent's backbone — you don't run it by hand.** The skill and
> council invoke these commands to move bytes around atomically; everything that
> needs judgment stays in markdown (see [the closing rule](#what-is-not-a-cli-command)).
> A human's entire interface is the **slash commands** inside Claude Code. The lone
> exception is the one-time **Installation** bootstrap below — `pip install dummyindex`
> + `dummyindex install` — which a human runs in a terminal to put the skill in place.

## Installation — the human bootstrap (run once)

The one place a human touches the terminal. Every section after this is agent-invoked.

### `dummyindex install [--scope user|project] [--dir PATH] [--skill-only]`

- Copies the skill into Claude Code's skills directory.
- `--scope user` (default) → `~/.claude/skills/dummyindex/SKILL.md`.
- `--scope project` → `<PATH>/.claude/skills/dummyindex/SKILL.md`.
- Registers the skill in the chosen `CLAUDE.md` so `/dummyindex` is recognized.
- **Auto-init** (v0.13.4): when the resolved project candidate (`--dir`, else CWD) is a git repo, `install` also runs the full project init — builds `.context/`, writes the managed `CLAUDE.md` block, and installs the managed session hooks. Pass `--skill-only` to suppress this and copy the skill alone. A non-git candidate prints a one-line "skipped project init" note.
- **Installs three Claude hooks** as part of auto-init — SessionStart (`dummyindex context plan-update`, drift report), Stop (`dummyindex context memory nudge`), and PreCompact (`dummyindex context memory breadcrumb`). None rebuild the index (unlike the legacy pre-v0.13.5 shell-rebuild hooks).

### `dummyindex uninstall [--scope user|project] [--dir PATH]`

- Removes the skill and the version stamp.
- Removes the hooks installed at `--scope project`.
- Best-effort cleanup of now-empty parent directories.

## Backbone

### `dummyindex ingest [path] [--root DIR] [--no-hooks] [--docs PATH]...`

- Primary entry point. Equivalent to `context init`.
- Runs the deterministic backbone on `path`.
- Writes `.context/` and a 3-line managed block in `<root>/CLAUDE.md`.
- **Installs hooks** by default; pass `--no-hooks` to skip.
- Smart default: relative `path` under cwd → output to cwd; absolute path → output to that path.
- `--docs PATH` (repeatable) — adds external doc folders to the source-docs catalog. In-repo docs (`README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `SECURITY.md`, `BRIEF.md`, any root-level `*.md`, plus `docs/`, `doc/`, `documentation/`, `ADR/`, `RFC/`) are discovered automatically.

### `dummyindex context init [path] [--root DIR] [--no-hooks] [--docs PATH]...`

- Same as `ingest`.

### `dummyindex context rebuild [--changed] [--full] [path] [--root DIR] [--docs PATH]...`

- Full or incremental rebuild.
- `--changed` re-extracts only files whose content hash changed (the manual incremental path). The manifest tracks both code and in-repo docs, so a README edit is detected. As of v0.13.5 this is run manually, not from a hook.
- **Non-destructive on an enriched index.** When `features/INDEX.json` carries a curated taxonomy (a feature renamed off `community-*`, or an `INFERRED` confidence), `--changed` no longer re-clusters or re-stubs. It refreshes only the deterministic, enrichment-free artefacts (`map/files.json`, `map/symbols.json`, `conventions/naming.{json,md}`, `source-docs/INDEX.{json,md}`, `features/symbol-graph.json`), preserves `tree.json` abstracts and every per-feature `spec.md`, prints a reconcile report (drifted features + unassigned new files), and advances `meta.indexed_commit` to HEAD. A fresh deterministic-only index (all `community-*` / `EXTRACTED`) still full-builds.
- `--full` forces the destructive full re-cluster regardless, printing a warning that it discards any curated taxonomy + enrichment. Use after an intentional from-scratch reset; otherwise prefer the default non-destructive path.
- `--docs PATH` accepts the same form as `ingest`. Pass it on every rebuild that should preserve the same external doc roots.
- Outputs `added / modified / removed` summary (or the reconcile report on the enriched path).

### `dummyindex context check [path] [--root DIR] [--auto-refresh] [--quiet] [--docs PATH]...`

- Manifest-based drift detection. Compares current source + doc content hashes to the stored manifest; reports `added / modified / removed`.
- `--auto-refresh` runs `rebuild --changed` automatically when drift is detected.
- `--quiet` suppresses output unless drift exists.
- `--docs PATH` mirrors `ingest` so external doc roots aren't reported as `removed`.
- A manual inspection command. **No longer auto-refreshes** and is **not** the SessionStart hook (that's `plan-update`, below).

### `dummyindex context plan-update [path] [--root DIR]`

- The SessionStart-hook command (v0.13.5).
- Prints a markdown drift report to stdout: one line per feature whose source-file mtime exceeds the max mtime of that feature's docs. Empty stdout when nothing is stale.
- Claude Code's `SessionStart` hook takes the plain stdout as `additionalContext` — no JSON wrapping.
- Advisory only: it does not rebuild or rewrite anything. The running session reconciles the named features' docs in place.

### `dummyindex context bootstrap [path] [--root DIR]`

- Regenerates only the managed block in `CLAUDE.md`.
- Useful when the block text changes (e.g., schema bumps).

## Hooks (installed by `ingest` or `install --scope project`)

### `dummyindex context hooks install [path] [--root DIR]`

- Idempotent. Installs **three** `.claude/settings.json` hooks, none of which rebuild the index:
  - SessionStart — runs `dummyindex context plan-update` (drift report).
  - Stop — runs `dummyindex context memory nudge` (handoff-checkpoint CTA).
  - PreCompact — runs `dummyindex context memory breadcrumb` (writes a breadcrumb to `now.md`).
- **Upgrade scrub**: removes any legacy `git post-commit` script and sentinel-bearing `PostToolUse` entry installed by pre-v0.13.5 versions. User-authored hooks (no sentinel) are left untouched.

### `dummyindex context hooks uninstall [path] [--root DIR]`

- Removes the three managed hooks (and scrubs any legacy entries). Leaves the rest of `.git/hooks` and `settings.json` untouched.

### `dummyindex context hooks status [path] [--root DIR]`

- Prints whether each managed hook is installed and whether it points at the current binary. (`HookStatus` carries `claude_session_start`, `claude_stop`, and `claude_pre_compact`; `all_installed` requires all three.)

## Onboarding & preflight

### `dummyindex context preflight [path] [--root DIR] [--json]`

- Read-only inventory of the repo's existing `.claude/` setup before any write: `settings.json` validity + user hooks, `.claude/rules/`, project agents, CLAUDE.md managed-block state, git-clean status.
- The skill runs it as Phase 0 on every invocation and surfaces the summary.

### `dummyindex context onboard [path] [--root DIR] --model opus-4.7|sonnet-4.6|haiku-4.5 [--scope repo|subdir|explicit] [--scope-path PATH] [--mode light|standard|deep] [--hook|--no-hook] [--doc PATH]... [--defaults]`

- Persists the first-run council preferences (scope, mode, model, session hooks, external docs) to `.context/config.json`.
- The model is never silently defaulted — `--model` (or `--defaults`) is required.
- Driven by the skill's Phase 1.2 five-question setup; re-run via `/dummyindex --reconfigure`.

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

### `dummyindex context propose --slug S --title "..." [--root DIR] [--force]`

- Build loop — grounded planning. Scaffolds `.context/proposals/<slug>/` (`proposal.json` + `spec.md` / `plan.md` / `checklist.md`).
- Runs a deterministic consistency scan (reuses `query`, no LLM) and records related features + conventions in `proposal.json` and a `## Consistency` block in `spec.md`.
- `--force` overwrites an existing proposal.
- Why: gives `/dummyindex-plan` a structured, index-grounded scaffold to fill rather than drafting into the void.

### `dummyindex context equip [apply] [path] [--root DIR] [--dry-run] [--for-proposal S] [--specialist C] [--json]`

- Build loop — render the project-tuned toolkit into `.claude/` from `.context/` + preflight data; records in `.context/equipment.json` (schema v3).
- Generates: `<stack>-implementer` + `<stack>-tester` agent, `<proj>-reviewer` agent, `<proj>-verify` skill; wires the detected formatter's PostToolUse hook into `settings.json` under `DUMMYINDEX_EQUIP` sentinel.
- **Generated vs adopted.** A capability a template backs (**db / security / performance / docs / search**) is *generated* as a real, file-backed `<proj>-<cap>-specialist.md` (marker + `version`/`origin_hash`/`grounded_in`, lifecycle-managed like the core four). A capability with **no** template (e.g. frontend → *Frontend Developer*) is *adopted* manifest-only (`path: ""`, no file written).
- `--for-proposal S` covers the capabilities `S`'s `plan.md`/`checklist.md` demand (generating or adopting per the rule above; RLS / tenant-isolation map to `security`). `--specialist C` also generates capability `C`. Already-applied specialists are carried forward, so a plain re-apply never drops one.
- `--dry-run` writes nothing; additive + never-clobber on real runs.

### `dummyindex context equip add-specialist CAPABILITY [--root DIR] [--dry-run] [--json]`

- Generate one grounded specialist on demand (`db | security | performance | docs | search`) as a `<proj>-CAPABILITY-specialist` agent, on top of the existing toolkit. Idempotent + additive (a later plain `equip` preserves it).
- An unknown `CAPABILITY` (no template — e.g. `frontend`) exits `2` with the valid list; that capability is covered by manifest-only adoption on a `--for-proposal` run instead.

### `dummyindex context equip discover [QUERY] [--root DIR] [--json]`

- **Plugin manager (dry-run).** Fetch the seed marketplaces' `marketplace.json` (and, for a `QUERY`, GitHub code search) and print a ranked plan. With no `QUERY`, auto-matches the detected stack's capabilities; with one, ranks by query + capability overlap.
- Each candidate shows its **blast radius**: the surfaces it declares (`hook` / `mcp` / `lsp` / `bin` run code; `agent` / `skill` / `command` are inert) and its trust tier (Anthropic-official = trusted). Writes nothing. Requires `gh` (warns + degrades when absent).

### `dummyindex context equip install <plugin>@<marketplace> [--yes] [--scope project|local|user] [--root DIR]`

- Wire one approved plugin **natively**: add it to `extraKnownMarketplaces` + `enabledPlugins` in `.claude/settings.json` (scope `project` by default — `local` → `settings.local.json`, `user` → `~/.claude/settings.json`), and record a `MARKETPLACE` item in the manifest.
- A code-running plugin from an **untrusted** source is refused (`exit 1`) without `--yes`. Settings writes are preserve-or-refuse + atomic.

### `dummyindex context equip status [--root DIR] [--json]`

- Classify every tracked item: generated + vendored by origin-hash (`pristine` / `user-modified` / `missing`), and marketplace items by whether their `enabledPlugins` key is still set (`pristine` = enabled, `missing` = not), with each item's version.

### `dummyindex context equip refresh [--root DIR] [--dry-run]`

- Re-render PRISTINE-and-stale items, re-baseline + minor-bump. USER_MODIFIED items are skipped forever.

### `dummyindex context equip reset NAME [--root DIR]`

- Restore one generated item to its pristine render (the escape hatch), re-baseline + bump.

### `dummyindex context equip uninstall [--root DIR] [--dry-run]`

- Remove PRISTINE generated files + the `DUMMYINDEX_EQUIP` hook + the manifest; USER_MODIFIED files are kept and reported. Also disables any equip-enabled plugins (and drops their marketplaces) from `settings.json`, and removes PRISTINE vendored files (user-edited vendored copies are kept).

### `dummyindex context equip patch --item NAME --from-file F [--root DIR]`

- Sanctioned evolution: apply an exact-once old→new patch (`F` is `{"old": "...", "new": "..."}`) to a generated item, re-baseline + patch-version bump.
- Why: lets build-run learnings flow back into generated tooling (`dummyindex-build` calls this post-build) without stomping user edits.

### `dummyindex context build --proposal S (--next-wave | --next | --check "<item>" | --status) [--json]`

- Build loop — deterministic state machine over a proposal's `checklist.md`. The `/dummyindex-build` skill orchestrates dispatch; this command drives the state.
- `checklist.md` may group items under `## Wave N — label` (or `## Group N`) headings: items in one wave are mutually independent and may be dispatched **in parallel**; waves run strictly in order. Any other heading (a plain title) keeps items serial, so legacy flat checklists are unchanged.
- `--next-wave` prints **every** unchecked item in the earliest incomplete wave — each with its mapped equipment agent + `subagent_type` (per-item `general-purpose` fallback) — plus the shared grounding paths. On a flat checklist this is exactly one item. This is the loop's driver; the skill dispatches the whole wave concurrently via parallel Task calls.
- `--next` prints the single first unchecked item with the same mapping (serial fallback). Both verbs report an **`equipped`** flag (`--json`) — `true` iff `.context/equipment.json` exists with ≥1 item — and, in non-json mode, warn to stderr when the repo isn't equipped at all (the skill halts on that signal rather than silently dispatching `general-purpose`).
- `--check "<item>"` flips an item to `- [x]`, idempotent — one call per verified item.
- `--status` reports `done/total`; when complete, prints `dummyindex context reconcile`.

## Audit — argue-and-audit panel (`/dummyindex-audit`)

On-demand adversarial review: a free-text description spins up a **task-dependent** panel of auditors that file findings, then **argue** them (up to 3 rebuttal rounds, stopping early on agreement) before a synthesis pass writes a ranked `report.md`. The CLI is deterministic plumbing — scaffold + persona catalog + debate resumption log; the `/dummyindex-audit` skill picks the panel and orchestrates the debate via the Task tool. It does **not** require a full `.context/` index.

### `dummyindex context audit start --describe "..." [--scope PATH]... [--mode light|standard|deep] [--model opus-4.7|sonnet-4.6|haiku-4.5] [--slug S] [--force] [--root DIR] [--json]`

- Scaffolds `.context/audits/<slug>/` (`audit.json`, `description.md`, `catalog.json`, `findings/`) and emits the persona catalog as JSON (`{slug, dir, mode, model, max_rounds, scope, catalog:[...]}`).
- `--describe` is required. `--slug` defaults to a slug derived from the description; `--force` overwrites an existing audit.
- `--model` is **required** unless `.context/config.json` provides one — the model is never silently defaulted (Opus is an option). `--mode` defaults to the config's mode, else `standard`.
- `--scope PATH` (repeatable) focuses the audit on specific paths.

### `dummyindex context audit show --slug S [--root DIR] [--json]`

- Reports an audit's state: its config, which rebuttal rounds are complete, and whether `report.md` has been written.

### `dummyindex context audit-log --slug S --round N --persona P --status STATE [--note "..."] [--root DIR]`

- Appends a row to `audits/<slug>/_debate-log.json` for debate resumption. `STATE` is `started|complete|failed|skipped`. The skill logs each persona per round so a re-run skips completed rounds.

## Doc reorg (opt-in, destructive — `/dummyindex --reorg-docs`)

### `dummyindex context doc-reorg guard|list|backup|restore [path] [--root DIR] [--json] [--from DIR]`

- Safety net for the destructive in-place doc reorg; the rewrites themselves happen in the session via `Edit` with per-file confirm.
- `guard` — exit 0 if the working tree is clean, else 1 (the hard gate).
- `list` — the doc files in scope. `backup` — copy them to a timestamped backup dir. `restore --from <dir>` — put a backup back.

## Token usage

### `dummyindex usage [chat|daily|session|monthly|blocks]`

- Reads Claude Code transcripts to report token usage. No LLM cost.
- `chat` (default) — the current session: context window now (main thread, matches `/context`) plus deduplicated cumulative totals, with a subagents column summing any Task/subagent transcripts. This is what the `/tokens` slash command runs.
- `daily` / `session` / `monthly` — token totals aggregated across every project, grouped by day / session / month.
- `blocks` — usage grouped into billing blocks across every project.

## What is NOT a CLI command

- "Run the council" — that's the **skill's** job. The CLI doesn't dispatch agents.
- "Enrich PROJECT.md" — that's a markdown procedure; the agent uses `Write`.
- "Decide if a flow is trivial" — that's the dev agent's call.

Rule of thumb: the CLI moves bytes around atomically. Everything that requires judgment is in markdown.

And the human never runs it: the CLI is the agent's deterministic backbone, invoked by the skill and council. A human's interface is the slash commands inside Claude Code — plus the one-time `install` bootstrap.
