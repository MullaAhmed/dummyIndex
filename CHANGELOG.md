# Changelog

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
