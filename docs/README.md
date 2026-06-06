# Documentation

The design & reference documentation for **dummyindex**. Every file follows one
naming rule — `NN-topic.md`, ordered by sequence, no dates in filenames (a doc's
date/status lives in its header). Each file opens with an `# NN — Title` heading.

> This `docs/` tree is *about* dummyindex. The skill markdown that actually runs
> at `/dummyindex` lives under [`../dummyindex/skills/`](../dummyindex/skills/)
> (`skill.md` + `council/`, `retrieval/`, `agents/`), and is numbered the same way.

## Brief — the guided tour (read in order)

| # | Doc | What it covers |
|---|-----|----------------|
| 01 | [brief/01-purpose.md](brief/01-purpose.md) | Why dummyindex exists |
| 02 | [brief/02-mental-model.md](brief/02-mental-model.md) | The mental model |
| 03 | [brief/03-architecture.md](brief/03-architecture.md) | Architecture |
| 04 | [brief/04-data-model.md](brief/04-data-model.md) | The `.context/` data model |
| 05 | [brief/05-council.md](brief/05-council.md) | The multi-agent council |
| 06 | [brief/06-personas.md](brief/06-personas.md) | Personas |
| 07 | [brief/07-cli.md](brief/07-cli.md) | CLI surface (every command) |
| 08 | [brief/08-skill.md](brief/08-skill.md) | Skill orchestration (the phases) |
| 09 | [brief/09-lifecycle.md](brief/09-lifecycle.md) | Lifecycle + drift (two modes: setup vs ongoing; build loop; session memory) |
| 10 | [brief/10-non-goals.md](brief/10-non-goals.md) | Non-goals |
| 11 | [brief/11-roadmap.md](brief/11-roadmap.md) | Roadmap |
| 12 | [brief/12-retrieval.md](brief/12-retrieval.md) | Retrieval model |

## Reference — the long-form contract

| # | Doc | What it covers |
|---|-----|----------------|
| 01 | [reference/01-conventions.md](reference/01-conventions.md) | Code organisation & style conventions (the contract) |

## Specs — design documents (point-in-time)

| # | Doc | Date |
|---|-----|------|
| 01 | [specs/01-session-memory-design.md](specs/01-session-memory-design.md) | 2026-06-05 |
| 02 | [specs/02-build-loop-overview.md](specs/02-build-loop-overview.md) | 2026-06-06 |
| 03 | [specs/03-build-loop-mvp-slices.md](specs/03-build-loop-mvp-slices.md) | 2026-06-06 |

## Plans — implementation plans (point-in-time)

| # | Doc | Date |
|---|-----|------|
| 01 | [plans/01-session-memory.md](plans/01-session-memory.md) | 2026-06-05 |

## Audits — point-in-time reviews

| # | Doc | Date |
|---|-----|------|
| 01 | [audits/01-dead-broken-incomplete.md](audits/01-dead-broken-incomplete.md) | 2026-06-05 (re-audited 2026-06-06) |

---

**Conventions for these docs:** numbered `NN-topic.md`; `# NN — Title` H1; specs/
plans/audits carry their date in a header line (`**Date:** …`), not the filename.
When a doc disagrees with the code, the code wins — fix the doc.
