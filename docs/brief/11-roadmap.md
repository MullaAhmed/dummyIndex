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

- Package reorganised around the BOS Backend conventions (adapted for a synchronous CLI). `docs/reference/01-conventions.md` is the contract.
- `features/graph.json` carries class / function / method nodes. The detail panel becomes the surgical-update payload: pick a feature → see touched files grouped by class/method with `path:line` citations.
- Dead-code removal: 2,185 lines of orphan exporters (`to_obsidian`, `to_canvas`, `to_cypher`, …) cut from `pipeline/export/`.
- Skill installs now stamp the SKILL.md with the package version so drift between the installed skill and the CLI is visible.

## v0.13.5 — SessionStart drift hook replaces shell-side rebuild ✅ shipped

A correction to the v0.6 auto-refresh model. The old design installed three hooks (`git post-commit`, Claude `PostToolUse`, Claude `SessionStart`), all firing `rebuild --changed` in a shell. That deterministic-only refresh re-ran feature scaffolding on every edit — producing orphan `community-N/` folders, clobbering `features/INDEX.json`, and stamping placeholder `flow-NNN.md` files the skill never came back to rewrite (the skill never runs from a shell hook).

The fix flips the model: **hooks no longer rebuild the backbone**.

- **New CLI `dummyindex context plan-update`** — prints a markdown drift report to stdout (one line per feature whose source mtime exceeds its docs' mtime). Empty when nothing is stale. Claude's `SessionStart` hook takes plain stdout as `additionalContext`.
- **New module `dummyindex.context.drift`** — mtime-based staleness, with heuristic decay: editing a feature doc advances its mtime and the signal goes quiet. No `mark-updated` command needed.
- **`hooks` install now installs only `SessionStart`** and scrubs the legacy post-commit + PostToolUse entries on upgrade (user-authored hooks without our sentinel are left untouched).
- The running Claude session — which knows *what* changed and *why* — updates `.context/features/<id>/*.md` in place, instead of a blind shell rebuild.

## v0.14 — Spec-kit-shaped pipeline + stack-specialist dev + onboarding ✅ shipped

The redesign that replaces the v0.13 parallel-essay model. Inspired by [github/spec-kit](https://github.com/github/spec-kit): layered artifacts produced by a sequential pipeline, each step with one author and one job.

**Decisions locked (2026-05-27):**

1. `README.md` per feature is **dropped** — `spec.md` is the entry point. No 10-line index file.
2. Reality-check validates `plan.md` + `concerns.md` `path:range` citations. `spec.md` is intent-level, not line-checked.
3. `standard` is the **default** mode; `--mode light|deep` overrides.

### Artifact reshape

Each feature gets three layered docs instead of six overlapping essays:

- `spec.md` — what does this feature do? (intent, contracts, user-visible behavior)
- `plan.md` — how is it implemented? (architecture, file map, key decisions)
- `concerns.md` — risks and gaps (data integrity, security, product surface)

Retires: `README.md` (dropped entirely — `spec.md` is the entry point), `architecture.md`, `implementation.md`, `data-model.md`, `security.md`, `product.md`. `section-write` accepts both the new and legacy section names for one release. Anything pointing at `<feature>/README.md` (the viewer, `features/INDEX.md`) gets repointed at `spec.md`.

### Pipeline

```
backbone → /specify (dev) → /plan (architect) → /critique (critics, mode-gated)
```

- **/specify**: one stack-specialist dev (FastAPI / Django / Spring / React / data / AI / generic, picked from `map/files.json` + manifests) drafts `spec.md` + `plan.md`.
- **/plan**: architect reorganises `plan.md` in place; writes `02-architect-notes.md` audit.
- **/critique**: critics (DBA / security / PM) file findings into `concerns.md`. Mode-gated:
  - `light`: skip critique entirely.
  - `standard` (default): one critic, picked by feature signals.
  - `deep`: all relevant critics + cross-review.

### Persona collapse

From 6 personas to 3 role classes:

- **Dev** — one parameterised persona (`{{framework}}` slot, Context7 docs injected per dispatch when v0.15 lands).
- **Architect** — keeps the regrouping pre-stage, gains the per-feature `plan.md` revision job.
- **Critics** — DBA / security / PM as critique-only, no primary authorship.

Retired: chairman (no synthesis step needed), standalone senior-developer (folded into the dev's generic branch).

### Onboarding flow

First `/dummyindex` on a repo with no `.context/config.json` triggers a 5-question interactive setup (Claude Code's question UI; CLI-prompt fallback deferred to v0.16). Answers persist to `.context/config.json` (committed — team shares prefs; stores **choices only, never API keys**, which route through the Claude session).

Questions:

1. **Scope** — whole repo / a subdir / pass paths explicitly each run.
2. **Mode** — standard (recommended) / light / deep, with a live cost + time estimate shown after the pick (feature count is already known from the backbone).
3. **Model** — Opus 4.7 / Sonnet 4.6 (recommended) / Haiku 4.5. _Required — never silently defaulted._
4. **Auto-refresh hook** — install the SessionStart drift hook (recommended) / skip.
5. **External docs** — none / collect paths.

Behavior:

- Questions 1–3 required; 4–5 skippable with defaults.
- Fires on v0.13.x→v0.14 upgrade too (existing `.context/`, no `config.json`) — captures model + mode without forcing a re-ingest.
- `--reconfigure` re-runs all 5. (`config get/set` for surgical edits deferred to v0.16.)
- `dummyindex install --no-onboarding --defaults` writes a default `config.json` non-interactively, for CI / scripted runs.
- `config.json` carries `schema_version` for forward migration.

### Skill changes

- `council/20-specify.md`, `council/30-plan.md`, `council/40-critique.md` (replacing the old stage1/stage2/stage3 markdowns).
- `agents/dev.md` (parameterised), `agents/critic-database.md` / `critic-security.md` / `critic-product.md`. `agents/chairman.md` retired.
- New CLI: `dummyindex context dev-pick --feature ID` returns the picked stack persona for inspection; `dummyindex onboard` / `--reconfigure` drives the question flow; `dummyindex config show` prints the resolved config.

Gating: a 14-feature FastAPI repo runs onboarding (model + mode captured), then in standard mode produces `spec.md` + `plan.md` + `concerns.md` per non-trivial feature, with `02-architect-notes.md` showing concrete revisions and at least one `path:range`-cited critic finding per critic dispatched.

## v0.15 — MCP integrations (Context7 + Sequential Thinking)

Wire two MCP servers into the v0.14 pipeline so authors don't guess at library APIs and the architect's revision is auditable.

### Context7 MCP (`mcp__context7__*`)

Per-library, always-current API documentation. Plugs into:

- **Conventions (Phase 1.5).** Seed `coding-practices.md` / `testing.md` with Context7's docs for the dominant framework detected from `map/files.json` + manifests. Stops the agent inventing patterns that look right but don't match canonical advice.
- **`/specify` dispatch.** The dev persona is parameterised by framework; Context7 fills the `{{framework_docs}}` slot with focused excerpts for the libraries the feature actually imports.
- **`/critique` dispatch.** The DBA looks up current ORM migration conventions; the security critic looks up CVE-adjacent advice for the relevant library versions.
- **Reality-check.** When the plan claims "X uses Django's `select_related` to avoid N+1", Context7 confirms the API still exists. Today reality-check only verifies the AST.

Skill change: a new `council/55-context7.md` companion describing the lookup protocol (resolve library id → fetch focused docs → include verbatim excerpt in the persona prompt).

### Sequential Thinking MCP (`mcp__sequentialthinking_sequentialthinking__sequentialthinking`)

Structured step-by-step reasoning with explicit revision. Plugs into the two places where the pipeline makes its biggest judgment calls:

- **Architect's structural review (Phase 2).** Drafts a regrouping plan → cross-checks against `features/symbol-graph.json` communities → revises → emits. Each revision step logs into `_council-log.json`.
- **Architect's `/plan` revision (Phase 3 stage 2).** Identifies what to sharpen in the dev's draft → proposes changes → checks each against `map/symbols.json` → revises. Audit trail in `02-architect-notes.md`.

Skill change: persona prompts get an "if your runtime exposes `mcp__sequentialthinking_*`, use it for this dispatch; otherwise fall back to single-shot reasoning" preamble.

### Graceful fallback

- If the runtime exposes the MCP tools, use them.
- If it doesn't, the pipeline runs as v0.14 without MCP.
- Either way, the `.context/` artifacts have the same shape — only the *quality* of the prose changes.

Gating: a representative council run with both MCPs available cites ≥ 1 Context7-verifiable library claim and shows ≥ 1 sequential-thinking revision step in `02-architect-notes.md`.

## v0.16 — Polish + portability

- `dummyindex install --platform <name>` returns for non-Claude platforms (Codex, OpenCode, Cursor, Aider, …). Skill markdowns adapted per platform.
- CLI-prompt fallback for onboarding (the v0.14 question flow runs through stdin for terminal-only / non-Claude use).
- `dummyindex config get/set <key>` for surgical config edits without re-running the full onboarding flow.
- Hosted skill discovery (`uv tool install dummyindex` via PyPI is the v1 distribution path).
- Cron mode: `dummyindex council --schedule weekly` for managed re-enrichment.

## v1 — Once I'm done testing

Promoted from v0.16 once the user has exercised the full v0.9 → v0.16 stack on real repos.

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
