# 01 — Purpose

## The problem

- AI coding agents waste tokens grepping unfamiliar codebases.
- Vector RAG returns chunks without structure. Similarity ≠ relevance.
- Repo-maps (Aider, Cursor) are flat, per-turn, ephemeral.
- Hand-written `CLAUDE.md` files go stale.
- No **persistent, agent-facing, always-on, self-evolving** context lives next to the code.

## What dummyindex is

- A skill that turns any repo into a `.context/` folder.
- The folder is the **canonical context engine** for the repo.
- Once installed, every Claude Code session in the repo consults it first — automatically.
- Auto-refreshes on git commits and code edits. Never lags the code.
- Other AI agents (Cursor, Codex, Aider) can read the same folder.

## What it does specifically

- Indexes every file, class, function, method via AST.
- Language-agnostic: tree-sitter for ~20 mainstream languages; LLM-driven extraction fallback for the rest.
- Builds a hierarchy: project → directory → file → class → method.
- Detects features (cohesive groups of symbols) via graph community detection.
- Traces flows (entry-point call sequences) per feature.
- Runs a sequential pipeline per feature — stack-specialist dev drafts, architect reorganises, critics file concerns. Three layered docs (`spec.md` / `plan.md` / `concerns.md`), not a wall of essays.
- Maintains a 3-line managed pointer in the repo's `CLAUDE.md`.
- Retrieves answers via **PageIndex-style tree search** — no grep, no vectors.

## Who it's for

- AI coding agents — primary consumer, every session.
- Humans onboarding a codebase — secondary consumer.
- The repo's existing maintainers — tertiary (they get free docs that stay current).

## What success looks like

- An agent given a non-trivial task **never grepps blindly** — it walks `.context/` first.
- Tool-call count drops ≥50% on representative tasks vs. baseline.
- Implementation quality is parity or better — no semantic regression.
- New contributors (human or AI) can answer "where does X live?" in seconds.
- `.context/` stays in lockstep with the code; staleness is detected and auto-resolved.

## The promise: language-agnostic

- Tree-sitter native: Python, TS/JS, Go, Rust, Java, C/C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Julia, Verilog.
- Fallback for any other text-based language: LLM extracts structure (classes, functions, exports) from source.
- Quality scales with language tooling, but the framework adapts. No language is unsupported.

## How it differs from alternatives

| Tool | Output | When refreshed | Persists? | Agent-shaped? | Always-on? |
|---|---|---|---|---|---|
| **dummyindex** | `.context/` folder | Auto on commit/edit | Yes (on disk) | Yes | Yes |
| Aider repo-map | Token budget | Every turn | No | No | No |
| Cursor `@codebase` | Vector hits | Background | Yes (vector store) | Partial | No (manual ref) |
| Hand-written CLAUDE.md | One file | Manual | Yes | Yes | Yes (but stale) |
| PageIndex (the inspiration) | Tree TOC | On ingest | Yes | Yes | Per-document |
| Symbol-only graph (dummyindex v1) | HTML viewer | Manual | Yes | No (for humans) | No |

## v0.15: grounded build loop + session memory

Part 1 — the context engine — is the foundation. v0.15 builds on it in two directions. First, a grounded build loop (plan→equip→execute): `/dummyindex-plan` turns a feature request into a consistency-checked proposal grounded in the index; `/dummyindex-equip` generates a project-tuned toolkit in `.claude/` (agents, skills, hooks, versioned and origin-hash baselined); `/dummyindex-build` drives the proposal's checklist through that toolkit, re-indexing when done. Second, markdown-first cross-session memory at `.context/session-memory/` via `/dummyindex-remember`.

Core principle: **dummyindex stays the spine — it never writes production code itself; it plans, equips `.context/`-grounded tooling into `.claude/`, and orchestrates; the generated tooling + dispatched agents do the writing. Agent dispatch is always skill-layer.**

## The bet

- Structured retrieval beats vector retrieval for code tasks.
- Persistent disk artifacts beat per-turn maps for consistency.
- LLM-written docs beat name-based stubs for onboarding speed.
- A managed `.context/` that **evolves with the code** beats a one-time index.
- Reasoning-over-tree (PageIndex) beats similarity-over-chunks for code understanding.
