# 07 — CLI surface

Every command. What it does. Why it exists.

## Installation

### `dummyindex install [--scope user|project] [--dir PATH]`

- Copies the skill into Claude Code's skills directory.
- `--scope user` (default) → `~/.claude/skills/dummyindex/SKILL.md`.
- `--scope project` → `<PATH>/.claude/skills/dummyindex/SKILL.md`.
- Registers the skill in the chosen `CLAUDE.md` so `/dummyindex` is recognized.
- **Installs hooks** when run with `--scope project`: post-commit git hook + PostToolUse + SessionStart hooks in `.claude/settings.json`.

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
- `--changed` re-extracts only files whose content hash changed (the auto-refresh path). The manifest tracks both code and in-repo docs, so a README edit triggers a rebuild.
- `--docs PATH` accepts the same form as `ingest`. Pass it on every rebuild that should preserve the same external doc roots.
- Outputs `added / modified / removed` summary.

### `dummyindex context check [path] [--root DIR] [--auto-refresh] [--quiet] [--docs PATH]...`

- Drift detection. Compares current source + doc hashes to the stored manifest.
- `--auto-refresh` triggers `rebuild --changed` if drift detected.
- `--quiet` suppresses output unless drift exists.
- `--docs PATH` mirrors `ingest` so external doc roots aren't reported as `removed`.
- Called by the SessionStart hook.

### `dummyindex context bootstrap [path] [--root DIR]`

- Regenerates only the managed block in `CLAUDE.md`.
- Useful when the block text changes (e.g., schema bumps).

## Hooks (installed by `ingest` or `install --scope project`)

### `dummyindex context hooks install [path] [--root DIR]`

- Idempotent. Installs all three hooks:
  - `.git/hooks/post-commit` — runs `rebuild --changed`.
  - `.claude/settings.json` PostToolUse — runs `rebuild --changed` on Edit/Write/Bash(mv|rm|cp).
  - `.claude/settings.json` SessionStart — runs `check --auto-refresh --quiet`.

### `dummyindex context hooks uninstall [path] [--root DIR]`

- Removes the three hooks above. Leaves rest of `.git/hooks` and `settings.json` untouched.

### `dummyindex context hooks status [path] [--root DIR]`

- Prints whether each hook is installed and whether it points at the current binary.

## Enrichment (called by the council)

### `dummyindex context enrich-plan [path] [--root DIR]`

- Emits `.context/_enrich_plan.json` — work-list of `tree.json` stubs.
- Grouped into per-file batches.
- Used by the senior dev to enrich tree abstracts.

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

### `dummyindex context flow-remove [--root DIR] --feature X --flow Y`

- Drops a flow's JSON + MD.
- Updates: `feature.json` (remove from `flow_ids`), `INDEX.json` (decrement `flow_count`), `graph.json` (remove flow node + edges).
- Used by the senior dev when filtering trivial/false-positive flows.

## Council (called by skill procedures)

### `dummyindex context section-write [--root DIR] --feature X --section NAME --from-file PATH`

- Atomic placement of a markdown into `features/<X>/<NAME>.md`.
- Sections: `README`, `architecture`, `implementation`, `data-model`, `security`, `product`.
- Temp-file + rename for atomicity. Idempotent.
- Used by the chairman during stage 3.

### `dummyindex context council-log [--root DIR] --feature X --stage N --agent NAME --status STATE [--note "..."]`

- Appends to `features/<X>/council/_council-log.json`.
- Status values: `started`, `complete`, `failed`, `skipped`.
- Used by every persona at start and end of work.
- Enables resumption: skill checks the log to know what's already done.

## Refresh

### `dummyindex context refresh-indexes [path] [--root DIR]`

- Rebuilds `.context/INDEX.md` from disk.
- Rebuilds `features/INDEX.md` from `features/INDEX.json`.
- Rebuilds `features/graph.json` + `features/graph.html` from the per-feature data.
- Use after enrichment + renames to reconcile derived artifacts.
- **Also migrates** legacy layouts (moves `graph/` contents under `features/`, shrinks long CLAUDE.md blocks).

## Future: retrieval CLI

### `dummyindex context query "..." [--root DIR] [--budget N]` (roadmap, v0.9)

- PageIndex-style tree search. Agent passes a natural-language question.
- Walks `features/INDEX.json` → relevant feature → relevant section.
- Returns the cited markdown + `path:range` references.
- Budget-capped (default 2000 tokens) for predictable cost in agent loops.

## What is NOT a CLI command

- "Run the council" — that's the **skill's** job. The CLI doesn't dispatch agents.
- "Enrich PROJECT.md" — that's a markdown procedure; the agent uses `Write`.
- "Decide if a flow is trivial" — that's the senior dev agent's call.

Rule of thumb: the CLI moves bytes around atomically. Everything that requires judgment is in markdown.
