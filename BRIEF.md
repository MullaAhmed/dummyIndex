# dummyindex — Project Brief

> The persistent context engine for AI coding agents.
> Always-on. Source of truth. Self-evolving with the code.
> Deterministic structure + multi-agent deep dive → a text-rich `.context/` per repo.

## Contents

- [01 — Purpose](docs/brief/01-purpose.md) — what dummyindex is, who it's for, what it solves
- [02 — Mental model](docs/brief/02-mental-model.md) — folder · file · feature · flow
- [03 — Architecture](docs/brief/03-architecture.md) — the four build layers + the SessionStart drift hook
- [04 — `.context/` data model](docs/brief/04-data-model.md) — what gets generated, where
- [05 — Multi-agent council](docs/brief/05-council.md) — the spec-kit-shaped sequential pipeline
- [06 — Personas](docs/brief/06-personas.md) — dev · architect · critics
- [07 — CLI surface](docs/brief/07-cli.md) — every command, why it exists
- [08 — Skill orchestration](docs/brief/08-skill.md) — markdown-first conductor
- [09 — Lifecycle](docs/brief/09-lifecycle.md) — always-on + self-evolving
- [10 — Non-goals](docs/brief/10-non-goals.md) — what dummyindex deliberately does **not** do
- [11 — Roadmap](docs/brief/11-roadmap.md) — what's deferred, in priority order
- [12 — Retrieval model](docs/brief/12-retrieval.md) — PageIndex-style reasoning-based tree search

## One-page summary

- Drop into any repo. Type `/dummyindex` once. It installs as the project's context engine.
- After install, **every Claude Code session** in that repo consults `.context/` first.
- Auto-refreshes on git commits and code edits. The agent never works against stale context.
- Language-agnostic: tree-sitter for 20 languages (+ regex extractors for Blade/Dart); LLM-driven extraction for the rest.
- Two enrichment passes: deterministic Python builds the skeleton; specialist agents fill it with judgment.
- Spec-kit-shaped pipeline: a stack-specialist dev drafts → an architect reorganises → critics file concerns. Each feature gets three layered docs (`spec.md` / `plan.md` / `concerns.md`), not six overlapping essays.
- Retrieval is **PageIndex-style tree search** — no grep, no vectors. Agent reasons over the table-of-contents.
- The folder is the contract. `.context/` is the project's canonical answer to "how does this work?"

## Inspirations

- [PageIndex](https://github.com/VectifyAI/PageIndex) — vectorless tree-search retrieval.
- [llm-council](https://github.com/karpathy/llm-council) — peer-ranked multi-LLM debate.
- [agency-agents](https://github.com/msitarzewski/agency-agents) — persona library (MIT).
- [OpenViking](https://github.com/volcengine/OpenViking) — context database paradigm; hierarchical, self-evolving.
- [KARIMO](https://github.com/opensesh/KARIMO) — PRD-driven Claude harness orchestration.
- [ECC](https://github.com/affaan-m/ECC) — skills/instincts/memory operator system.
- [dummyindex](https://github.com/safishamsi/dummyindex) — this project's deterministic-graph heritage.
