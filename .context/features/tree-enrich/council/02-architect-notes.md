# Architect notes — tree-enrich (stage 2)

## What I changed

- "Where it lives" → "Boundary" — narrowed to the exactly-two-file bounded
  context (domain + CLI) and stated the argv/JSON-validation-stays-in-CLI split;
  dropped the test-path mention to the Open questions noise para. Why: the
  boundary is the load-bearing fact; tests are not part of it.
- "Architecture in three sentences" → "Plan / apply bracket (the core pattern)"
  — named the plan→author→apply loop explicitly and pinned each step to a
  `path:range`, including the previously-unnamed pre-order `_walk` and the
  atomic temp-then-replace writer. Why: prose described the flow but never named
  the pattern or showed where each phase lives.
- "Data model" — kept, tightened citations: pointed the merge at `_apply`
  (`:261-275`) and the change-guard (`:266-272`) rather than the public wrapper.
  Why: the no-op-on-unchanged logic lives in the internal, not `apply_updates`.
- Added "Dependencies" section — was absent; made upstream/downstream/cycles
  explicit. Why: mandate requires visible dependencies.
- "Key decisions" → "Decisions" — rewrote each as "decided X because Y";
  promoted the previously-implicit rationale (scratch artefact, one-way promotion,
  per-file batching, surfaced typos, mode gating). Why: rationale was stated
  flatly; promoted to decision form.
- "Open questions" — kept both, trimmed the membership list to a representative
  sample. Why: the full enumeration was filler; the point survives.

## Patterns named

- **Plan / apply bracket (plan → out-of-band author → apply)** — `build_plan`
  at `dummyindex/context/domains/enrich.py:90`, `apply_updates` at `:202`,
  bracketing the `/dummyindex` LLM step persisted to
  `.context/cache/_enrich_plan.json` (`dummyindex/cli/enrich.py:42-43`).
- **Pre-order tree walk** — `_walk` at
  `dummyindex/context/domains/enrich.py:228-235`, driving stub collection in
  `build_plan` (`:113`).
- **Atomic temp-then-replace writer** — `write_plan`
  (`dummyindex/context/domains/enrich.py:182-185`) and the tree rewrite in
  `apply_updates` (`:219-221`).
- **Port/adapter split (CLI boundary vs pure domain)** — adapter
  `dummyindex/cli/enrich.py` (argv + gating + JSON validation) over domain
  functions that take `Path`/`dict` only (`enrich.py:90`, `:202`).

## Dependencies surfaced

- **Upstream:** `ConfidenceLevel` (`dummyindex/pipeline/enums.py:16-24`);
  `tree.json` from deterministic ingest; `ensure_context_gitignore` +
  `remove_legacy_enrich_plan` from `dummyindex.context.build.runner`
  (`dummyindex/cli/enrich.py:11-14`).
- **Downstream:** `context` dispatcher (`dummyindex/cli/__init__.py`,
  `ENRICH_PLAN`/`ENRICH_APPLY` → `run_plan`/`run_apply`); PageIndex tree walk
  consumes the enriched `tree.json`.
- **Cycles:** none. Domain → enum + stdlib only; CLI → domain + build.runner;
  no back-edges.

## Decisions promoted

- Plan is transient scratch (cache/, gitignored), not a committed doc — feeds
  retrieval, not council (`dummyindex/cli/enrich.py:34-43`).
- Confidence promotion one-way + idempotent — never demotes, no-op on unchanged
  (`dummyindex/context/domains/enrich.py:266-272`).
- Per-file-subtree batching for resumability (`:151-158`).
- Typo'd node_ids surfaced (exit 1 + stderr), never silently dropped
  (`:213-215`, `dummyindex/cli/enrich.py:116-123`).
- Both verbs mode-gated, exit 2 without an index
  (`dummyindex/cli/enrich.py:22-28`, `:94-99`).
