# Changelog

## 0.13.2 — consolidation-pass guards (2026-05-26)

Three guards on the trivial-feature consolidation pass to stop the
failure mode where 21 parser-artifact "features" got bulk-merged into
unrelated parents under an invented `noise-absorbed` section, with no
chairman audit trail.

1. **`merge_feature` rejects unknown `--as-section` names.** A new
   `_VALID_MERGE_SECTIONS` allowlist in
   `dummyindex/context/domains/features/_constants.py` (currently
   `{"supporting"}`) is checked at the start of the merge. Ad-hoc
   section names like `noise-absorbed` are rejected before any I/O.
2. **`merge_feature` auto-appends a stage-0 chairman entry** to the
   target's `council/_council-log.json`. The audit trail can no longer
   be skipped by forgetting to run `council-log` after the merge. New
   optional `--note` flag on the CLI lets the chairman pass an explicit
   rationale; otherwise a default `merged-from:<id>` is generated.
   Backwards-compatible: existing callers that don't pass `note` keep
   working.
3. **`scaffold_features` drops empty-`__init__.py` communities** at
   ingest time. A new `_is_parser_artifact` helper in
   `builder.py` filters out Leiden communities whose only files are
   `__init__.py` and which have no entry points. Real package APIs
   that define callables in `__init__.py` are kept. This stops the
   upstream noise from ever reaching the trivial filter.

**Why:** the previous consolidation pass on an external project produced
five `noise-absorbed.md` files (a section name not in the spec), 21
features merged into 5 catch-all parents with no real call-graph
relationship to most of the source files, and no Chairman entries in
the council log for any of those decisions. The spec required Chairman
per feature, valid section names, and per-decision logging — but
nothing in the code enforced any of it. These three guards close the
gaps at the API boundary.

The procedure (`dummyindex/skills/council/filter-trivial.md`) is updated
to match: explicit "one Chairman per feature, no batching" language,
Outcome C requires recording the parent-check in the council-log note,
and the auto-log behavior of `features-merge` is documented so the
procedure and code can't drift.

5 new tests added (350 total, all passing).

## 0.13.1 — respect .gitignore by default (2026-05-26)

`dummyindex ingest` now reads `.gitignore` in addition to
`.dummyindexignore` / `.codeindexignore`. Both files are checked at the
scan root and every ancestor directory up to the git repo root, layered
together (gitignore first, dummyindex-specific last).

**Why:** running on a real repo with vendored code surfaced the bug —
364 of 405 indexed files were vendored libpostal + ad-hoc scripts
because dummyindex didn't read the project's existing `.gitignore`.
Users had to write a separate `.dummyindexignore` listing the same
patterns. With this change, the gitignore-already-knows-this case just
works; `.dummyindexignore` becomes the override for dummyindex-only
exclusions (heavy benchmark dirs you commit to git but don't want
catalogued).

Side effect: the `_load_dummyindexignore` helper now reads both files
in a single ancestor walk. Helper name kept the same to avoid public-
surface churn. Patterns are appended in load order, so a
`.dummyindexignore` near the scan root overrides a same-named pattern
in a parent `.gitignore`.

## 0.13.0 — structural reorg + symbol-aware viewer + conventions (2026-05-26)

Two big shifts in one release:

1. **Package reorganised** around an adapted form of the BOS Backend
   conventions (see "Folder layout" + "Conventions" below).
2. **Viewer rebuilt** to surface classes / functions / methods, so a
   feature's detail panel cites the exact `path:line` you need to make a
   surgical edit (see "Symbol-aware features viewer" below).

All 345 tests still pass; the public test surface is unchanged.

### Symbol-aware features viewer

The graph stopped at file-level granularity. Updates to a feature meant
"this feature touches `app/api/foo.py` somewhere" — you still had to grep
to find which class or method.

`features/graph.json` now carries the AST symbol catalog inline:

- 7 node kinds (was 4): `folder`, `file`, **`class`**, **`function`**,
  **`method`**, `feature`, `flow`. Each symbol node carries `path` +
  `range` so the viewer can deep-link.
- Edge relations gain `file → class/function` (contains),
  `class → method` (contains), `feature → symbol` (touches).
- DummyIndex-on-itself goes from 293 nodes / 1,767 edges → 899 / 3,215.

Viewer changes (`features/graph.html`):

- **Detail panel** is now the surgical-update payload. Click a feature →
  "Files · classes · methods" section lists each touched file with a
  grouped list of class / function / method names, each carrying a
  `:line` suffix. "Flows" block shows each flow with its file targets.
- **Force view** gains kind-filter chips (default-on: folder, file,
  feature; default-off: class, function, method, flow). Symbols would
  otherwise overwhelm the layout on large repos.
- **Force tuning**: per-kind charge, collision radii, link distances.
- **Tooltips** include `path:line` when the node has a range.

Plumbing: `_graph_view(features, flows, symbols=None)` now optional-takes
the `map/symbols.json` payload. `builder._write_all` and
`indexes.rebuild_features_graph` both call `_load_symbols_map`. Missing
symbols.json gracefully degrades to the old file-only graph.

### Skill versioning

- `dummyindex/skills/skill.md` carries a `__VERSION__` placeholder right
  under its title. `dummyindex install` substitutes the installed package
  version at copy time, so the installed `~/.claude/skills/dummyindex/SKILL.md`
  shows "Installed from dummyindex `<version>`" at the top. The
  `.dummyindex_version` sidecar file stays for machine-readable checks.

### Folder layout

### Folder layout

- **`dummyindex/cli/`** — new top-level CLI package. The old monolithic
  `dummyindex/context/cli.py` (1,354 lines) is split into one module per
  subcommand (`init.py`, `rebuild.py`, `bootstrap.py`, `enrich.py`,
  `features.py`, `refresh.py`, `check.py`, `hooks.py`, `council.py`,
  `conventions.py`, `query.py`, `reality_check.py`) plus `_common.py`,
  `_migrate.py`, and `_usage.py`. `dispatch()` and `_resolve_context_root`
  remain the public surface.
- **`dummyindex/export/`** — promoted from `dummyindex/pipeline/export/` to
  a top-level package. Was a 2,785-line monolith; now four files
  (`__init__.py`, `_common.py`, `_html_assets.py`, `graph.py`). 2,185 lines
  of orphaned exporters (`to_obsidian`, `to_canvas`, `to_cypher`,
  `push_to_neo4j`, `to_graphml`, `to_svg`, `to_structure_*`, `to_flow_*`,
  `to_feature_*`, `attach_hyperedges`, `restore_hyperedges_from_disk`,
  `prune_dangling_edges`) **removed** — zero in-repo callers, zero tests.
  `to_json` and `to_html` remain.
- **`dummyindex/pipeline/`** internals regrouped:
  - `pipeline/io/` — `cache.py` + `detect.py` (filesystem-touching).
  - `pipeline/build/` — `__init__.py` (`build_from_json`), `structure.py`,
    `validate.py`, plus new `references.py` (textual reference detection
    split out of `structure.py`) and `_common.py` (`_rel_path` shared).
  - `pipeline/extract/` — `extract.py` (3,439 lines) split into 18 modules:
    `config.py`, `_common.py`, `_imports.py`, `_helpers.py`, `_configs.py`,
    `_generic.py`, `_python_rationale.py`, `_resolve.py`, and a
    `languages/` subpackage with one file per custom-walk language
    (Julia, Go, Rust, Zig, PowerShell, Objective-C, Elixir, Verilog,
    Blade, Dart) plus `_wrappers.py` for thin generic wrappers.
- **`dummyindex/context/`** regrouped by lifecycle phase:
  - `context/build/` — `runner.py`, `incremental.py`, `meta.py`, `maps.py`,
    `tree.py`, `graph.py`, `conventions.py`, `manifest.py`.
  - `context/output/` — `bootstrap.py`, `docs.py`, `instructions.py`,
    `viewer.py`.
  - `context/domains/` — `enrich.py`, `query.py`, `reality_check.py`,
    `council.py`, plus `features/` (was `features.py`, 1,575 lines, split
    into 10 modules) and `source_docs/` (was `source_docs.py`, 850 lines,
    split into 9 modules).
  - `context/hooks.py`, `context/enums.py`, `context/schemas/` stay top-level.

### Conventions

- **`docs/CONVENTIONS.md`** — new. Adapted form of the BOS Backend
  conventions. Codifies the domain-first folder rule, 200/400/600-line
  file-size cap, "every data class is `@dataclass(frozen=True)`" (BOS §7
  adapted: no Pydantic — no HTTP boundary justifies it), per-area enums
  rule, KISS/YAGNI/no-dangling-code, and lists the BOS sections that
  explicitly do **not** apply (HTTP endpoints, async, JWT, JSONB, tenant
  scope, soft-delete, transactions, structlog observability).

### Enums

- **`dummyindex/pipeline/enums.py`** — `ConfidenceLevel`,
  `NodeKind`, `EdgeRelation` (all `(str, Enum)` for JSON round-trip).
  Closed-alphabet lookup sets exported (`HIERARCHY_RELATIONS`,
  `INFERABLE_LEVELS`).
- **`dummyindex/context/enums.py`** — `DocConfidence`, `ContextSubcommand`,
  plus the `DOC_CONFIDENCE_ORDER` lookup dict.
- ~85 literal-string sites (`"EXTRACTED"` / `"INFERRED"` / `"AMBIGUOUS"` /
  `"high"` / `"medium"` / `"low"`) replaced with enum references across 25
  files. Comparisons, allowlists, dataclass defaults, and dict orderings
  now derive from the enum.
- `dummyindex/cli/_HANDLERS` is keyed by `ContextSubcommand` enum;
  `dispatch()` validates the incoming subcommand against the enum.

### Migration notes

- Old in-repo imports like `from dummyindex.context.bootstrap import ...`
  now live at `dummyindex.context.output.bootstrap`. Same for `runner`,
  `meta`, `maps`, `tree`, `graph`, `conventions`, `incremental`,
  `manifest` → `context/build/`; `docs`, `instructions`, `viewer` →
  `context/output/`; `enrich`, `query`, `reality_check`, `council`,
  `source_docs`, `features` → `context/domains/`.
- `from dummyindex.pipeline.detect` → `from dummyindex.pipeline.io` (re-
  exported from the `io` package's `__init__.py`).
- `from dummyindex.pipeline.export` → `from dummyindex.export`.
- `from dummyindex.context.cli` → `from dummyindex.cli`.
- The lazy `__getattr__` map in `dummyindex/__init__.py` is updated;
  external callers using `dummyindex.detect` / `dummyindex.extract` /
  `dummyindex.to_json` / etc. see no change.

## 0.12.0 — source-docs + retrieval + viewer + reality-check

Pre-release tag for testing. Will be promoted to `1.0` once exercised on real repos.

Bundles four roadmap items into one milestone:

### Source-docs catalog (new, not on the original roadmap)

- **Source-docs catalog** with explicit staleness signals. `dummyindex ingest` now scans existing prose docs (`README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `SECURITY.md`, `BRIEF.md`, any `*.md` at the repo root, plus `docs/`, `doc/`, `ADR/`, `RFC/`) and writes `.context/source-docs/INDEX.{json,md}`. Each entry carries a `confidence` (`high` / `medium` / `low`) derived from:
  - `broken_refs` — backticked code identifiers in the doc that no longer appear in `map/symbols.json` or `map/files.json` (the strongest signal that a doc has rotted).
  - `age_bucket` — doc mtime vs newest code mtime.
- **`--docs PATH` flag** (repeatable) on `ingest` / `context init` / `context rebuild` / `context check`. Points at doc folders outside the scan root — useful when ADRs / design docs live in a sibling directory. External paths are stored as absolute and marked `is_external: true`.
- **Doc layer surfaced into existing artifacts**:
  - `PROJECT.md` gains an "Existing documentation" section with the confidence breakdown and the highest-confidence README/intro doc.
  - `architecture/overview.md` gains a "Documented architecture" subsection when matching docs exist.
  - `features/<id>/docs.md` (new file) — pointer list to catalog entries that mention a feature's files or symbols. Pointers, not copies: confidence/staleness stays in `source-docs/INDEX.md`. Capped at the top 10 matches per feature with an overflow pointer back to the catalog.
  - Council prompts (stage 1 + stage 3) now include explicit "treat doc claims as hypotheses; verify against AST" instructions.

### v0.9 — PageIndex retrieval CLI

- **`dummyindex context query "..."`** — walks `features/INDEX.json`, scores features by token overlap with `name` / `summary` / file basenames / member-symbol names, returns the top-K with cited markdown excerpts (`path:range`).
- Budget-capped output (default 2000 tokens via `--budget N`).
- Stopword filter + CamelCase/snake_case token splitting so `parse_body` matches `ParseBody`.
- Deterministic, no LLM — same JSON the agent walks manually.
- New module: `dummyindex/context/query.py`.

### v0.10 — Viewer rebuild

- **Feature-grid as the default view** in `features/graph.html`. One clickable card per feature, sorted by file_count; opens a detail panel with summary, files, flows, confidence. Scales cleanly to 200+ features (no force-directed hairball).
- **Force-directed** kept behind a toggle for repos where the layered structure is the clearer mental model.
- **Search box** across feature names + summaries + file paths; dims non-matching cards / nodes.
- Viewer HTML extracted into its own module: `dummyindex/context/viewer.py`. `features.py` lost ~225 lines of inline HTML.

### v0.11 — Reality checker

- **`dummyindex context reality-check --feature <id> [--demote] [--json]`** — pulls concrete claims from a feature's canonical docs and verifies each against the AST.
- Claim shapes recognized: `` `X` calls `Y` ``, `` `X` uses `Y` ``, `` `X` has method `Y` ``, `` `path/to/file.py:42` ``.
- Each claim: `verified` (AST agrees) / `contradicted` (AST disagrees) / `ambiguous` (symbols exist but no direct edge).
- Writes `features/<id>/_reality-check.{json,md}`.
- `--demote` flips the feature's `confidence` to `AMBIGUOUS` in `feature.json` + `INDEX.json` when contradictions exist.
- Skill phase 3.5 (between chairman synthesis and flow refinement): `dummyindex/skills/council/45-reality-check.md`.
- New module: `dummyindex/context/reality_check.py`.

### Changed

- `pipeline.detect.detect()` accepts `extra_doc_roots: list[Path] = ()`. External roots are scanned without `.dummyindexignore` lookups (those belong to the home repo).
- Drift manifest (`cache/manifest.json`) now tracks both code and in-repo docs, so doc edits show up in `dummyindex context check` and trigger `dummyindex context rebuild --changed`.
- `dummyindex.context.incremental.rebuild_changed` compares against the manifest (which has docs) instead of `map/files.json` (code only), so a README edit no longer falsely reports "no source files changed".
- Broken-references matcher is now much wider — checks against *all* tracked repo files (not just code), JSON schema keys harvested from `*.json` in the repo, a built-in framework whitelist (Claude Code tool names, hook event names, dummyindex's own `.context/` artifact filenames and field names), and basename matches against that whitelist.
- Confidence thresholds softened: `high` accepts ≤10% broken refs (was ≤5%), `low` requires both ≥40% broken refs *and* at least 4 broken refs. Protects tiny docs that cite one hypothetical identifier.

### Docs

- README, `docs/brief/04-data-model.md`, `docs/brief/05-council.md`, `docs/brief/07-cli.md`, `docs/brief/08-skill.md`, `docs/brief/11-roadmap.md` updated to describe source-docs, query CLI, new viewer, and reality-check phase.
- v0.8 (language-agnostic LLM extraction) moved to "Beyond v1" — needs a provider choice + design discussion that hasn't happened.

### Tests

- 345 tests pass (was 278 pre-source-docs).
- New: `tests/context/test_source_docs.py` (30), `tests/context/test_query.py` (14), `tests/context/test_reality_check.py` (16).

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
