# Architect notes — tree-enrich (stage 2)

Revised the dev draft (`01-dev-draft.md`) in place. The draft was already
accurate; the work was structural — separating the bounded context cleanly,
naming the patterns at their homes, surfacing the dependency graph, and promoting
two unstated rationales into "decided X because Y". All cited symbols spot-checked
against `map/symbols.json`; all load-bearing ranges verified against source (code
wins). No contradiction found between the HIGH-confidence docs (`skill.md`,
`retrieval/00-overview.md`) and the code.

## What I changed

- `## Where it lives` -> `## Bounded context`, split into four typed roles:
  Domain (CORE), CLI boundary (CORE), dispatch wiring (SHARED, not owned),
  orchestration (out of the Python boundary). The draft had these as one flat
  list; the CORE / shared / out-of-repo seams are now explicit.
- Promoted the co-located-test-noise call to its own
  `### Co-located test noise — boundary call` subsection. Stated the *mechanism*
  of the mis-clustering (shared test-harness call edges via a common CLI runner
  fixture) rather than only asserting it, and pinned the one genuine test file
  (`tests/context/domains/test_enrich.py`, members `feature.json:121-138`).
- Added `## Patterns (named, with their home)` — four patterns, each with a
  `path:range`.
- Added `## Dependencies` — upstream / downstream / sibling made explicit.
- Rewrote `## Key decisions` so each bullet leads "Decided X because Y" and states
  the trade-off where there is one.
- Cut filler: stopped re-narrating exit codes (spec owns that contract); the plan
  now points at `cli/enrich.py:116-123` instead of paraphrasing it.

## Patterns named

- **Plan/apply two-phase with an out-of-band author** — lives in
  `dummyindex/context/domains/enrich.py:90` (`build_plan`), `:180` (`write_plan`),
  `:202` (`apply_updates`). The author step sits *outside* the domain by design;
  the CLI never calls an LLM.
- **Stub -> INFERRED confidence flip (one-way, idempotent)** — lives in `_apply`,
  `dummyindex/context/domains/enrich.py:261-275`; change-guard at `:266-272`.
- **Mode-gated fan-out owned by the orchestrator** — lives in
  `dummyindex/skills/skill.md:260-263`, NOT in the CLI verbs. The verbs are
  mode-agnostic.
- **Atomic temp-then-`replace` for every writer** — lives in
  `dummyindex/context/domains/enrich.py:182-185` (`write_plan`) and `:219-221`
  (the `apply_updates` tree rewrite).

## Dependencies surfaced

- **Upstream:** `tree.json` from the deterministic backbone. `build_plan` reads
  `<context_dir>/tree.json` and raises `FileNotFoundError` if absent
  (`dummyindex/context/domains/enrich.py:90-92`); the `EXTRACTED` stubs it filters
  are seeded by the backbone build, not this feature
  (`dummyindex/skills/skill.md:248-249`).
- **Downstream:** a future session's PageIndex tree walk reads the abstracts at
  step 6 of the retrieval procedure
  (`dummyindex/skills/retrieval/00-overview.md:28-29`, DocConfidence.HIGH).
- **Sibling:** runs as Phase 4.5, strictly before Phase 5 reconcile
  (`dummyindex/skills/skill.md:246-271`).

## Decisions promoted

- **Why retrieval-facing & runs after per-feature work** — promoted from an
  implicit aside to a decided-because. The personas never read node abstracts; the
  abstracts feed a *future* PageIndex walk, so the phase runs after council and the
  work-list is a throwaway under `cache/` (`dummyindex/skills/skill.md:250-252`;
  gitignore upgrade + legacy-copy delete at `dummyindex/cli/enrich.py:40-41`).
- **Why mode gating is an orchestration concern, not a CLI concern** — promoted
  with its trade-off. Keeping `--mode` out of the verbs keeps the domain a pure
  testable function (`dummyindex/skills/skill.md:260-263`); the cost is that the
  "standard skips symbol batches" invariant lives only in the orchestrator's
  dispatch choice and is untested by the CLI suite.

## Audit trail

- All enrich symbols resolve in `map/symbols.json` at the cited ranges
  (`build_plan:90`, `apply_updates:202`, `write_plan:180`,
  `run_plan`/`run_apply` at `cli/enrich.py:10`/`:58`, DTOs at
  `:29`/`:42`/`:51`/`:189`). Verified.
- `map/symbols.json` records the `_collect_ids` *definition* at `enrich.py:253`;
  the plan cites the *call-site* inside `apply_updates` (`:213-215`). Both correct
  — the call-site is the load-bearing one for the unknown-id behaviour. Verified
  against source (`enrich.py:213-217`).
- No doc/code conflict. `skill.md` (HIGH) and `retrieval/00-overview.md` (HIGH)
  both corroborate the retrieval-facing placement and orchestrator-owned mode
  gating; quoted only after spot-check. No `low`-confidence doc used as authority.
