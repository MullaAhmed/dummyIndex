# dummyindex — Conceptual Guide

> The persistent context engine for AI coding agents.
> Always-on. Source of truth. Self-evolving with the code.
> Deterministic structure + multi-agent deep dive → a text-rich `.context/` per repo.

Read the docs in order for a full picture, or jump directly to what you need.

## Contents

- [01 — Purpose](01-purpose.md) — what dummyindex is, who it's for, what it solves
- [02 — Mental model](02-mental-model.md) — folder · file · feature · flow
- [03 — Architecture](03-architecture.md) — the five layers + managed session hooks
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

- Drop into any repo. Run `/dummyindex` in Claude Code or `$dummyindex` in Codex once.
- After install, both hosts receive durable guidance to consult `.context/` first.
- Updated explicitly (`rebuild`/`reconcile`). Claude's managed hooks flag drift,
  memory, GC, and doc-write issues; Codex uses its active project instruction
  file and explicit skills without a dummyindex-installed hook.
- Language-agnostic: tree-sitter for ~20 languages (+ regex extractors for Blade/Dart). Other languages are skipped at extraction (LLM extraction is roadmapped, not built).
- Two enrichment passes: deterministic Python builds the skeleton; specialist agents fill it with judgment.
- Spec-kit-shaped pipeline: a stack-specialist dev drafts → an architect reorganises → critics file concerns. Each feature gets three layered docs (`spec.md` / `plan.md` / `concerns.md`), not six overlapping essays.
- Retrieval is **PageIndex-style tree search** — no grep, no vectors. Agent reasons over the table-of-contents.
- The folder is the contract. `.context/` is the project's canonical answer to "how does this work?"
- Grounded build loop: plan proposes and build drives dependency waves. Claude
  auto-equips and requires its manifest. Codex plan does not run equip, build
  needs no manifest, and native `worker`/`explorer`/`default` subagents receive
  the grounding inline.
- Equip is also a Claude **plugin manager**: `equip discover` searches the marketplaces + GitHub for agents/skills/plugins that fill detected gaps (trust-tiered, blast-radius disclosed); `equip install` wires them natively into `.claude/settings.json`. `equip eval`/`benchmark` score a tool's trigger-description suite against observed firings → precision/recall/accuracy.
- Cross-session memory: `/dummyindex-remember` or `$dummyindex-remember` uses a
  markdown-first store at `.context/session-memory/` (`now.md` → `recent.md` →
  `archive.md`).
- On-demand review: `/dummyindex-audit` or `$dummyindex-audit` spins up a
  task-dependent argue-and-audit panel over real source and writes a ranked
  `.context/audits/<slug>/report.md`. Read-only.
- Context hygiene: `/dummyindex-gc` or `$dummyindex-gc` sweeps and **deletes**
  (never archives) stale/superseded/dead generated docs, council-judged and
  always user-confirmed.
- Maintenance: `/dummyindex-update` or `$dummyindex-update` upgrades the CLI,
  selected host skill family, and repo wiring non-destructively.
- Managed doc homes: `context migrate-docs` relocates stray planning docs that leaked under `docs/` into their `.context/` homes; a `guard-doc-write` PreToolUse hook blocks new ones from landing in unmanaged locations.
- A `dummyindex context statusline` badge (`[ctx ✓]` / `[ctx: N drift]`) surfaces `.context/` freshness in the shell; `context debt` emits a TODO/FIXME/HACK/DEBT ledger over the repo's Python source.
- Core principle: dummyindex stays the spine — it never writes production code
  itself. Claude may render `.context/`-grounded tooling into `.claude/`; Codex
  stays native and non-mutating. Dispatched agents do the writing.

## Inspirations

- [PageIndex](https://github.com/VectifyAI/PageIndex) — vectorless tree-search retrieval.
- [llm-council](https://github.com/karpathy/llm-council) — peer-ranked multi-LLM debate.
- [agency-agents](https://github.com/msitarzewski/agency-agents) — persona library (MIT).
- [OpenViking](https://github.com/volcengine/OpenViking) — context database paradigm; hierarchical, self-evolving.
- [KARIMO](https://github.com/opensesh/KARIMO) — PRD-driven Claude harness orchestration.
- [ECC](https://github.com/affaan-m/ECC) — skills/instincts/memory operator system.
- [dummyindex](https://github.com/safishamsi/dummyindex) — this project's deterministic-graph heritage.
