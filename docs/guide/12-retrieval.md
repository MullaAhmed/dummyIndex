# 12 — Retrieval model

This page describes how agents **find** things in `.context/`. [PageIndex](https://github.com/VectifyAI/PageIndex) inspired the method. The method is vectorless. An agent reasons through a tree search.

## The principle

- **Similarity ≠ relevance.**
- Vector search returns chunks that *look* similar.
- An agent that reasons over a tree finds the section that *is* relevant.
- For code, structure carries semantics. Use it.

## What we have that PageIndex needs

- A **table-of-contents tree**: `features/INDEX.json` (top-level) and `tree.json` (per-symbol hierarchy).
- **Per-section summaries**: every `feature.json` has a one-line summary. Every `feature/<id>/spec.md` opens with the feature's intent in plain language.
- **Per-section detail**: `spec.md` (intent and contracts), `plan.md` (architecture and decisions), `concerns.md` (risks and gaps), plus flow narratives.
- **Symbol-level pinpoints**: `map/symbols.json` resolves any symbol to `path:range`.

The retrieval target is always one (or a few) sections — never "a fuzzy match".

## The retrieval procedure (what the agent does)

When the agent has a task or question about the codebase:

0. **(Optional) Get a ranked shortlist.** Run `dummyindex context query "<task>"` (see "Query CLI" below). The command scores every feature by token overlap (name/summary/files/symbols) and prints the top-K with cited excerpts. It is deterministic and has no LLM. Use it as a hint for *which* features to open. Then continue to reason over the TOC.
1. **Read the TOC.** Start with `features/INDEX.json`. It is a flat list with `feature_id`, `name`, `summary`, counts.
2. **Reason over the TOC.** Pick 1–3 features the task touches. Do not grep. Do not scan. Reason only from the names and the summaries.
3. **Read the chosen feature(s).** For each feature, read `feature.json` (machine context) and `spec.md` (the WHAT).
4. **Drill down by depth.** Choose the file that the task needs:
   - "What does this feature do?" → `spec.md` (you already read it in step 3).
   - "How is it implemented?" / "How does X work?" → `plan.md`.
   - "What could go wrong here?" / "Security? Data integrity? Edge cases?" → `concerns.md`.
   - "Trace the flow when …" → `flows/<flow-id>.md`.
5. **Follow pointers.** Every section cites `path:range`. Open the source when the doc references it.
6. **Recurse if needed.** If the task spans features, repeat step 2 for the next feature.
7. **Stop when you can answer.** You do not need to read everything.

## What the agent NEVER does

- ❌ Grep the source tree for keywords before you consult `.context/`.
- ❌ Read random files to try to find context.
- ❌ Ask the user "where is X?" when `map/symbols.json` answers it.
- ❌ Treat `tree.json`'s abstract field as authoritative without a check of the source for high-stakes work.

## What the agent ALWAYS does

- ✅ Start every non-trivial task with `features/INDEX.json`.
- ✅ Cite `path:range` when you describe code.
- ✅ Trust `confidence: INFERRED` for prose but verify against the source for facts.
- ✅ Trigger a rebuild when the index disagrees with the code.

## When to read what

| Task | Read order |
|---|---|
| "Add a new endpoint" | `INDEX.json` → relevant feature `spec.md` → `playbooks/add-endpoint.md` → similar feature's `plan.md` |
| "Fix a bug in checkout" | `INDEX.json` → `checkout/feature.json` → `checkout/plan.md` → `checkout/flows/<the-broken-flow>.md` → source |
| "Audit auth security" | `INDEX.json` → `auth/concerns.md` (Security section) → `auth/plan.md` → `auth/flows/*.md` (for trust boundaries) → source |
| "Refactor the user model" | `INDEX.json` → all features mentioning users → each feature's `plan.md` (Data model section) and `concerns.md` (Data integrity) → source |
| "Onboard a new contributor" | `PROJECT.md` → `architecture/overview.md` → `features/INDEX.md` (the human table) |

## Cost model

- A tree walk reads small JSON files and small markdown files.
- Each query reads ~5–15 KB in total.
- Compare this with vector RAG, which fetches dozens of chunks. It reads 30–100 KB and has much lower precision.
- The tree wins on both cost AND quality.

## How the skill enforces this

- The managed host-guidance block tells the agent: "start at `.context/HOW_TO_USE.md`".
  The block is in `.claude/CLAUDE.md` or in the active instruction file of the Codex project.
- `HOW_TO_USE.md` points at the retrieval procedure above.
- `features/HOW_TO_NAVIGATE.md` covers the features subtree specifically.
- Every persona's output contract forbids ungrounded prose. Every claim cites `path:range`.

## Query CLI ✅ shipped (v0.12)

- `dummyindex context query "how does auth work?"` walks the tree like PageIndex's chat does. It returns the relevant section with `path:range` citations.
- Full surface: `dummyindex context query "..." [--root DIR] [--top-k N] [--budget N] [--json]`.
- `--top-k N` sets how many features the command returns (default 3). The command ranks the features by token overlap.
- `--budget N` sets a token cap on the output that the command prints (default 2000). The cap lets the output fit cleanly into agent loops. The command drops lower-ranked matches when the output reaches the cap.
- `--json` emits a structured result instead of markdown. Use it in scripts.
- Exit codes: `0` on a hit, `1` (no error output) when nothing matches, and `2` on a usage error. The `1` code lets shell scripts detect "no hit". An example of a usage error is a non-integer `--top-k`/`--budget`.
- It is deterministic, with no LLM in the loop. The command is a convenience view over the same JSON that the agent walks manually. The tree-walk procedure above remains the primary interface.
