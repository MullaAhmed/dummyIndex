# Phase 1.5 — Conventions (agent-derived)

After the deterministic backbone lands in `.context/`, you produce four
agent-authored docs alongside the statistically-derived
`conventions/naming.md`. These describe how the project actually wants new
code to be written — patterns Python can't read off the AST.

## What gets written

| File | Author (persona) | Section about |
|---|---|---|
| `conventions/folder-organization.md` | architect | How source is grouped into directories and where a new file should go |
| `conventions/coding-practices.md`    | senior-developer | DI style, error handling, async/sync, validation, dataclass/Protocol use |
| `conventions/testing.md`             | senior-developer | Framework, fixtures, mocks, unit vs integration vs e2e, coverage |
| `conventions/data-access.md`         | database-engineer | ORM vs raw, transactions, migrations, query placement, indexing |

The catalog lives in `dummyindex.context.build.conventions.CONVENTION_SECTIONS` —
add a section there, then add a row above. Naming.md is **deterministic**
(counted from the AST) and is NOT in this phase.

## When this phase runs

After Phase 1 (deterministic backbone) and before Phase 2 (structural
review). The architect's folder-organization output informs the
structural review.

Skip in mode `light` — light mode only refreshes `naming.md`.

## Dispatch pattern

These four are independent — fan them out in **parallel**. Read each
persona's `subagent_type` from its `agents/*.md` frontmatter; the council
defaults are listed in `skill.md`. Three dispatches (senior-developer
runs twice, once per section):

```
Task(architect)         → folder-organization.md
Task(senior-developer)  → coding-practices.md
Task(senior-developer)  → testing.md
Task(database-engineer) → data-access.md
```

Prompt template (adapt per section):

> You are the **<persona>**. Author
> `.context/conventions/<section>.md` for this repo.
>
> ## What to cover
>
> <CONVENTION_SECTIONS[section] from conventions.py>
>
> ## Inputs available
>
> - `.context/tree.json` — directory hierarchy.
> - `.context/map/files.json` and `.context/map/symbols.json` — every
>   file + every symbol with `path:range`.
> - `.context/conventions/naming.md` — statistically inferred naming.
> - Source files (read them — don't speculate).
>
> ## Output discipline
>
> - **Derive from the source.** Cite `path:range` for every claim.
> - **Describe what *this* project does**, not best-practice generalities.
>   "This repo uses Pydantic models at API boundaries and dataclasses
>   internally" beats "use type hints".
> - **One markdown page.** Headings, bullet rules, code excerpts from
>   actual files. ~400-600 words.
> - If the codebase is too small or inconsistent to derive a rule for
>   some sub-topic, say so explicitly — don't invent.
>
> ## When done
>
> Write your markdown to a tmp file, then place it atomically:
>
> ```
> dummyindex context conventions-write --section <section> --from-file /tmp/<section>.md
> ```

## Failure handling

If any of the four subagents fails, log a warning and continue with the
others — naming.md is already on disk so the conventions folder is never
empty. Re-running `/dummyindex` retries.

## After this phase

The four docs are referenced from `HOW_TO_USE.md` and become required
reading for any future Claude session that's writing code in this repo.
Proceed to Phase 2 (structural review).
