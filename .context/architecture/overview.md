# Architecture overview

Auto-derived from the directory layout and AST extraction. Heuristic role hints come from common directory naming patterns.

## Stack

- **Languages:** powershell, python, typescript
- **Files:** 312
- **Symbols:** 2453

## Top-level layout

| Path | Role (heuristic) | Files | Symbols | Languages |
|---|---|---:|---:|---|
| `dummyindex/` | _unknown_ | 203 | 910 | powershell, python |
| `scripts/` | operational scripts | 1 | 13 | python |
| `tests/` | test suite | 108 | 1530 | python, typescript |

## Documented architecture

These checked-in docs describe the architecture. **Advisory only** — the AST-derived layout above is the source of truth. Each doc carries a `confidence` from `source-docs/INDEX.md`; treat low-confidence entries as history.

- [`docs/specs/2026-06-10-parallel-council-dispatch-design.md`](../../docs/specs/2026-06-10-parallel-council-dispatch-design.md) (**DocConfidence.HIGH** — Parallel council dispatch — design)
- [`dummyindex/skills/audit/agents/architecture.md`](../../dummyindex/skills/audit/agents/architecture.md) (**DocConfidence.HIGH** — Architecture auditor — dummyindex audit panel)
- [`dummyindex/skills/council/00-overview.md`](../../dummyindex/skills/council/00-overview.md) (**DocConfidence.HIGH** — Council overview)
- [`dummyindex/skills/retrieval/00-overview.md`](../../dummyindex/skills/retrieval/00-overview.md) (**DocConfidence.HIGH** — Retrieval — PageIndex-style tree search)
- [`docs/guide/03-architecture.md`](../../docs/guide/03-architecture.md) (**DocConfidence.MEDIUM** — 03 — Architecture)
- [`docs/internal/specs/02-build-loop-overview.md`](../../docs/internal/specs/02-build-loop-overview.md) (**DocConfidence.MEDIUM** — 02 — Build-loop architecture overview)
- [`docs/internal/specs/2026-06-06-equip-v2-design.md`](../../docs/internal/specs/2026-06-06-equip-v2-design.md) (**DocConfidence.MEDIUM** — Equip v2 — codified, evolving toolkit engine)
- [`docs/specs/2026-06-10-equip-plugin-manager-design.md`](../../docs/specs/2026-06-10-equip-plugin-manager-design.md) (**DocConfidence.MEDIUM** — equip as a Claude plugin manager — design)
- [`docs/specs/2026-06-12-plan-plugin-annotation-design.md`](../../docs/specs/2026-06-12-plan-plugin-annotation-design.md) (**DocConfidence.MEDIUM** — Plan-time plugin annotation — design)
- [`docs/specs/2026-06-16-superpowers-default-wiring-design.md`](../../docs/specs/2026-06-16-superpowers-default-wiring-design.md) (**DocConfidence.MEDIUM** — Wire `superpowers` as a default plugin on dummyindex init)
- [`docs/internal/specs/01-session-memory-design.md`](../../docs/internal/specs/01-session-memory-design.md) (**DocConfidence.LOW** — 01 — Session-memory subsystem design)
- [`docs/specs/2026-06-08-auto-handoff-nudge-design.md`](../../docs/specs/2026-06-08-auto-handoff-nudge-design.md) (**DocConfidence.LOW** — Design — Auto-handoff nudge)
- [`docs/specs/2026-06-10-equip-plugin-usage-interview-design.md`](../../docs/specs/2026-06-10-equip-plugin-usage-interview-design.md) (**DocConfidence.LOW** — Equip plugin usage interview — design)
- [`docs/specs/2026-06-11-auto-council-drift-hook-design.md`](../../docs/specs/2026-06-11-auto-council-drift-hook-design.md) (**DocConfidence.LOW** — Design — Always-on, drift-triggered auto-council)
- [`docs/superpowers/specs/2026-06-17-audit-grounding-backlog-design.md`](../../docs/superpowers/specs/2026-06-17-audit-grounding-backlog-design.md) (**DocConfidence.LOW** — Audit grounding pack + backlog awareness — design)

## How to use this file

This is a fast-orienting overview. For specifics, walk `tree.json` for full hierarchy and consult `map/symbols.json` for exact line locations. Honor `conventions/naming.md` when adding new code in any of the directories above.
