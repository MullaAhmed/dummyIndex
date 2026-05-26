# 11 — Roadmap

What's deferred. In priority order.

Each item is gated until the previous one ships.

## v0.6 — Always-on infrastructure ✅ shipped

- 3-line CLAUDE.md managed block (down from 41 lines).
- Auto-refresh hooks installed by `ingest`:
  - git `post-commit` hook → `rebuild --changed`.
  - Claude Code `PostToolUse` hook → `rebuild --changed` after Edit/Write/Bash(mv|rm|cp).
  - Claude Code `SessionStart` hook → `check --auto-refresh --quiet`.
- New CLI: `context check`, `context hooks install/uninstall/status`.
- Drift detection in `.context/cache/manifest.json`.
- Consolidation: `graph/` contents moved under `features/`; pyvis HTML dropped.

## v0.7 — Multi-agent council ✅ shipped

- Five personas: architect, senior developer, database engineer, security analyst, product manager.
- Chairman synthesizer.
- Three stages: independent perspectives → cross-review → synthesis.
- Default mode: standard. Override via `/dummyindex --mode deep|light`.
- Structural review pre-stage (architect regrouping).
- Flow filtering by senior dev.
- `_council-log.json` for resumption.
- Per-feature content hash for cache.
- CLI helpers: `flow-remove`, `section-write`, `council-log`, `features-merge`, `conventions-write`.

## Source-docs layer ✅ shipped (between v0.7 and v0.9)

Not on the original roadmap. Surfaced when running dummyindex on repos with real prose docs.

- `.context/source-docs/INDEX.{json,md}` catalogs every prose doc found in the repo (README, CHANGELOG, ARCHITECTURE, SECURITY, BRIEF, any root-level `*.md`, plus `docs/`, `doc/`, `ADR/`, `RFC/`).
- `--docs PATH` (repeatable) for external doc roots.
- Per-doc `confidence` (high/medium/low) derived from broken backticked refs + age vs newest code mtime.
- Wired into PROJECT.md, architecture/overview.md, `features/<id>/docs.md` (top-10 pointers), and the council stage-1 + stage-3 doc-evidence directive.

## v0.9 — PageIndex retrieval CLI ✅ shipped (in v0.12)

- `dummyindex context query "..."` — walks `features/INDEX.json` → scores features by token overlap with name/summary/files/symbols → returns cited markdown excerpts with `path:range`.
- Budget-capped (default 2000 tokens, `--budget N` overrides).
- Single, stable CLI surface every platform (Claude Code, Cursor, Codex CLI, OpenCode, Aider) can shell out to.
- Deterministic — no LLM in the loop. The CLI is a view over the same JSON the agent walks manually.

## v0.10 — Viewer rebuild ✅ shipped (in v0.12 + v0.13)

- v0.12: feature-grid default; D3 force toggle; search; council excerpts in tooltips.
- v0.13 follow-on: symbol-kind nodes (class/function/method) so the detail panel can cite `path:line`. Kind-filter chips in the force view. Force layout tuned for 900+ nodes.

## v0.11 — Reality checker integration ✅ shipped (in v0.12)

- `dummyindex context reality-check --feature ID` — Phase 3.5 in the skill.
- Pulls concrete claims out of the feature's canonical docs, verifies against `map/symbols.json` + symbol-graph + source.
- Contradiction → confidence flipped to `AMBIGUOUS`; surfaced for the original persona to revisit.

## v0.12 — Source-docs + retrieval + viewer + reality-check ✅ shipped

Bundles v0.9/0.10/0.11 plus the source-docs catalog (not originally on the roadmap — see "Source-docs layer" above).

## v0.13 — Structural reorg + symbol-aware viewer ✅ shipped

- Package reorganised around the BOS Backend conventions (adapted for a synchronous CLI). `docs/CONVENTIONS.md` is the contract.
- `features/graph.json` carries class / function / method nodes. The detail panel becomes the surgical-update payload: pick a feature → see touched files grouped by class/method with `path:line` citations.
- Dead-code removal: 2,185 lines of orphan exporters (`to_obsidian`, `to_canvas`, `to_cypher`, …) cut from `pipeline/export/`.
- Skill installs now stamp the SKILL.md with the package version so drift between the installed skill and the CLI is visible.

## v0.14 — MCP integrations (Context7 + Sequential Thinking)

Wire two MCP servers into the skill so the council doesn't have to guess about library APIs or wing a single-shot synthesis.

### Context7 MCP (`mcp__context7__*`)

Per-library, always-current API documentation. Plugs into three places:

- **Conventions (Phase 1.5).** When dispatching the `senior-developer` persona to write `coding-practices.md` / `testing.md`, look up the dominant framework first (Django / FastAPI / Spring / Rails / Next / etc. — detected from `map/files.json` + `pyproject.toml` / `package.json`) and seed the dispatch with Context7's testing + idioms docs for that framework. Stops the persona from inventing patterns that look right but don't match the framework's current canonical advice.
- **Per-feature council (Phase 3).** Each persona's prompt picks up Context7 docs for the libraries the feature actually imports (parsed from `imports`/`imports_from` edges). The `security-analyst` looks up current CVE-adjacent advice for that library version; the `database-engineer` looks up the ORM's current migration conventions.
- **Reality-check (Phase 3.5).** When the synthesis claims "X uses Django's `select_related` to avoid N+1", Context7 confirms the API still exists / hasn't been renamed. Today reality-check only verifies the AST; with Context7 it also verifies the library claim.

Skill change: a new `council/55-context7.md` companion describing the lookup protocol (resolve library id → fetch focused docs → include verbatim excerpt in the persona prompt).

### Sequential Thinking MCP (`mcp__sequentialthinking_sequentialthinking__sequentialthinking`)

Structured step-by-step reasoning with explicit revision. Plugs into the two places where the current skill makes its biggest single-shot judgment calls:

- **Architect's structural review (Phase 2).** Today the architect proposes a regrouping plan in one shot. With sequential-thinking, the architect drafts → cross-checks the draft against `features/symbol-graph.json` communities → revises → emits. Each revision step is logged into `_council-log.json`, so a user reviewing the merge plan can see the reasoning chain.
- **Chairman synthesis (Phase 3 stage 3).** The chairman reconciles 2–5 persona perspectives into the canonical `README.md` / `architecture.md` / `implementation.md` / `data-model.md` / `security.md` / `product.md` set. Today this is one big prompt with no revision loop. Sequential-thinking turns it into a chain: identify disagreements → propose resolutions → check each resolution against `map/symbols.json` evidence → revise.

Skill change: persona prompts get an "if your runtime exposes
`mcp__sequentialthinking_*`, use it for this dispatch; otherwise fall
back to single-shot reasoning" preamble. Companion at
`council/40-stage3-synthesis.md` documents the chain format.

### Skill orchestrator

`dummyindex/skills/skill.md` already references `council/15-conventions.md`, `council/45-reality-check.md`, etc. Add references to the two new companions, behind a graceful-fallback rule:

- If the runtime exposes the MCP tools, use them.
- If it doesn't, the council runs as today.
- Either way, the canonical `.context/` artefacts have the same shape — only the *quality* of the synthesis changes.

Gating: the council, with both MCPs available, produces a section that cites at least one library-API claim verifiable via Context7, and the chairman's `_council-log.json` shows ≥ 1 revision step on a representative sample.

## v0.15 — Polish + portability

- `dummyindex install --platform <name>` returns for non-Claude platforms (Codex, OpenCode, Cursor, Aider, …). Skill markdowns adapted per platform.
- Pre-commit hook integration (in addition to post-commit).
- Hosted skill discovery (`uv tool install dummyindex` via PyPI is the v1 distribution path).
- Cron mode: `dummyindex council --schedule weekly` for managed re-enrichment.

## v1 — Once I'm done testing

Promoted from v0.15 once the user has exercised the full v0.9 → v0.15 stack on real repos.

## Beyond v1

- **Language-agnostic extraction** (originally planned as v0.8): LLM fallback for languages without tree-sitter grammars; heuristic structure detection for config/shell/SQL/YAML; per-language confidence stamps. Deferred — needs an LLM provider choice + design discussion before code.
- **Multi-repo / workspace**: workspace-level `.context/` aggregating multiple repos.
- **Domain-specific personas**: detect stack (e.g., Solidity, Unity, K8s) and load extra personas.
- **Diff mode**: `dummyindex diff` shows what changed in `.context/` between two commits (great for PR reviews).
- **Council learning**: feed back which sections the agent referenced during real tasks; reweight what to emphasize next time.
- **Sourced retrieval API**: every retrieval result carries the chain of nodes that led to it (for explainability).

## Won't do

- Code generation. Belongs to other tools.
- Hosted service. dummyindex is local-first.
- Subscription model. MIT, install once.
- Vector store. The tree IS the retrieval index.

## Open questions

- Is the council pattern the right shape, or should we use a more rigorous "RFC + adversarial review" pattern?
- Should the architect's regrouping be human-confirmed before applying, or fully autonomous?
- Should `confidence` be more than `EXTRACTED / INFERRED / AMBIGUOUS`? (Numeric scores? Per-source attribution?)
- How do we handle private/proprietary code paths the persona shouldn't write about (compliance contexts)?
- For polyglot repos, what's the right LLM extraction fallback — one-shot per file, or a multi-step structure inference?

These get answered as we use the system, not before.
