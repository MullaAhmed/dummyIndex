# 12 — Retrieval model

How agents **find** things in `.context/`. Inspired by [PageIndex](https://github.com/VectifyAI/PageIndex): vectorless, reasoning-based, tree-search.

## The principle

- **Similarity ≠ relevance.**
- Vector search returns chunks that *look* similar.
- Reasoning over a tree returns the section that *is* relevant.
- For code, structure carries semantics. Use it.

## What we have that PageIndex needs

- A **table-of-contents tree**: `features/INDEX.json` (top-level) + `tree.json` (per-symbol hierarchy).
- **Per-section summaries**: every `feature.json` has a one-line summary; every `feature/<id>/README.md` has a one-page synthesis.
- **Per-section detail**: `architecture.md`, `implementation.md`, `data-model.md`, `security.md`, `product.md`, plus flow narratives.
- **Symbol-level pinpoints**: `map/symbols.json` resolves any symbol to `path:range`.

The retrieval target is always one (or a few) sections — never "a fuzzy match".

## The retrieval procedure (what the agent does)

When the agent has a task or question about the codebase:

1. **Read the TOC.** Start with `features/INDEX.json`. It's a flat list with `feature_id`, `name`, `summary`, counts.
2. **Reason over the TOC.** Pick 1–3 features the task touches. No grep, no scan — just reasoning from names + summaries.
3. **Read the chosen feature(s).** For each: `feature.json` (machine context) and `README.md` (synthesized prose).
4. **Drill down by domain.** Based on the task:
   - "How does X work?" → `architecture.md` + `implementation.md`.
   - "What data does X read/write?" → `data-model.md`.
   - "Can X be exploited?" → `security.md`.
   - "What does X do for the user?" → `product.md`.
   - "Trace the flow when …" → `flows/<flow-id>.md`.
5. **Follow pointers.** Every section cites `path:range`. Open the source when the doc references it.
6. **Recurse if needed.** If the task spans features, repeat step 2 for the next feature.
7. **Stop reading when you can answer.** No need to read everything.

## What the agent NEVER does

- ❌ Grep the source tree for keywords before consulting `.context/`.
- ❌ Read random files trying to find context.
- ❌ Ask the user "where is X?" when `map/symbols.json` answers it.
- ❌ Treat `tree.json`'s abstract field as authoritative without checking source for high-stakes work.

## What the agent ALWAYS does

- ✅ Start every non-trivial task with `features/INDEX.json`.
- ✅ Cite `path:range` when describing code.
- ✅ Trust `confidence: INFERRED` for prose but verify against source for facts.
- ✅ Trigger a rebuild when the index disagrees with the code.

## When to read what

| Task | Read order |
|---|---|
| "Add a new endpoint" | `INDEX.json` → relevant feature `README` → `playbooks/add-endpoint.md` → similar feature's `architecture.md` |
| "Fix a bug in checkout" | `INDEX.json` → `checkout/feature.json` → `checkout/implementation.md` → `checkout/flows/<the-broken-flow>.md` → source |
| "Audit auth security" | `INDEX.json` → `auth/security.md` → `auth/flows/*.md` (for trust boundaries) → source |
| "Refactor the user model" | `INDEX.json` → all features mentioning users → cross-reference `data-model.md` files → source |
| "Onboard a new contributor" | `PROJECT.md` → `architecture/overview.md` → `features/INDEX.md` (the human table) |

## Cost model

- A tree walk reads small JSON + small markdown files.
- Total per query: ~5–15 KB read.
- Compare to vector RAG fetching dozens of chunks: 30–100 KB read, with much lower precision.
- The tree wins on both cost AND quality.

## How the skill enforces this

- The 3-line managed block in `CLAUDE.md` tells the agent: "start at `.context/HOW_TO_USE.md`".
- `HOW_TO_USE.md` points at the retrieval procedure above.
- `features/HOW_TO_NAVIGATE.md` covers the features subtree specifically.
- Every persona persona's output contract forbids ungrounded prose — every claim cites `path:range`.

## Future: query CLI

- v0.9 (roadmap): `dummyindex context query "how does auth work?"` → walks the tree like PageIndex's chat does, returns the relevant section with `path:range` citations.
- Budget-capped output so it slots cleanly into agent loops.
- Until then: the agent walks the file structure directly. The procedure above IS the interface.
