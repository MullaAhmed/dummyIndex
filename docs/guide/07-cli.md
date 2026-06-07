# 07 — CLI surface

Every command. What it does. Why it exists.

## Installation

### `dummyindex install [--scope user|project] [--dir PATH] [--skill-only]`

- Copies the skill into Claude Code's skills directory.
- `--scope user` (default) → `~/.claude/skills/dummyindex/SKILL.md`.
- `--scope project` → `<PATH>/.claude/skills/dummyindex/SKILL.md`.
- Registers the skill in the chosen `CLAUDE.md` so `/dummyindex` is recognized.
- **Auto-init** (v0.13.4): when the resolved project candidate (`--dir`, else CWD) is a git repo, `install` also runs the full project init — builds `.context/`, writes the managed `CLAUDE.md` block, and installs the SessionStart drift hook. Pass `--skill-only` to suppress this and copy the skill alone. A non-git candidate prints a one-line "skipped project init" note.
- **Installs the SessionStart drift hook** as part of auto-init (v0.13.5 — a single hook running `dummyindex context plan-update`, not the legacy three-hook set).

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

### `dummyindex context rebuild [--changed] [path] [--root DIR] [--docs PATH]...`

- Full or incremental rebuild.
- `--changed` re-extracts only files whose content hash changed (the manual incremental path). The manifest tracks both code and in-repo docs, so a README edit is detected. As of v0.13.5 this is run manually, not from a hook.
- `--docs PATH` accepts the same form as `ingest`. Pass it on every rebuild that should preserve the same external doc roots.
- Outputs `added / modified / removed` summary.

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

- Idempotent. Installs **one** hook (v0.13.5):
  - `.claude/settings.json` SessionStart — runs `dummyindex context plan-update`.
- **Upgrade scrub**: removes any legacy `git post-commit` script and sentinel-bearing `PostToolUse` entry installed by pre-v0.13.5 versions. User-authored hooks (no sentinel) are left untouched.

### `dummyindex context hooks uninstall [path] [--root DIR]`

- Removes the SessionStart hook (and scrubs any legacy entries). Leaves the rest of `.git/hooks` and `settings.json` untouched.

### `dummyindex context hooks status [path] [--root DIR]`

- Prints whether the SessionStart hook is installed and whether it points at the current binary. (`HookStatus` carries only `claude_session_start` as of v0.13.5.)

## Onboarding & preflight

### `dummyindex context preflight [path] [--root DIR] [--json]`

- Read-only inventory of the repo's existing `.claude/` setup before any write: `settings.json` validity + user hooks, `.claude/rules/`, project agents, CLAUDE.md managed-block state, git-clean status.
- The skill runs it as Phase 0 on every invocation and surfaces the summary.

### `dummyindex context onboard [path] [--root DIR] --model opus-4.7|sonnet-4.6|haiku-4.5 [--scope repo|subdir|explicit] [--scope-path PATH] [--mode light|standard|deep] [--hook|--no-hook] [--doc PATH]... [--defaults]`

- Persists the first-run council preferences (scope, mode, model, auto-refresh hook, external docs) to `.context/config.json`.
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

## Build loop (v0.15)

### `dummyindex context propose --slug S --title "..." [--root DIR] [--force]`

- Build loop — grounded planning. Scaffolds `.context/proposals/<slug>/` (`proposal.json` + `spec.md` / `plan.md` / `checklist.md`).
- Runs a deterministic consistency scan (reuses `query`, no LLM) and records related features + conventions in `proposal.json` and a `## Consistency` block in `spec.md`.
- `--force` overwrites an existing proposal.
- Why: gives `/dummyindex-plan` a structured, index-grounded scaffold to fill rather than drafting into the void.

### `dummyindex context equip [apply] [path] [--root DIR] [--dry-run] [--for-proposal S] [--json]`

- Build loop — render the project-tuned toolkit into `.claude/` from `.context/` + preflight data; records in `.context/equipment.json` (schema v2).
- Generates: `<stack>-implementer` + `<stack>-tester` agent, `<proj>-reviewer` agent, `<proj>-verify` skill; wires the detected formatter's PostToolUse hook into `settings.json` under `DUMMYINDEX_EQUIP` sentinel; adopts existing project specialists into the manifest (manifest-only, no overwrite).
- `--for-proposal S` scopes adoption to the capabilities `S`'s `checklist.md` demands.
- `--dry-run` writes nothing; additive + never-clobber on real runs.

### `dummyindex context equip status [--root DIR] [--json]`

- Classify every generated item: `pristine` / `user-modified` / `missing`, with each item's version.

### `dummyindex context equip refresh [--root DIR] [--dry-run]`

- Re-render PRISTINE-and-stale items, re-baseline + minor-bump. USER_MODIFIED items are skipped forever.

### `dummyindex context equip reset NAME [--root DIR]`

- Restore one generated item to its pristine render (the escape hatch), re-baseline + bump.

### `dummyindex context equip uninstall [--root DIR] [--dry-run]`

- Remove PRISTINE generated files + the `DUMMYINDEX_EQUIP` hook + the manifest; USER_MODIFIED files are kept and reported.

### `dummyindex context equip patch --item NAME --from-file F [--root DIR]`

- Sanctioned evolution: apply an exact-once old→new patch (`F` is `{"old": "...", "new": "..."}`) to a generated item, re-baseline + patch-version bump.
- Why: lets build-run learnings flow back into generated tooling (`dummyindex-build` calls this post-build) without stomping user edits.

### `dummyindex context build --proposal S (--next | --check "<item>" | --status) [--json]`

- Build loop — deterministic state machine over a proposal's `checklist.md`. The `/dummyindex-build` skill orchestrates dispatch; this command drives the state.
- `--next` prints the first unchecked item, its mapped equipment agent (or per-item `general-purpose` fallback), and grounding paths. It also reports an **`equipped`** flag (`--json`) — `true` iff `.context/equipment.json` exists with ≥1 item — and, in non-json mode, warns to stderr when the repo isn't equipped at all (the skill halts on that signal rather than silently dispatching `general-purpose`).
- `--check "<item>"` flips an item to `- [x]`, idempotent.
- `--status` reports `done/total`; when complete, prints `dummyindex context rebuild --changed`.

## Doc reorg (opt-in, destructive — `/dummyindex --reorg-docs`)

### `dummyindex context doc-reorg guard|list|backup|restore [path] [--root DIR] [--json] [--from DIR]`

- Safety net for the destructive in-place doc reorg; the rewrites themselves happen in the session via `Edit` with per-file confirm.
- `guard` — exit 0 if the working tree is clean, else 1 (the hard gate).
- `list` — the doc files in scope. `backup` — copy them to a timestamped backup dir. `restore --from <dir>` — put a backup back.

## What is NOT a CLI command

- "Run the council" — that's the **skill's** job. The CLI doesn't dispatch agents.
- "Enrich PROJECT.md" — that's a markdown procedure; the agent uses `Write`.
- "Decide if a flow is trivial" — that's the dev agent's call.

Rule of thumb: the CLI moves bytes around atomically. Everything that requires judgment is in markdown.
