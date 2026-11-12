# Phase 1.5 — Conventions (agent-derived)

After the deterministic backbone lands in `.context/`, you produce four
agent-authored docs alongside the statistically-derived
`conventions/naming.md`. These describe how the project wants new
code to be written — patterns that Python cannot read off the AST.

## What gets written

| File | Author (persona) | Section about |
|---|---|---|
| `conventions/folder-organization.md` | architect | How source is grouped into directories and where a new file should go |
| `conventions/coding-practices.md`    | dev (generic-senior branch) | DI style, error handling, async/sync, validation, dataclass/Protocol use |
| `conventions/testing.md`             | dev (generic-senior branch) | Framework, fixtures, mocks, unit vs integration vs e2e, coverage |
| `conventions/data-access.md`         | critic-database | ORM vs raw, transactions, migrations, query placement, indexing |

The catalog lives in `dummyindex.context.build.conventions.CONVENTION_SECTIONS` —
add a section there, then add a row above. Naming.md is **deterministic**
(counted from the AST) and is NOT in this phase.

## Reconcile with the team's stated conventions — don't re-derive blindly

If the repo states its own conventions, the generated docs must
**reconcile with them, not silently contradict or duplicate them.** The
Phase 0 preflight reports the Claude-specific sources that it found. On Codex, resolve
the active project instruction file with Codex's normal precedence
(`AGENTS.override.md`, `AGENTS.md`, then configured fallback filenames):

- `.claude/rules/**` — the team's own coding rules (`rule_files` in the
  preflight report / `dummyindex context preflight --json`).
- Conventions stated in `.claude/CLAUDE.md`, the active Codex project
  instruction file, and a root `CONVENTIONS.md`, when present.

Each Phase 1.5 author **reads those first**, then:

1. **Code follows a stated rule** → cite the rule *and* a `path:range` that
   shows it in practice.
2. **Code reveals a real practice that the rules do not mention** → add it, marked as
   observed-from-source.
3. **Code contradicts a stated rule** → flag it explicitly ("host guidance says X, but
   `foo.py:42` does Y"). The AST wins for *what the code currently does*. The
   stated rule is the team's *intent*. Surface both. Never overwrite one with
   the other.

Goal: `.context/conventions/*` should read as an extension of the team's stated
rules, grounded in the actual AST. They should not read as a from-scratch re-derivation that drifts
from (or quietly contradicts) what the team already wrote down.

## Context7 seeding (optional, recommended)

Before you dispatch the `coding-practices.md` and `testing.md` authors, detect the
**dominant framework** for the repo. Use `map/files.json` + the repo manifests
(`pyproject.toml`, `package.json`, `pom.xml`, …) to detect it. Run the Context7 lookup
protocol in `council/55-context7.md` for that framework. Then inject the verbatim
excerpt into those two dispatches under a `## Canonical framework docs (Context7)`
heading. This stops the agent from inventing patterns that look right but do not match
the framework's canonical advice. Examples of that advice are the FastAPI `Depends` DI style and the
pytest fixture idiom.

> If your runtime exposes a Context7 MCP server (any `*context7*` namespace — see
> `council/55-context7.md`), seed the dispatch as described above. Otherwise,
> fall back to single-shot reasoning from the source and skip the Context7
> lookup. The `.context/` artifacts have the same shape either way —
> only the quality of the prose changes.

`folder-organization.md` (architect) and `data-access.md` (DBA) do not need the
framework seed. The DBA does its own ORM lookup at critique time (see
`agents/critic-database.md`).

## When this phase runs

After Phase 1 (deterministic backbone) and before Phase 2 (structural
review). The architect's folder-organization output informs the
structural review.

Skip in mode `light` — light mode only refreshes `naming.md`.

## Dispatch pattern

These four are independent — fan them out in **parallel**. On Claude, read each
persona's `subagent_type` from its `agents/*.md` frontmatter, and `skill.md` lists the council
defaults. On Codex, inline the same persona mandate and
use `worker` because these subagents author artifacts. The dev's generic-senior
branch runs twice (once per section). On Claude, dispatch it with
`subagent_type: Senior Developer` (the dev fallback). Four logical dispatches:

```
architect        → folder-organization.md
dev              → coding-practices.md
dev              → testing.md
critic-database  → data-access.md
```

Prompt template (adapt per section):

> You are the **<persona>**. Author
> `.context/conventions/<section>.md` for this repo.

> ## What to cover

> <CONVENTION_SECTIONS[section] from conventions.py>

> ## Inputs available

> - `.context/tree.json` — directory hierarchy.
> - `.context/map/files.json` and `.context/map/symbols.json`. They list every
>   file + every symbol with `path:range`.
> - `.context/conventions/naming.md` — statistically inferred naming.
> - **The team's own stated conventions, when present.** These are `.claude/rules/**`
>   (paths: <preflight `rule_files`, or "none found">). They also include convention
>   statements in `.claude/CLAUDE.md`, the active Codex project instruction
>   file, and a root `CONVENTIONS.md`. **Read these before authoring.**
> - Source files (read them — do not speculate).

> When you write `.context/` documents, follow the Writing standard in `00-overview.md` (ASD-STE100). After you write, run `dummyindex context check --style`.

> ## Reconcile, do not re-derive

> - If a stated rule exists for this topic, **build on it**: cite the rule and
>   a `path:range` that demonstrates it. Add practices that the rules omit. Mark them
>   observed-from-source.
> - If the code **contradicts** a stated rule, flag it ("host guidance says X, but
>   `foo.py:42` does Y"). The AST wins for what the code does, and the rule is the
>   team's intent. Surface both. **Never emit a convention that contradicts a
>   stated team rule without flagging the conflict.**

> ## Output discipline

> - **Derive from the source.** Cite `path:range` for every claim.
> - **Describe what *this* project does**, not best-practice generalities. Example:
>   "This repo uses Pydantic models at API boundaries and dataclasses
>   internally" beats "use type hints".
> - **One markdown page.** Use headings, bullet rules, and code excerpts from
>   actual files. Length: ~400-600 words.
> - The codebase can be too small or inconsistent to derive a rule for
>   some sub-topic. In that case, say so explicitly — do not invent.

> ## When done

> Write your markdown to a tmp file, then place it atomically:

> ```
> dummyindex context conventions-write --section <section> --from-file /tmp/<section>.md
> ```

## Failure handling

If any of the four subagents fails, log a warning and continue with the
others. The naming.md file is already on disk, so the conventions folder is never
empty. To retry, run `/dummyindex` on Claude or `$dummyindex` on Codex again.

## After this phase

`HOW_TO_USE.md` references the four docs. They become required
reading for any future Claude Code or Codex session that writes code in this
repo.
Proceed to Phase 2 (structural review).
