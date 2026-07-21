# Existing documentation (source-docs)

> **Advisory — verify before quoting.** This catalog is generated from prose checked into the repo. Docs drift faster than code. Every entry carries a `confidence` (high / medium / low) derived from how many of its backticked code references still match the current AST. Treat high-confidence docs as hypotheses worth quoting; cross-check medium-confidence docs against `../map/symbols.json` and `../tree.json`; treat low-confidence docs as historical context only.

_63 doc(s) — 5 high · 29 medium · 29 low._

| Doc | Type | Confidence | Broken refs | Age |
|---|---|---|---|---|
| [`docs/guide/01-purpose.md`](../../docs/guide/01-purpose.md) — 01 — Purpose | markdown | **high** | 0 / 5 | recent |
| [`docs/guide/05-council.md`](../../docs/guide/05-council.md) — 05 — Multi-agent council | markdown | **high** | 1 / 19 | recent |
| [`docs/guide/10-non-goals.md`](../../docs/guide/10-non-goals.md) — 10 — Non-goals | markdown | **high** | 0 / 3 | recent |
| [`docs/guide/12-retrieval.md`](../../docs/guide/12-retrieval.md) — 12 — Retrieval model | markdown | **high** | 2 / 21 | recent |
| [`dummyindex/skills/audit/agents/over-engineering.md`](../../dummyindex/skills/audit/agents/over-engineering.md) — Over-engineering auditor — dummyindex audit panel | markdown | **high** | — | recent |
| [`CONTRIBUTING.md`](../../CONTRIBUTING.md) — Contributing to dummyindex | markdown | **medium** | 2 / 2 | fresh |
| [`README.md`](../../README.md) — dummyindex | markdown | **medium** | 3 / 4 | recent |
| [`docs/README.md`](../../docs/README.md) — Documentation | markdown | **medium** | 1 / 1 | recent |
| [`docs/guide/02-mental-model.md`](../../docs/guide/02-mental-model.md) — 02 — Mental model | markdown | **medium** | 1 / 1 | recent |
| [`docs/guide/03-architecture.md`](../../docs/guide/03-architecture.md) — 03 — Architecture | markdown | **medium** | 9 / 24 | recent |
| [`docs/guide/04-data-model.md`](../../docs/guide/04-data-model.md) — 04 — `.context/` data model | markdown | **medium** | 6 / 44 | recent |
| [`dummyindex/skills/agents/architect.md`](../../dummyindex/skills/agents/architect.md) — Software Architect — dummyindex council persona | markdown | **medium** | 2 / 14 | aging |
| [`dummyindex/skills/agents/critic-database.md`](../../dummyindex/skills/agents/critic-database.md) — Database critic — dummyindex concerns-only persona | markdown | **medium** | 1 / 7 | aging |
| [`dummyindex/skills/agents/critic-product.md`](../../dummyindex/skills/agents/critic-product.md) — No PM-specific subagent is assumed on either host. The persona instructions | markdown | **medium** | 1 / 6 | recent |
| [`dummyindex/skills/agents/dev.md`](../../dummyindex/skills/agents/dev.md) — subagent_type resolved per-feature via `dummyindex context dev-pick`; | markdown | **medium** | 1 / 9 | aging |
| [`dummyindex/skills/audit/agents/architecture.md`](../../dummyindex/skills/audit/agents/architecture.md) — Architecture auditor — dummyindex audit panel | markdown | **medium** | — | aging |
| [`dummyindex/skills/audit/agents/correctness.md`](../../dummyindex/skills/audit/agents/correctness.md) — Correctness auditor — dummyindex audit panel | markdown | **medium** | — | aging |
| [`dummyindex/skills/audit/agents/data-integrity.md`](../../dummyindex/skills/audit/agents/data-integrity.md) — Data-integrity auditor — dummyindex audit panel | markdown | **medium** | — | aging |
| [`dummyindex/skills/audit/agents/maintainability.md`](../../dummyindex/skills/audit/agents/maintainability.md) — Maintainability auditor — dummyindex audit panel | markdown | **medium** | — | aging |
| [`dummyindex/skills/audit/agents/performance.md`](../../dummyindex/skills/audit/agents/performance.md) — Performance auditor — dummyindex audit panel | markdown | **medium** | — | aging |
| [`dummyindex/skills/audit/agents/security.md`](../../dummyindex/skills/audit/agents/security.md) — Security auditor — dummyindex audit panel | markdown | **medium** | — | aging |
| [`dummyindex/skills/audit/agents/tests.md`](../../dummyindex/skills/audit/agents/tests.md) — Test-coverage auditor — dummyindex audit panel | markdown | **medium** | 1 / 1 | aging |
| [`dummyindex/skills/council/10-structural-review.md`](../../dummyindex/skills/council/10-structural-review.md) — Structural review (pre-stage) | markdown | **medium** | 1 / 9 | recent |
| [`dummyindex/skills/council/18-filter-trivial.md`](../../dummyindex/skills/council/18-filter-trivial.md) — Trivial-feature filter → consolidation decision | markdown | **medium** | 8 / 28 | aging |
| [`dummyindex/skills/council/19-resume.md`](../../dummyindex/skills/council/19-resume.md) — Resumption — pick up where we left off | markdown | **medium** | 0 / 1 | aging |
| [`dummyindex/skills/council/20-specify.md`](../../dummyindex/skills/council/20-specify.md) — Stage 1 — `/specify` (dev drafts spec.md + plan.md) | markdown | **medium** | 4 / 11 | aging |
| [`dummyindex/skills/council/22-parallel-dispatch.md`](../../dummyindex/skills/council/22-parallel-dispatch.md) — Parallel dispatch — the council batch loop | markdown | **medium** | 0 / 1 | aging |
| [`dummyindex/skills/council/30-plan.md`](../../dummyindex/skills/council/30-plan.md) — Stage 2 — `/plan` (architect reorganises plan.md) | markdown | **medium** | 3 / 11 | aging |
| [`dummyindex/skills/council/50-flow-narrative.md`](../../dummyindex/skills/council/50-flow-narrative.md) — Flow refinement — keep, discard, narrate | markdown | **medium** | 1 / 8 | aging |
| [`dummyindex/skills/council/60-doc-reorg.md`](../../dummyindex/skills/council/60-doc-reorg.md) — Doc reorg — reorganise the repo's real docs in place (DESTRUCTIVE, opt-in) | markdown | **medium** | 1 / 6 | aging |
| [`dummyindex/skills/gc/SKILL.md`](../../dummyindex/skills/gc/SKILL.md) — /dummyindex-gc / $dummyindex-gc — context-hygiene GC council sweep | markdown | **medium** | 3 / 19 | recent |
| [`dummyindex/skills/retrieval/00-overview.md`](../../dummyindex/skills/retrieval/00-overview.md) — Retrieval — PageIndex-style tree search | markdown | **medium** | 3 / 13 | recent |
| [`dummyindex/skills/retrieval/10-feature-lookup.md`](../../dummyindex/skills/retrieval/10-feature-lookup.md) — Feature lookup | markdown | **medium** | 3 / 9 | aging |
| [`dummyindex/skills/retrieval/20-symbol-lookup.md`](../../dummyindex/skills/retrieval/20-symbol-lookup.md) — Symbol lookup | markdown | **medium** | 3 / 8 | aging |
| [`CHANGELOG.md`](../../CHANGELOG.md) — Changelog | markdown | **low** | 153 / 293 | fresh |
| [`SECURITY.md`](../../SECURITY.md) — Security Policy | markdown | **low** | 4 / 8 | fresh |
| [`docs/COMMANDS.md`](../../docs/COMMANDS.md) — Commands | markdown | **low** | 15 / 23 | recent |
| [`docs/guide/06-personas.md`](../../docs/guide/06-personas.md) — 06 — Personas | markdown | **low** | 8 / 18 | recent |
| [`docs/guide/07-cli.md`](../../docs/guide/07-cli.md) — 07 — CLI surface | markdown | **low** | 47 / 88 | recent |
| [`docs/guide/08-skill.md`](../../docs/guide/08-skill.md) — 08 — Skill orchestration | markdown | **low** | 6 / 14 | recent |
| [`docs/guide/09-lifecycle.md`](../../docs/guide/09-lifecycle.md) — 09 — Lifecycle | markdown | **low** | 12 / 27 | recent |
| [`docs/guide/11-roadmap.md`](../../docs/guide/11-roadmap.md) — 11 — Roadmap | markdown | **low** | 31 / 52 | fresh |
| [`docs/guide/README.md`](../../docs/guide/README.md) — dummyindex — Conceptual Guide | markdown | **low** | 4 / 7 | recent |
| [`docs/reference/01-conventions.md`](../../docs/reference/01-conventions.md) — 01 — Conventions | markdown | **low** | 41 / 90 | recent |
| [`docs/sources/installable-sources.md`](../../docs/sources/installable-sources.md) — Installable sources catalog | markdown | **low** | 5 / 7 | recent |
| [`dummyindex/skills/agents/critic-security.md`](../../dummyindex/skills/agents/critic-security.md) — Security critic — dummyindex concerns-only persona | markdown | **low** | 5 / 10 | aging |
| [`dummyindex/skills/audit/SKILL.md`](../../dummyindex/skills/audit/SKILL.md) — /dummyindex-audit / $dummyindex-audit — argue-and-audit panel | markdown | **low** | 6 / 7 | recent |
| [`dummyindex/skills/council/00-overview.md`](../../dummyindex/skills/council/00-overview.md) — Council overview | markdown | **low** | 9 / 15 | aging |
| [`dummyindex/skills/council/05-onboarding.md`](../../dummyindex/skills/council/05-onboarding.md) — Onboarding (first run only) | markdown | **low** | 8 / 9 | recent |
| [`dummyindex/skills/council/15-conventions.md`](../../dummyindex/skills/council/15-conventions.md) — Phase 1.5 — Conventions (agent-derived) | markdown | **low** | 20 / 30 | recent |
| [`dummyindex/skills/council/40-critique.md`](../../dummyindex/skills/council/40-critique.md) — Stage 3 — `/critique` (critics file concerns, mode-gated) | markdown | **low** | 5 / 12 | aging |
| [`dummyindex/skills/council/45-reality-check.md`](../../dummyindex/skills/council/45-reality-check.md) — Phase 3.5 — Reality check | markdown | **low** | 7 / 14 | aging |
| [`dummyindex/skills/council/52-tree-enrich.md`](../../dummyindex/skills/council/52-tree-enrich.md) — Phase 4.5 — Tree enrichment (node abstracts) | markdown | **low** | 8 / 12 | aging |
| [`dummyindex/skills/council/55-context7.md`](../../dummyindex/skills/council/55-context7.md) — Context7 lookup protocol (MCP companion) | markdown | **low** | 14 / 16 | aging |
| [`dummyindex/skills/council/56-github.md`](../../dummyindex/skills/council/56-github.md) — GitHub release-check protocol (MCP companion) | markdown | **low** | 12 / 12 | aging |
| [`dummyindex/skills/council/65-reconcile.md`](../../dummyindex/skills/council/65-reconcile.md) — Reconcile — fold a commit delta into the curated index | markdown | **low** | 9 / 11 | recent |
| [`dummyindex/skills/equip/SKILL.md`](../../dummyindex/skills/equip/SKILL.md) — /dummyindex-equip / $dummyindex-equip — equip the project with a tuned, evolving toolkit | markdown | **low** | 10 / 16 | recent |
| [`dummyindex/skills/memory/SKILL.md`](../../dummyindex/skills/memory/SKILL.md) — /dummyindex-remember / $dummyindex-remember — save the session into `.context/session-memory/` | markdown | **low** | 4 / 4 | recent |
| [`dummyindex/skills/plan/SKILL.md`](../../dummyindex/skills/plan/SKILL.md) — /dummyindex-plan / $dummyindex-plan — Grounded planning | markdown | **low** | 8 / 14 | recent |
| [`dummyindex/skills/retrieval/30-flow-trace.md`](../../dummyindex/skills/retrieval/30-flow-trace.md) — Flow trace | markdown | **low** | 7 / 15 | aging |
| [`dummyindex/skills/skill.md`](../../dummyindex/skills/skill.md) — /dummyindex / $dummyindex — The context engine orchestrator | markdown | **low** | 39 / 66 | recent |
| [`dummyindex/skills/update/SKILL.md`](../../dummyindex/skills/update/SKILL.md) — /dummyindex-update / $dummyindex-update [&lt;version|tag&gt;] — Update (or pin) dummyindex | markdown | **low** | 7 / 10 | recent |
| [`tests/eval/BASELINE.md`](../../tests/eval/BASELINE.md) — Retrieval eval baseline | markdown | **low** | 8 / 15 | recent |

## Low-confidence docs

These have broken references or are significantly older than the newest code change. Don't quote without verifying against current source.

### `CHANGELOG.md`

**Broken references** (no longer in the AST):

- `project_doc_max_bytes`
- `.context/equipment.json`
- `checklist.md`
- `stop_hook_active`
- `.context/config.json`
- `grounded_in`
- `council/22-parallel-dispatch.md`
- `dev_pick`
- `lifecycle.py`
- `cli/_usage.py`
- _… +143 more_

### `SECURITY.md`

**Broken references** (no longer in the AST):

- `escapeHtml()`
- `sanitize_label`
- `doc_guard_enabled`
- `doc_guard_allow`

### `docs/COMMANDS.md`

**Broken references** (no longer in the AST):

- `sonnet-4.6`
- `stop_hook_active`
- `.claude/settings.json`
- `.context/config.json`
- `.context/debt.md`
- `now.md`
- `.context/equipment.json`
- `checklist.md`
- `equipment.json`
- `settings.json`
- _… +5 more_

### `docs/guide/06-personas.md`

**Broken references** (no longer in the AST):

- `pyproject.toml`
- `package.json`
- `Cargo.toml`
- `pom.xml`
- `go.mod`
- `app/api/route.ts`
- `council/55-context7.md`
- `45-reality-check.md`

### `docs/guide/07-cli.md`

**Broken references** (no longer in the AST):

- `sonnet-4.6`
- `AGENTS.override.md`
- `AGENTS.md`
- `README.md`
- `meta.indexed_commit`
- `stop_hook_active`
- `session_id`
- `transcript_path`
- `.context/config.json`
- `.claude/settings.json`
- _… +37 more_

### `docs/guide/08-skill.md`

**Broken references** (no longer in the AST):

- `SKILL.md`
- `report.md`
- `agents/dev.md`
- `agents/architect.md`
- `council/55-context7.md`
- `skills/agents/dev.md`

### `docs/guide/09-lifecycle.md`

**Broken references** (no longer in the AST):

- `AGENTS.override.md`
- `AGENTS.md`
- `meta.indexed_commit`
- `equipment.json`
- `.claude/settings.json`
- `now.md`
- `doc_guard_enabled`
- `doc_guard_allow`
- `council/52-tree-enrich.md`
- `awaiting_enrichment`
- _… +2 more_

### `docs/guide/11-roadmap.md`

**Broken references** (no longer in the AST):

- `docs/reference/01-conventions.md`
- `to_obsidian`
- `to_canvas`
- `to_cypher`
- `flow-NNN.md`
- `dummyindex.context.drift`
- `README.md`
- `.context/config.json`
- `config.json`
- `council/20-specify.md`
- _… +21 more_

### `docs/guide/README.md`

**Broken references** (no longer in the AST):

- `.claude/settings.json`
- `now.md`
- `recent.md`
- `archive.md`

### `docs/reference/01-conventions.md`

**Broken references** (no longer in the AST):

- `_common.py`
- `security.py`
- `sanitize_label`
- `export.to_html`
- `to_html`
- `_html_assets.py`
- `snake_case`
- `PascalCase`
- `self._cache`
- `build_from_json`
- _… +31 more_

### `docs/sources/installable-sources.md`

**Broken references** (no longer in the AST):

- `.claude-plugin/marketplace.json`
- `.claude/settings.json`
- `skills.sh`
- `SKILL.md`
- `marketplace.json`

### `dummyindex/skills/agents/critic-security.md`

**Broken references** (no longer in the AST):

- `pyproject.toml`
- `package.json`
- `pom.xml`
- `council/55-context7.md`
- `council/56-github.md`

### `dummyindex/skills/audit/SKILL.md`

**Broken references** (no longer in the AST):

- `report.md`
- `audit.json`
- `description.md`
- `catalog.json`
- `persona_id`
- `max_rounds`

### `dummyindex/skills/council/00-overview.md`

**Broken references** (no longer in the AST):

- `20-specify.md`
- `30-plan.md`
- `40-critique.md`
- `50-flow-narrative.md`
- `agents/dev.md`
- `agents/architect.md`
- `agents/critic-database.md`
- `agents/critic-security.md`
- `agents/critic-product.md`

### `dummyindex/skills/council/05-onboarding.md`

**Broken references** (no longer in the AST):

- `.context/config.json`
- `AskUserQuestion`
- `opus-4.8`
- `sonnet-4.6`
- `haiku-4.5`
- `AGENTS.override.md`
- `AGENTS.md`
- `.claude/settings.json`

### `dummyindex/skills/council/15-conventions.md`

**Broken references** (no longer in the AST):

- `conventions/folder-organization.md`
- `conventions/coding-practices.md`
- `conventions/testing.md`
- `conventions/data-access.md`
- `dummyindex.context.build.conventions.CONVENTION_SECTIONS`
- `AGENTS.override.md`
- `AGENTS.md`
- `rule_files`
- `CONVENTIONS.md`
- `coding-practices.md`
- _… +10 more_

### `dummyindex/skills/council/40-critique.md`

**Broken references** (no longer in the AST):

- `agents/critic-database.md`
- `agents/critic-security.md`
- `agents/critic-product.md`
- `45-reality-check.md`
- `50-flow-narrative.md`

### `dummyindex/skills/council/45-reality-check.md`

**Broken references** (no longer in the AST):

- `UserService.authenticate()`
- `JWTValidator.verify()`
- `TokenService.check_signature()`
- `_reality-check.md`
- `select_related`
- `Depends`
- `council/55-context7.md`

### `dummyindex/skills/council/52-tree-enrich.md`

**Broken references** (no longer in the AST):

- `total_nodes`
- `stub_nodes`
- `by_kind`
- `file_subtree`
- `stub_abstract`
- `evidence_files`
- `stats.stub_nodes`
- `skill.md`

### `dummyindex/skills/council/55-context7.md`

**Broken references** (no longer in the AST):

- `select_related`
- `Depends`
- `pyproject.toml`
- `package.json`
- `pom.xml`
- `go.mod`
- `council/15-conventions.md`
- `coding-practices.md`
- `testing.md`
- `agents/dev.md`
- _… +4 more_

### `dummyindex/skills/council/56-github.md`

**Broken references** (no longer in the AST):

- `search_repositories`
- `get_latest_release`
- `list_releases`
- `get_release_by_tag`
- `pyproject.toml`
- `package.json`
- `pom.xml`
- `go.mod`
- `X.Y`
- `A.B`
- _… +2 more_

### `dummyindex/skills/council/65-reconcile.md`

**Broken references** (no longer in the AST):

- `meta.indexed_commit`
- `indexed_commit`
- `awaiting_enrichment`
- `unassigned_new_files`
- `drifted_features`
- `removed_files`
- `18-filter-trivial.md`
- `dirty_source`
- `working_tree_dirty`

### `dummyindex/skills/equip/SKILL.md`

**Broken references** (no longer in the AST):

- `checklist.md`
- `.context/equipment.json`
- `.claude/settings.json`
- `origin_hash`
- `grounded_in`
- `settings.json`
- `patch.json`
- `SKILL.md`
- `case_id`
- `expects_trigger`

### `dummyindex/skills/memory/SKILL.md`

**Broken references** (no longer in the AST):

- `now.md`
- `core-memories.md`
- `recent.md`
- `archive.md`

### `dummyindex/skills/plan/SKILL.md`

**Broken references** (no longer in the AST):

- `checklist.md`
- `proposal.json`
- `related_features`
- `reused_symbols`
- `.context/equipment.json`
- `Wave`
- `Group`
- `DECISIONS.md`

### `dummyindex/skills/retrieval/30-flow-trace.md`

**Broken references** (no longer in the AST):

- `20-symbol-lookup.md`
- `10-feature-lookup.md`
- `login()`
- `handle_login()`
- `checkout()`
- `place_order()`
- `entry_points`

### `dummyindex/skills/skill.md`

**Broken references** (no longer in the AST):

- `.context/config.json`
- `council/05-onboarding.md`
- `council/15-conventions.md`
- `council/22-parallel-dispatch.md`
- `council/45-reality-check.md`
- `council/52-tree-enrich.md`
- `council/00-overview.md`
- `council/10-structural-review.md`
- `council/20-specify.md`
- `council/30-plan.md`
- _… +29 more_

### `dummyindex/skills/update/SKILL.md`

**Broken references** (no longer in the AST):

- `0.24.0`
- `v0.24.0`
- `AGENTS.override.md`
- `AGENTS.md`
- `dummyindex_version`
- `.context/equipment.json`
- `build_all`

### `tests/eval/BASELINE.md`

**Broken references** (no longer in the AST):

- `build_all`
- `retrieval_fixtures.json`
- `negative_control`
- `expected_feature_id`
- `expected_path`
- `total_estimated_tokens`
- `1.0`
- `0.85`
