# Retrieval — PageIndex-style tree search

When an agent in a future session has a task or question about the codebase, **how does it find the right context**?

Inspired by [PageIndex](https://github.com/VectifyAI/PageIndex). The pattern: hierarchical TOC + LLM reasoning over the tree. No vectors, no chunks, no grep-first.

## The principle

- **Similarity ≠ relevance.**
- Vector RAG returns chunks that look similar to the query.
- Reasoning over a structured tree returns the section that **is** relevant.
- For code, structure carries semantics. Use it.

## The seven-step procedure

When the agent has a non-trivial task:

1. **Read the TOC.** Start at `.context/features/INDEX.json`.
2. **Reason over the TOC.** Pick 1–3 features the task touches. No grep, no scan — just reasoning from `name` + `summary` + counts.
3. **Read the chosen feature(s).** For each: `feature.json` (machine context) and `spec.md` (the WHAT — intent, behavior, contracts).
4. **Drill into the relevant doc.** Based on the task type, read the right doc:
   - "How does X work?" / "How is it built?" → `plan.md`
   - "What data does X read/write?" → `plan.md` (Data model section)
   - "Can X be exploited?" / "What's risky?" → `concerns.md`
   - "What does X do for the user?" → `spec.md`
5. **Follow flow narratives.** For sequence questions ("what happens when X is triggered?"), read `flows/<flow-id>.md`.
6. **Resolve symbols via maps.** Use `map/symbols.json` to translate symbol names to `path:range`.
7. **Read source.** Only when the docs cite something specific and you need to verify or extend it.

## What the agent NEVER does

- ❌ Grep the source tree first.
- ❌ Read random files trying to find context.
- ❌ Ask the user "where is X?" when the maps answer it.
- ❌ Skip `.context/` and go straight to the code.

## What the agent ALWAYS does

- ✅ Start every non-trivial task with `features/INDEX.json`.
- ✅ Cite `path:range` when describing or modifying code.
- ✅ Trust `confidence: INFERRED` for prose; verify against source for facts.
- ✅ Trigger a rebuild when the docs disagree with what the source actually shows.

## Sub-procedures

- `10-feature-lookup.md` — how to walk INDEX.json → feature drill-down.
- `20-symbol-lookup.md` — how to resolve a symbol to source via `map/`.
- `30-flow-trace.md` — how to follow a flow narrative to source.

## Cost model

A typical tree walk reads:
- INDEX.json: ~5 KB
- 1–3 feature.json + spec.md: ~15 KB
- 1 domain doc: ~5 KB

Total ~25 KB read for most queries. Compare to vector RAG fetching 20 chunks: ~60 KB at lower precision.

The tree wins on both cost AND quality.

## When this is built into the agent

Every session, the agent reads `.context/HOW_TO_USE.md` via the 3-line CLAUDE.md managed block. `HOW_TO_USE.md` IS the user-facing version of this procedure. The skill writes it during ingest; refreshing the skill markdown + running `bootstrap` propagates updates.
