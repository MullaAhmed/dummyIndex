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
- Once installed, Claude Code and Codex both receive durable instructions to
  consult it first. Claude also gets automatic session hooks; Codex uses its
  active project instruction file and explicit `$dummyindex*` workflows.
- Stays in sync via explicit `rebuild`/`reconcile`; Claude's SessionStart hook
  flags drift automatically, while Codex surfaces it through durable guidance
  and the explicit status/reconcile flow.
- Self-maintains its own output: a garbage-collection sweep (`context gc`,
  driven by `/dummyindex-gc` on Claude or `$dummyindex-gc` on Codex) retires
  stale, superseded, or dead generated docs under `proposals/` and `audits/` —
  always user-confirmed, deleted not archived.
- Other AI agents (Cursor, Aider, and similar tools) can read the same folder.

## What it does specifically

- Indexes every file, class, function, method via AST.
- Language-agnostic: tree-sitter for ~20 mainstream languages, plus regex extractors for Blade/Dart.
- Builds a hierarchy: project → directory → file → class → method.
- Detects features (cohesive groups of symbols) via graph community detection.
- Traces flows (entry-point call sequences) per feature.
- Runs a sequential pipeline per feature — stack-specialist dev drafts, architect reorganises, critics file concerns. Three layered docs (`spec.md` / `plan.md` / `concerns.md`), not a wall of essays.
- Maintains managed host guidance in `.claude/CLAUDE.md` for Claude Code and
  the active project instruction file for Codex.
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
- `.context/` stays in lockstep with the code; Claude surfaces staleness at
  session start and Codex surfaces it through its explicit workflow, then the
  active session resolves it.

## The promise: language-agnostic

- Tree-sitter native: Python, TS/JS, Go, Rust, Java, C/C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Julia, Verilog.
- Other text-based languages without a grammar are currently **skipped** at extraction time — LLM-based extraction is roadmapped (see [11 — Roadmap](11-roadmap.md)), not yet built.
- Quality scales with language tooling; coverage today is whatever tree-sitter + the Blade/Dart regex extractors handle.

## How it differs from alternatives

| Tool | Output | When refreshed | Persists? | Agent-shaped? | Always-on? |
|---|---|---|---|---|---|
| **dummyindex** | `.context/` folder | Explicit `rebuild`/`reconcile`; Claude also gets a per-session drift flag | Yes (on disk) | Yes | Yes |
| Aider repo-map | Token budget | Every turn | No | No | No |
| Cursor `@codebase` | Vector hits | Background | Yes (vector store) | Partial | No (manual ref) |
| Hand-written host instruction file | One file | Manual | Yes | Yes | Yes (but stale) |
| PageIndex (the inspiration) | Tree TOC | On ingest | Yes | Yes | Per-document |
| Symbol-only graph (dummyindex v1) | HTML viewer | Manual | Yes | No (for humans) | No |

## v0.15: grounded build loop + session memory

Part 1 — the context engine — is the foundation. The grounded build loop turns a
feature request into a consistency-checked proposal and drives its checklist to
reconciliation. Claude may render an origin-hash-baselined `.claude/` toolkit;
Codex skips equipment and routes through native built-ins without a manifest.
The second extension is markdown-first cross-session memory at
`.context/session-memory/`.

Core principle: **dummyindex stays the spine — it never writes production code
itself. It plans and orchestrates; Claude can add rendered equipment, while
Codex stays native. Dispatched agents do the writing.**

## The bet

- Structured retrieval beats vector retrieval for code tasks.
- Persistent disk artifacts beat per-turn maps for consistency.
- LLM-written docs beat name-based stubs for onboarding speed.
- A managed `.context/` that **evolves with the code** beats a one-time index.
- Reasoning-over-tree (PageIndex) beats similarity-over-chunks for code understanding.
