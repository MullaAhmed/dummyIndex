# Changelog

## Unreleased

### Added

- **Source-docs catalog** with explicit staleness signals. `dummyindex ingest` now scans existing prose docs (`README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `SECURITY.md`, `BRIEF.md`, any `*.md` at the repo root, plus `docs/`, `doc/`, `ADR/`, `RFC/`) and writes `.context/source-docs/INDEX.{json,md}`. Each entry carries a `confidence` (`high` / `medium` / `low`) derived from:
  - `broken_refs` — backticked code identifiers in the doc that no longer appear in `map/symbols.json` or `map/files.json` (the strongest signal that a doc has rotted).
  - `age_bucket` — doc mtime vs newest code mtime.
- **`--docs PATH` flag** (repeatable) on `ingest` / `context init` / `context rebuild` / `context check`. Points at doc folders outside the scan root — useful when ADRs / design docs live in a sibling directory. External paths are stored as absolute and marked `is_external: true`.
- **Doc layer surfaced into existing artifacts**:
  - `PROJECT.md` gains an "Existing documentation" section with the confidence breakdown and the highest-confidence README/intro doc.
  - `architecture/overview.md` gains a "Documented architecture" subsection when matching docs exist.
  - `features/<id>/docs.md` (new file) — pointer list to catalog entries that mention a feature's files or symbols. Pointers, not copies: confidence/staleness stays in `source-docs/INDEX.md`. Capped at the top 10 matches per feature with an overflow pointer back to the catalog.
  - Council prompts (stage 1 + stage 3) now include explicit "treat doc claims as hypotheses; verify against AST" instructions.

### Changed

- `pipeline.detect.detect()` accepts `extra_doc_roots: list[Path] = ()`. External roots are scanned without `.dummyindexignore` lookups (those belong to the home repo).
- Drift manifest (`cache/manifest.json`) now tracks both code and in-repo docs, so doc edits show up in `dummyindex context check` and trigger `dummyindex context rebuild --changed`.
- `dummyindex.context.incremental.rebuild_changed` compares against the manifest (which has docs) instead of `map/files.json` (code only), so a README edit no longer falsely reports "no source files changed".
- Broken-references matcher is now much wider — checks against *all* tracked repo files (not just code), JSON schema keys harvested from `*.json` in the repo, a built-in framework whitelist (Claude Code tool names, hook event names, dummyindex's own `.context/` artifact filenames and field names), and basename matches against that whitelist. Catches the case where a doc cites `map/files.json` or `feature.json` (which are real but generated) and would previously have been flagged broken.
- Confidence thresholds softened: `high` accepts ≤10% broken refs (was ≤5%), `low` requires both ≥40% broken refs and at least 4 broken refs. The minimum-broken-count floor protects tiny docs from being unfairly downgraded when they cite a single hypothetical identifier.

### Docs

- README, `docs/brief/04-data-model.md`, `docs/brief/05-council.md`, `docs/brief/07-cli.md`, `docs/brief/08-skill.md` updated to describe `source-docs/` and the `--docs` flag.

## 0.5.0 — Claude Code only

Major reset around the v2 `.context/` flow. The package now ships one purpose: index a repo for Claude Code via a deterministic CLI backbone plus an in-session LLM enrichment pass.

### Added

- `dummyindex ingest <path>` — primary entry point. Writes `<path>/.context/` (tree, maps, conventions, playbooks, graph) and a managed block in `<path>/CLAUDE.md`. Equivalent to `dummyindex context init <path>`.
- `dummyindex context enrich-plan <path>` — emits `.context/_enrich_plan.json`, an ordered work-list of tree.json nodes whose abstracts are still deterministic stubs, grouped into per-file batches.
- `dummyindex context enrich-apply <path> --from-json FILE` — merges a `{node_id: abstract}` JSON mapping into `tree.json` idempotently, bumping each touched node's `confidence` from `EXTRACTED` → `INFERRED`. Warns and exits non-zero on unknown node_ids.
- `dummyindex install --scope project [--dir PATH]` — install the Claude Code skill per-repo instead of user-global.
- `/dummyindex` skill rewrite — Claude now runs the CLI then enriches `PROJECT.md`, `architecture/overview.md`, `tree.json` abstracts, all five playbooks, and `graph/GRAPH_REPORT.md` from inside the session. The enrichment write-back goes through `dummyindex context enrich-apply` (no inline tree-mutation Python).

### Removed

- All non-Claude platform installers (Codex, OpenCode, Cursor, Gemini, Aider, Copilot, Claw, Droid, Trae, Hermes, Kiro, Antigravity, VSCode, Windows).
- The legacy v1 commands (`add`, `query`, `path`, `explain`, `update`, `watch`, `cluster-only`, `save-result`, `check-update`, `benchmark`, `serve`, `hook`).
- Dead modules: `dummyindex/runtime/{serve,ingest,hooks,transcribe,watch,manifest,run_log}.py` and `dummyindex/analysis/{flows,flow_naming,features,feature_naming,report,wiki,benchmark}.py`.
- Stale install fragments: `_PLATFORM_CONFIG`, per-platform skill files, `claude install`/`gemini install`/etc. subcommands.
- Optional-dependency extras with no surviving callers: `mcp`, `neo4j`, `pdf`, `watch`, `svg`, `office`, `video`. Only `leiden` and `dev` remain.
- `V0_SCOPE.md`, `BRIEF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `.opencode/`, `evals/v0/` — superseded by this README and by the running CLI.

### Fixed

- `dummyindex-out/` references purged from the (now slimmed) installer text. Every CLAUDE.md / AGENTS.md / GEMINI.md template that survives points at `.context/`.
- `.claude/`, `.cursor/`, `.aider/`, `.kiro/`, `.trae/`, `.trae-cn/`, `.github/`, `.gitlab/`, and `.context/` are now skipped by both `pipeline.detect` and `pipeline.structure` so agent config / self-output never lands in the index.
- `tree.json` no longer carries phantom file nodes for non-code files (CLAUDE.md, README.md, configs, etc.). The v2 code paths now call `build_structure(..., include_extras=False)`; the legacy "include every file in the source layout" behavior is preserved as the default for any external caller.

### Public API

- `dummyindex/__init__.py` now lazy-exposes only the v2 surface: `detect`, `extract`, `collect_files`, `build_from_json`, `build_structure`, `cluster`, `to_json`, `to_html`. Everything else accessible via the `dummyindex.context.*` subpackage or the CLI.
