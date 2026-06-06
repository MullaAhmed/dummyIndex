# Documentation

Public documentation for **dummyindex** — the persistent context engine for AI coding agents.

> The skill markdown that drives `/dummyindex` lives under
> [`../dummyindex/skills/`](../dummyindex/skills/) (`skill.md` + `council/`,
> `retrieval/`, `agents/`). This tree is about dummyindex, not the runnable skill.

---

## Guide — conceptual docs (read in order)

The twelve-doc tour of how dummyindex works, why it was designed this way,
and what it deliberately does not do.

| # | Doc | What it covers |
|---|-----|----------------|
| 01 | [guide/01-purpose.md](guide/01-purpose.md) | Why dummyindex exists |
| 02 | [guide/02-mental-model.md](guide/02-mental-model.md) | The mental model |
| 03 | [guide/03-architecture.md](guide/03-architecture.md) | Architecture |
| 04 | [guide/04-data-model.md](guide/04-data-model.md) | The `.context/` data model |
| 05 | [guide/05-council.md](guide/05-council.md) | The multi-agent council |
| 06 | [guide/06-personas.md](guide/06-personas.md) | Personas |
| 07 | [guide/07-cli.md](guide/07-cli.md) | CLI surface (every command) |
| 08 | [guide/08-skill.md](guide/08-skill.md) | Skill orchestration (the phases) |
| 09 | [guide/09-lifecycle.md](guide/09-lifecycle.md) | Lifecycle + drift (two modes: setup vs ongoing; build loop; session memory) |
| 10 | [guide/10-non-goals.md](guide/10-non-goals.md) | Non-goals |
| 11 | [guide/11-roadmap.md](guide/11-roadmap.md) | Roadmap |
| 12 | [guide/12-retrieval.md](guide/12-retrieval.md) | Retrieval model |

Start at [guide/README.md](guide/README.md) for the one-page summary.

---

## Reference — the long-form contract

| # | Doc | What it covers |
|---|-----|----------------|
| 01 | [reference/01-conventions.md](reference/01-conventions.md) | Code organisation & style conventions (the contract) |

---

## Internal

`internal/` holds build-phase artifacts — design specs, implementation plans, and audits. They are working documents, not user documentation, and are **untracked** (`docs/internal/` is gitignored): they exist only in local working copies, so a fresh clone won't have this folder.
