# Existing docs that touch `community-30`

_Pointer list — the canonical entries (with confidence + broken-references) live in `../../source-docs/INDEX.md`. **Treat doc claims as hypotheses; verify against `feature.json` + `../../map/symbols.json` before quoting.**_

- [`docs/internal/audits/audits/2026-06-13-full-audit-log.md`](../../../docs/internal/audits/audits/2026-06-13-full-audit-log.md) (**DocConfidence.MEDIUM** — Full audit — 2026-06-13 (overnight autonomous run)) _matched on:_ `path:tests/test_skills_doc_hygiene.py`
  - ⚠ broken refs: `docs/audits/2026-06-13-evidence/raw-findings.json`, `docs/audits/2026-06-13-REPORT.md`
- [`docs/plans/2026-06-10-equip-plugin-usage-interview.md`](../../../docs/plans/2026-06-10-equip-plugin-usage-interview.md) (**DocConfidence.MEDIUM** — Equip Plugin Usage Interview — Implementation Plan) _matched on:_ `symbol:run`
  - ⚠ broken refs: `grounded_in`, `missing_playbook`, `/tmp/usage-smoke/.context/equipment.json`
- [`docs/plans/2026-06-10-parallel-council-dispatch.md`](../../../docs/plans/2026-06-10-parallel-council-dispatch.md) (**DocConfidence.MEDIUM** — Parallel Council Dispatch Implementation Plan) _matched on:_ `symbol:run`
  - ⚠ broken refs: `council_batch`, `pyproject.toml`, `0.20.0`, … +3 more
- [`docs/plans/2026-06-11-auto-council-drift-hook.md`](../../../docs/plans/2026-06-11-auto-council-drift-hook.md) (**DocConfidence.MEDIUM** — Always-on Drift-Triggered Auto-Council — Implementation Plan) _matched on:_ `symbol:run`
  - ⚠ broken refs: `stop_hook_active`, `claude_settings`, `dummyindex.context`, … +13 more
- [`CHANGELOG.md`](../../../CHANGELOG.md) (**DocConfidence.LOW** — Changelog) _matched on:_ `symbol:bootstrap.py`
  - ⚠ broken refs: `.context/equipment.json`, `checklist.md`, `stop_hook_active`, … +120 more
- [`docs/reference/01-conventions.md`](../../../docs/reference/01-conventions.md) (**DocConfidence.LOW** — 01 — Conventions) _matched on:_ `symbol:run`
  - ⚠ broken refs: `_common.py`, `security.py`, `sanitize_label`, … +38 more
- [`docs/specs/2026-06-10-equip-plugin-usage-interview-design.md`](../../../docs/specs/2026-06-10-equip-plugin-usage-interview-design.md) (**DocConfidence.LOW** — Equip plugin usage interview — design) _matched on:_ `symbol:run`
  - ⚠ broken refs: `.claude/settings.json`, `grounded_in`, `project_root`, … +2 more
