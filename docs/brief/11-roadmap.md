# 11 — Roadmap

What's deferred. In priority order.

Each item is gated until the previous one ships.

## v0.6 — Always-on infrastructure (next)

- 3-line CLAUDE.md managed block (down from 41 lines).
- Auto-refresh hooks installed by `ingest`:
  - git `post-commit` hook → `rebuild --changed`.
  - Claude Code `PostToolUse` hook → `rebuild --changed` after Edit/Write/Bash(mv|rm|cp).
  - Claude Code `SessionStart` hook → `check --auto-refresh --quiet`.
- New CLI: `context check`, `context hooks install/uninstall/status`.
- Drift detection in `.context/cache/manifest.json`.
- Consolidation: `graph/` contents moved under `features/`; pyvis HTML dropped.

Gating: every `git commit` and every Claude `Edit` produces a current `.context/` within 5s.

## v0.7 — Multi-agent council

- Five personas: architect, senior developer, database engineer, security analyst, product manager.
- Chairman synthesizer.
- Three stages: independent perspectives → cross-review → synthesis.
- Default mode: deep. Override via `/dummyindex --mode standard|light`.
- Structural review pre-stage (architect regrouping).
- Flow filtering by senior dev.
- `_council-log.json` for resumption.
- Per-feature content hash for cache.
- Adapt personas from agency-agents (MIT-licensed).
- New CLI helpers: `flow-remove`, `section-write`, `council-log`.

Gating:
- Council runs end-to-end on a 14-feature repo in under 15 min wall time at deep mode.
- Every council-touched file carries `confidence: INFERRED`.
- Resumption works: kill mid-council, re-run, picks up cleanly.

## v0.8 — Language-agnostic extraction

- LLM fallback for languages without tree-sitter grammars.
- Heuristic detection of structure for non-AST languages (config files, shell, SQL schemas).
- Per-language confidence stamps on extraction.
- Tests on a polyglot fixture (Python + Rust + SQL + YAML).

Gating: extracts meaningful structure from a repo with at least one language tree-sitter doesn't cover.

## v0.9 — PageIndex retrieval CLI

- `dummyindex context query "..."` — walks `features/INDEX.json` → relevant feature → returns cited markdown with `path:range`.
- Budget-capped (default 2000 tokens).
- Single, stable CLI surface every platform (Claude Code, Cursor, Codex CLI, OpenCode, Aider) can shell out to.
- Keeps the file-based contract intact — the CLI is a view over the same JSON.

Gating: CLI returns the right section for a representative task list ≥80% of the time.

## v0.10 — Viewer rebuild

- Drop force-directed for repos > 50 nodes.
- Default view: feature super-nodes only, laid out radially or in a grid.
- Click a feature: zoom into folder/file/flow hierarchy for that feature.
- Tree/icicle alternate view for the structural reading.
- Search box.
- Embed council excerpts in tooltips (so the human gets prose, not just node ids).

Gating: usable for a 241-node graph without zoom-and-drag fatigue.

## v0.11 — Reality checker integration

- After chairman synthesis, dispatch a reality-checker subagent.
- Reads every claim of the form `X calls Y` or `Z is checked on line N`.
- Verifies against actual source.
- Red-flagged claims either: (a) get corrected by the original persona, or (b) get demoted to `confidence: AMBIGUOUS`.

Gating: false-claim rate after reality-check < 5% on a representative sample.

## v1.0 — Polish + portability

- `dummyindex install --platform <name>` returns for non-Claude platforms (Codex, OpenCode, Cursor, Aider, …). Skill markdowns adapted per platform.
- Pre-commit hook integration (in addition to post-commit).
- Hosted skill discovery (`uv tool install dummyindex` via PyPI is the v1 distribution path).
- Cron mode: `dummyindex council --schedule weekly` for managed re-enrichment.

## Beyond v1

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
