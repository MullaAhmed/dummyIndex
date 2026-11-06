# Architecture overview

Auto-derived from the directory layout and AST extraction. Heuristic role hints come from common directory naming patterns.

## Stack

- **Languages:** powershell, python, typescript
- **Files:** 570
- **Symbols:** 5922

## Top-level layout

| Path | Role (heuristic) | Files | Symbols | Languages |
|---|---|---:|---:|---|
| `benchmarks/` | _unknown_ | 15 | 130 | python |
| `dummyindex/` | _unknown_ | 333 | 1994 | powershell, python |
| `scripts/` | operational scripts | 1 | 15 | python |
| `tests/` | test suite | 221 | 3783 | python, typescript |

## Documented architecture

These checked-in docs describe the architecture. **Advisory only** — the AST-derived layout above is the source of truth. Each doc carries a `confidence` from `source-docs/INDEX.md`; treat low-confidence entries as history.

- [`dummyindex/skills/audit/agents/architecture.md`](../../dummyindex/skills/audit/agents/architecture.md) (**high** — Architecture auditor — dummyindex audit panel)
- [`docs/guide/03-architecture.md`](../../docs/guide/03-architecture.md) (**medium** — 03 — Architecture)
- [`dummyindex/skills/retrieval/00-overview.md`](../../dummyindex/skills/retrieval/00-overview.md) (**medium** — Retrieval — PageIndex-style tree search)
- [`dummyindex/skills/council/00-overview.md`](../../dummyindex/skills/council/00-overview.md) (**low** — Council overview)

## How to use this file

This is a fast-orienting overview. For specifics, walk `tree.json` for full hierarchy and consult `map/symbols.json` for exact line locations. Honor `conventions/naming.md` when adding new code in any of the directories above.
