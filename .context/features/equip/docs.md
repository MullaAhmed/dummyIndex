# Existing docs that touch `community-1`

_Pointer list — the canonical entries (with confidence + broken-references) live in `../../source-docs/INDEX.md`. **Treat doc claims as hypotheses; verify against `feature.json` + `../../map/symbols.json` before quoting.**_

- [`dummyindex/skills/council/00-overview.md`](../../../dummyindex/skills/council/00-overview.md) (**DocConfidence.HIGH** — Council overview) _matched on:_ `symbol:refresh`
- [`dummyindex/skills/council/19-resume.md`](../../../dummyindex/skills/council/19-resume.md) (**DocConfidence.HIGH** — Resumption — pick up where we left off) _matched on:_ `symbol:refresh`
- [`docs/internal/plans/01-session-memory.md`](../../../docs/internal/plans/01-session-memory.md) (**DocConfidence.MEDIUM** — 01 — Session-memory implementation plan) _matched on:_ `path:dummyindex/context/enums.py, symbol:write_text_atomic`
  - ⚠ broken refs: `docs/specs/01-session-memory-design.md`, `ValueError`, `SessionMemoryError`, … +12 more
- [`docs/internal/plans/2026-06-06-equip-v2.md`](../../../docs/internal/plans/2026-06-06-equip-v2.md) (**DocConfidence.MEDIUM** — Equip v2 Implementation Plan) _matched on:_ `path:dummyindex/context/claude_settings.py, symbol:apply_patch`
  - ⚠ broken refs: `docs/specs/2026-06-06-equip-v2-design.md`, `docs/CONVENTIONS.md`, `dummyindex/context/domains/equip/hookwire.py`, … +28 more
- [`docs/internal/specs/03-build-loop-mvp-slices.md`](../../../docs/internal/specs/03-build-loop-mvp-slices.md) (**DocConfidence.MEDIUM** — 03 — Build-loop MVP slices) _matched on:_ `path:dummyindex/context/enums.py, symbol:write_text_atomic`
  - ⚠ broken refs: `docs/specs/02-build-loop-overview.md`, `proposal.json`, `checklist.md`, … +11 more
- [`docs/internal/specs/2026-06-06-equip-v2-design.md`](../../../docs/internal/specs/2026-06-06-equip-v2-design.md) (**DocConfidence.MEDIUM** — Equip v2 — codified, evolving toolkit engine) _matched on:_ `path:dummyindex/context/claude_settings.py, symbol:StackProfile`
  - ⚠ broken refs: `uv.lock`, `format_command`, `proposal_capabilities`, … +6 more
- [`docs/plans/2026-06-10-equip-plugin-manager.md`](../../../docs/plans/2026-06-10-equip-plugin-manager.md) (**DocConfidence.MEDIUM** — equip Plugin Manager Implementation Plan) _matched on:_ `path:dummyindex/context/domains/equip/__init__.py, symbol:match_candidates`
  - ⚠ broken refs: `Runner`, `.context/equipment.json`, `.claude/settings.json`, … +29 more
- [`docs/plans/2026-06-10-equip-plugin-usage-interview.md`](../../../docs/plans/2026-06-10-equip-plugin-usage-interview.md) (**DocConfidence.MEDIUM** — Equip Plugin Usage Interview — Implementation Plan) _matched on:_ `path:dummyindex/context/domains/equip/lifecycle/status.py, symbol:to_dict`
  - ⚠ broken refs: `grounded_in`, `missing_playbook`, `/tmp/usage-smoke/.context/equipment.json`
- [`docs/plans/2026-06-10-parallel-council-dispatch.md`](../../../docs/plans/2026-06-10-parallel-council-dispatch.md) (**DocConfidence.MEDIUM** — Parallel Council Dispatch Implementation Plan) _matched on:_ `path:dummyindex/context/enums.py`
  - ⚠ broken refs: `council_batch`, `pyproject.toml`, `0.20.0`, … +3 more
- [`docs/plans/2026-06-11-auto-council-drift-hook.md`](../../../docs/plans/2026-06-11-auto-council-drift-hook.md) (**DocConfidence.MEDIUM** — Always-on Drift-Triggered Auto-Council — Implementation Plan) _matched on:_ `path:dummyindex/context/enums.py, symbol:MalformedSettingsError`
  - ⚠ broken refs: `stop_hook_active`, `claude_settings`, `dummyindex.context`, … +13 more

_… +20 more in [`../../source-docs/INDEX.md`](../../source-docs/INDEX.md)._
