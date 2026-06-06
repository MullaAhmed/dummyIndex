# dummyindex — Conceptual Guide

> The persistent context engine for AI coding agents.
> Always-on. Source of truth. Self-evolving with the code.
> Deterministic structure + multi-agent deep dive → a text-rich `.context/` per repo.

Read the docs in order for a full picture, or jump directly to what you need.

## Contents

- [01 — Purpose](01-purpose.md) — what dummyindex is, who it's for, what it solves
- [02 — Mental model](02-mental-model.md) — folder · file · feature · flow
- [03 — Architecture](03-architecture.md) — the four build layers + the SessionStart drift hook
- [04 — `.context/` data model](04-data-model.md) — what gets generated, where
- [05 — Multi-agent council](05-council.md) — the spec-kit-shaped sequential pipeline
- [06 — Personas](06-personas.md) — dev · architect · critics
- [07 — CLI surface](07-cli.md) — every command, why it exists
- [08 — Skill orchestration](08-skill.md) — markdown-first conductor
- [09 — Lifecycle](09-lifecycle.md) — two modes: setup + ongoing; build loop + session memory
- [10 — Non-goals](10-non-goals.md) — what dummyindex deliberately does **not** do
- [11 — Roadmap](11-roadmap.md) — what's deferred, in priority order
- [12 — Retrieval model](12-retrieval.md) — PageIndex-style reasoning-based tree search

## One-page summary

- Drop into any repo. Type `/dummyindex` once. It installs as the project's context engine.
- After install, **every Claude Code session** in that repo consults `.context/` first.
- Auto-refreshes on git commits and code edits. The agent never works against stale context.
- Language-agnostic: tree-sitter for 20 languages (+ regex extractors for Blade/Dart); LLM-driven extraction for the rest.
- Two enrichment passes: deterministic Python builds the skeleton; specialist agents fill it with judgment.
- Spec-kit-shaped pipeline: a stack-specialist dev drafts → an architect reorganises → critics file concerns. Each feature gets three layered docs (`spec.md` / `plan.md` / `concerns.md`), not six overlapping essays.
- Retrieval is **PageIndex-style tree search** — no grep, no vectors. Agent reasons over the table-of-contents.
- The folder is the contract. `.context/` is the project's canonical answer to "how does this work?"
- v0.15: three sibling skills drive a grounded build loop — `/dummyindex-plan` proposes, `/dummyindex-equip` builds a project-tuned toolkit in `.claude/`, `/dummyindex-build` drives the checklist. Equip v2: origin-hash baselines; user edits never stomped; `equip patch` feeds learnings back.
- v0.15: `/dummyindex-remember` + `dummyindex context memory session-start|roll` — markdown-first cross-session memory at `.context/session-memory/` (`now.md` → `recent.md` → `archive.md`).
- Core principle: dummyindex stays the spine — it never writes production code itself; it plans, equips `.context/`-grounded tooling into `.claude/`, and orchestrates; the generated tooling + dispatched agents do the writing.

## Inspirations

- [PageIndex](https://github.com/VectifyAI/PageIndex) — vectorless tree-search retrieval.
- [llm-council](https://github.com/karpathy/llm-council) — peer-ranked multi-LLM debate.
- [agency-agents](https://github.com/msitarzewski/agency-agents) — persona library (MIT).
- [OpenViking](https://github.com/volcengine/OpenViking) — context database paradigm; hierarchical, self-evolving.
- [KARIMO](https://github.com/opensesh/KARIMO) — PRD-driven Claude harness orchestration.
- [ECC](https://github.com/affaan-m/ECC) — skills/instincts/memory operator system.
- [dummyindex](https://github.com/safishamsi/dummyindex) — this project's deterministic-graph heritage.
