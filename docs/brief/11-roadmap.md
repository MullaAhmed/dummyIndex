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

## v0.9 — PageIndex retrieval CLI (in flight)

- `dummyindex context query "..."` — walks `features/INDEX.json` → scores features by token overlap with name/summary/files/symbols → returns cited markdown excerpts with `path:range`.
- Budget-capped (default 2000 tokens, `--budget N` overrides).
- Single, stable CLI surface every platform (Claude Code, Cursor, Codex CLI, OpenCode, Aider) can shell out to.
- Deterministic — no LLM in the loop. The CLI is a view over the same JSON the agent walks manually.

Gating: returns the right section for a representative task list ≥80% of the time.

## v0.10 — Viewer rebuild (in flight)

- Default view: feature super-nodes only, laid out in a grid; click a feature to drill into folder/file/flow hierarchy for that feature.
- Force-directed kept only for ≤50 nodes; auto-switches to grid above that.
- Search box across feature names + file paths.
- Tree/icicle alternate view for the structural reading.
- Council excerpts in tooltips so the human gets prose, not just node ids.

Gating: usable for a 200+ node graph without zoom-and-drag fatigue.

## v0.11 — Reality checker integration (in flight)

- After chairman synthesis, dispatch a reality-checker subagent.
- Reads every claim of the form `X calls Y` or `Z is checked on line N`.
- Verifies against actual source via a new `context reality-check --feature ID` helper.
- Red-flagged claims either: (a) get corrected by the original persona, or (b) get demoted to `confidence: AMBIGUOUS`.

Gating: false-claim rate after reality-check < 5% on a representative sample.

## v0.12 — Polish + portability

- `dummyindex install --platform <name>` returns for non-Claude platforms (Codex, OpenCode, Cursor, Aider, …). Skill markdowns adapted per platform.
- Pre-commit hook integration (in addition to post-commit).
- Hosted skill discovery (`uv tool install dummyindex` via PyPI is the v1 distribution path).
- Cron mode: `dummyindex council --schedule weekly` for managed re-enrichment.

## v1 — Once I'm done testing

Promoted from v0.12 once the user has exercised the full v0.9/0.10/0.11/0.12 stack on real repos.

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
