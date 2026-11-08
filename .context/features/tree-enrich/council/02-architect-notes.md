# Architect notes — Tree abstract enrichment

## What I changed

- Sections: mapped the draft's Bounded context / Plan-author-apply / Dependencies and feedback / Decisions and limits / Verification seam onto the dev template (Where it lives / Architecture in three sentences / Data model / Key decisions / Open questions), adding Patterns named + Dependencies surfaced per in-repo precedent (`codex-guidance/plan.md`, `audit-panel/plan.md`). 95 → 82 lines, 5178 → 5173 bytes (LF).
- Where it lives: cut the ownership prose to three bullets; dropped the `test_query.py` aside; test coverage collapsed to `tests/context/domains/test_enrich.py:35-296` plus one "Untested" open question.
- Architecture: three sentences replace the three numbered steps; per-node no-op and "not a transaction" wording moved to Key decisions or dropped.
- Dependencies: added two edges the draft missed — `refresh_tree` as the sole `source-stale` producer (`dummyindex/context/build/navigation_refresh.py:133-153`) and `estimate_run` as a second Python consumer of `build_plan` (`dummyindex/context/domains/fleet.py:436`, `:448-460`).
- Light-mode contradiction: re-framed with code-wins. `active_stages` appends `CouncilStage.TREE` in every mode (`dummyindex/context/domains/council_batch.py:78-79`), default-on at `dummyindex/cli/council_batch.py:105-108`, so the "light skips" prose (`dummyindex/skills/skill.md:334`, `dummyindex/skills/council/52-tree-enrich.md:41`) is the stale side. Which node kinds light authors is still undocumented.
- Doc/code conflict flagged: `dummyindex/skills/skill.md:334-335` and `spec.md` "Mode gating" both put files in the `structure` batch; code puts only project/dir there (`dummyindex/context/domains/enrich.py:133-137`). `spec.md` left untouched (read-only).
- Convention divergences surfaced (new): fixed `<name>.tmp` writes (`dummyindex/context/domains/enrich.py:188-190`, `:224-226`) vs unique-temp `write_text_atomic` (`.context/conventions/data-access.md:7`); `range: list` / `stats: dict` vs the tuple-only frozen rule (`.context/conventions/coding-practices.md:10-12`); uncaught `json.loads` (`dummyindex/cli/enrich.py:103`) vs the wire-only CLI rule (`.context/conventions/coding-practices.md:55-62`).
- Data model: replaced the restated JSON shapes with a pointer to `spec.md` Contracts plus the node-field read/write ranges.
- Doc evidence: `docs.md` lists only MEDIUM-confidence docs, all off-topic cluster matches (the `_apply` hit on the 2026-06-13 audit log is a name collision). None quoted.
- Symbol check: every named symbol exists in `map/symbols.json` (`EnrichNode`, `EnrichBatch`, `EnrichPlan`, `ApplyResult`, `build_plan`, `write_plan`, `apply_updates`, `_walk`, `run_plan`, `run_apply`, `migrate_context_layout`, `LayoutMigration`, `refresh_tree`, `write_tree`, `estimate_run`, `active_stages`, `ConfidenceLevel`, `CouncilStage`, `write_text_atomic`). `RETIRED_CONTEXT_PATHS` is not in the map, so it is cited only by range. Every kept range was re-read against HEAD source.
- Corrected the previous notes' stale cite `enrich.py:120-123` → `:116-120`. Single-shot reasoning; no Sequential Thinking MCP.

## Patterns named

- Table dispatcher at `dummyindex/cli/__init__.py:100-101` (`ContextSubcommand.ENRICH_PLAN/ENRICH_APPLY` → `enrich.run_plan/run_apply`); consumed, not owned.
- Two-phase plan/apply via a file hand-off: `write_plan` at `dummyindex/context/domains/enrich.py:185-190` → host authoring (`dummyindex/skills/council/52-tree-enrich.md:49-76`) → `apply_updates` at `dummyindex/context/domains/enrich.py:207-227`.
- Wire-only CLI handler at `dummyindex/cli/enrich.py:12-126`, except `:103`.
- Frozen records + `to_dict()` at `dummyindex/context/domains/enrich.py:31-90`, `:193-204`.
- Hand-rolled tmp+`replace` writer at `dummyindex/context/domains/enrich.py:188-190`, `:224-226`.
- Pre-order generator walk at `dummyindex/context/domains/enrich.py:233-242`; it appears in Architecture rather than in its own bullet.

## Dependencies surfaced

- Upstream code: `ConfidenceLevel` (`dummyindex/pipeline/enums.py:17`) is the domain's only first-party import (`dummyindex/context/domains/enrich.py:17-26`). The CLI also imports `parse_path_and_root` / `resolve_context_root` (`dummyindex/cli/common.py:123`, `:13`) and `migrate_context_layout` (`dummyindex/context/build/upgrade.py:542-593`).
- Upstream data: `write_tree` seeds `EXTRACTED` stubs (`dummyindex/context/build/runner.py:394`). `refresh_tree` (`dummyindex/context/build/navigation_refresh.py:75-158`, called at `dummyindex/context/build/enriched_refresh.py:174` on the `rebuild_changed` path) carries annotated abstracts forward and adds `source-stale` (`:150-153`).
- Downstream code: dispatcher (`dummyindex/cli/__init__.py:100-101`). `estimate_run` (`dummyindex/context/domains/fleet.py:415`) imports `build_plan` and counts `plan.nodes`, which couples the selection predicate to fleet estimates. Tested at `tests/context/domains/test_fleet.py:220`.
- Downstream orchestration: `active_stages` (`dummyindex/context/domains/council_batch.py:65-80`) schedules `CouncilStage.TREE`, and Phase 4.5 in `dummyindex/skills/skill.md:320-340` drives the verbs.
- Cycles: none at import level; only `dummyindex/cli/enrich.py` and `dummyindex/context/domains/fleet.py` import the domain. There is a data cycle through `tree.json`: apply → `INFERRED` → `refresh_tree` flags drift → `build_plan` reselects → apply clears `source-stale`.

## Decisions promoted

- decided per-file batches because partial progress must survive an interrupted session (was implicit at `dummyindex/context/domains/enrich.py:6-9`).
- decided `source-stale` overrides confidence in selection because `refresh_tree` preserves annotated abstracts and flags drift instead of resetting them (was implicit at `dummyindex/context/domains/enrich.py:116-120` + `dummyindex/context/build/navigation_refresh.py:78`, `:133-153`).
- decided `enrich-plan` runs the layout migration because reconcile-only repos never run a full build, with `package_version=None` because it does not extract (was implicit at `dummyindex/cli/enrich.py:33-40`).
- decided the plan is gitignored scratch under `cache/` (was implicit at `dummyindex/cli/enrich.py:33-35`).
- decided unknown IDs are reported, not rejected, because they are likely typos for the skill to surface (was implicit at `dummyindex/context/domains/enrich.py:199-200`).
- decided apply is idempotent per node (was implicit at `dummyindex/context/domains/enrich.py:13-14`, `:273-276`).
- decided mode scoping belongs to the host, for cost control (was implicit at `dummyindex/skills/council/52-tree-enrich.md:34-47`).
- Not promoted, because no rationale exists in code or docs: the fixed `.tmp` name and the discarded `LayoutMigration`. Both are left as divergence or open question.
