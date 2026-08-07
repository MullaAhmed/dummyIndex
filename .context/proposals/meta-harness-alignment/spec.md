# Spec — Meta-Harness alignment: keep equip-eval a reporter (proxy-not-prize framing + decision record)

> Scaffolded by `dummyindex context propose`. Flesh out the intent
> and contracts below, then keep the **Acceptance** checklist honest.

## Intent

**Problem.** The Stanford Meta-Harness paper (arXiv 2603.28052) and the informal
framing "dummyindex *is* a meta-harness" invite a tempting but wrong move: turning
the `equip eval` stage into a closed-loop optimizer (propose → eval → keep-best,
searching over a tool's `description` to maximise trigger accuracy). A 5-advisor
council (2026-07-01) and **two falsification experiments (2026-07-05)** showed
that move is unfounded:

- The trigger-accuracy metric scored **1.00 on every cell** (baseline/tuned ×
  search/held-out) for both a narrow tool (`db-specialist`) and a deliberately
  **ambiguous, overlapping** tool (`security-specialist`) with adversarial
  security-flavoured decoys — i.e. **no headroom** for a reasonably-described
  tool, so a search loop has nothing to optimise.
- The description "tuner" **visibly overfit** the search set both times
  (it enumerated the exact decoy categories), confirming that optimising this
  metric produces suite-overfit descriptions, not better routing.

**Upstream corroboration (R3 reanalysis, 2026-08-07).** The paper's own repo now
agrees with the contraindication. Upstream PR #12 (2026-07-11) added
`experimental/harbor_meta_harness/` — an outer-loop pilot whose reward is
**task-outcome** via Harbor verifier suites (aggregate mean/min/fraction_solved);
trigger accuracy appears nowhere. Its README mandates "Probe each collection
before using it" (a measured headroom check before any loop — the very
discipline our falsification experiments applied), and its `forbidden_references`
denylist (`meta-harness@44b9942:experimental/harbor_meta_harness/controller.py`
~127-149, `validate_source` ~272+) guards exactly the leakage/overfit failure
mode our tuner exhibited. Full 13-source reanalysis this fell out of:
`r3-repo-reanalysis.md` (this dir).

**Second corroborating exhibit (prime-agent survey, 2026-08-07).**
`PrimeIntellect-ai/prime-agent` (Continual Harness, arXiv 2605.09998; pinned
`87e7a7f`) ships the refine loop **without** the outcome channel its paper's
game environment had: `/refine` is self-judged (the "evidence" field is the
proposing LLM's own rationale), `expectedOutcome` is recorded but never
validated, auto-refine defaults ON, and the kernel CRUD path bypasses the
gates entirely (`prime-agent@87e7a7f:packages/coding-agent/src/core/refinement/refinement.ts`,
`prompts/rlm.ts:29`) — a shipping instance of exactly the self-optimization
shape this proposal contraindicates. Survey + verdict: the addendum in
`r3-repo-reanalysis.md`.

**Who this is for.** dummyindex maintainers and any AI session reading the equip
eval docs. The risk is conceptual drift: mistaking the **routing proxy**
(does the description fire on the right prompts?) for **toolkit quality**
(does the equipped tool make the agent's work better? — the "prize" the paper's
50.0 measures). This proposal locks the correct framing into the skill guidance
and code docstrings, and records the decision that the evolve-loop is
**contraindicated**, so no future contributor re-derives the wrong conclusion.

**This is a docs / framing + decision-record change. No behaviour changes.**

## Contracts

**Invariants (must hold after this change):**
- The pure eval domain (`dummyindex/context/domains/equip/eval/` — `score_run`,
  `aggregate_benchmark`) and the CLI boundary (`cli/equip/eval.py` — `run_eval`,
  `run_benchmark`) are **behaviourally unchanged**. Same confusion matrix, same
  exit codes, same reporter semantics (`benchmark` = reporter, not a gate). No
  logic edits — only docstring wording where it could be misread.
- The eval stage stays a **pure reporter**: no LLM-in-code, no search loop, no
  Pareto frontier, no persistence of a "best" candidate.
- The SKILL's existing **blind-judge** (judge each case blind to its label) and
  **held-out / synthetic-prompt** discipline is **reinforced, not weakened**.

**Seams touched (all docs/wording + one guard test):**
- `dummyindex/skills/equip/SKILL.md` — the `## Evaluate a generated tool` section
  (~L421) and the improve-loop step (~L512): add proxy-vs-prize framing + an
  overfitting/reporter-not-optimizer caution. Leave the existing `blind` +
  `synthetic`-prompt wording intact (it is NOT "held-out" — that term is from the
  experiments, not the shipped skill).
- `dummyindex/cli/equip/eval.py` and
  `dummyindex/context/domains/equip/eval/score.py` — module docstrings: **add one
  clause** naming the metric a routing *proxy for reporting*, not an optimization
  target. The existing "reporter, not a gate" / "never an LLM call from code"
  prose is already correct — do not rewrite it (churn, no value).
- `.context/features/equip/spec.md` — the **durable, non-GC home** for the
  decision: a line in the eval Contracts bullet recording that a trigger-accuracy
  evolve-loop is contraindicated (cites arXiv 2603.28052 + the memory note). (A
  proposal dir is GC-swept when it closes, so the decision must not live there
  alone.)
- `.context/proposals/meta-harness-alignment/decisions.md` — the **ephemeral
  working record** (rich detail for now; the durable copy is the feature spec
  above). Now also carries the upstream corroboration:
  `meta-harness@44b9942:experimental/harbor_meta_harness/README.md`
  (probe-before-loop) + `controller.py` (`forbidden_references`).
- `.context/proposals/meta-harness-alignment/r3-repo-reanalysis.md` — the R3
  full-reanalysis record (13 sources, 2026-08-07; **written in-session**, verify
  only at build time) **plus the prime-agent first-round survey addendum**
  (2026-08-07, 3 lenses + refutes, 0 refuted). Ephemeral like decisions.md;
  durable copies live in the `dummyindex-repo-adoption-verdict` and
  `harness-landscape-2026-07` memories.
- `tests/test_skills_doc_hygiene.py` — a guard, co-located with
  `test_equip_skill_documents_eval_benchmark_loop` and reusing `_equip_skill()`,
  asserting the **positive** framing tokens are present and (negative, regex-scoped
  like `test_gc_skill_no_runnable_gc_delete_without_yes`) that no *runnable*
  `equip evolve-loop` command is documented — never a bare "loop"/"evolve-loop"
  word check, which would false-positive on the sanctioned improve-loop and the
  new caution itself.

**Explicitly out of scope** (do NOT implement): any `equip evolve-loop` /
propose→eval→keep-best search; k-candidate generation; a Pareto frontier;
raw-`.claude/`-trace capture; any change to `.context/` generation or to eval
scoring behaviour. The real "prize" — task-outcome quality gradeable by the repo's
own **test suite** — is noted as the only future direction worth revisiting, but
is **not** built here. Likewise the **R3 reanalysis backlog** recorded in
`r3-repo-reanalysis.md` (tdd-guard gate, gh-skill provenance + sentinel fix,
headroom license vendoring, skill_lint, decorator-edge fix, graph verbs, …) is
**recorded here, not built here** — each item routes through its own proposal.
The optional pure-string leakage-guard warning in the eval reporter (flag when a
tool description verbatim-contains suite decoy strings) is recorded as a future
direction only.

## Acceptance

_Criteria are worded as literal, grep-checkable assertions because the doc-hygiene
harness (`_equip_skill()`) is string-level._

- [ ] SKILL.md `## Evaluate a generated tool` section contains the framing tokens
      **`proxy`** and **`prize`** (trigger accuracy = routing proxy, NOT
      toolkit/task-outcome quality).
- [ ] SKILL.md improve-loop step contains **`overfit`** and **`reporter`** (tuning
      the `description` overfits the suite; `equip eval` is a reporter, not a
      search-optimization target/gate).
- [ ] The existing `test_equip_skill_documents_eval_benchmark_loop` still passes —
      i.e. the SKILL's `blind` + `synthetic`-prompt + `equip patch` wording is
      still present (NOT weakened). (No "held-out" assertion — that term is not in
      the shipped skill.)
- [ ] The SKILL contains **no runnable** `equip evolve-loop` command synopsis
      (negative guard is regex-scoped to a command line, NOT a bare "loop" token).
- [ ] `.context/features/equip/spec.md` (durable, non-GC home) records that a
      trigger-accuracy **evolve-loop is contraindicated** — contains
      `contraindicated` and `2603.28052`.
- [ ] `.context/proposals/meta-harness-alignment/decisions.md` exists and contains
      `2603.28052`, `contraindicated`, and `1.00` (council verdict + the two
      falsification experiments + the contraindication decision), plus the
      upstream-corroboration tokens `harbor_meta_harness` and `44b9942`
      (probe-before-loop + `forbidden_references` citations), plus `prime-agent`
      (the second corroborating exhibit: refine loop shipped without its paper's
      outcome channel).
- [ ] `.context/proposals/meta-harness-alignment/r3-repo-reanalysis.md` exists and
      contains `13/13`, `0 refuted`, and `probity` (verdict table, coverage line,
      new-candidate list) plus `prime-agent` and `87e7a7f` (the addendum's verdict
      row and pinned HEAD). Written in-session 2026-08-07 — build-time work is
      verification only.
- [ ] `eval.py` and `score.py` module docstrings each gain a clause naming the
      metric a routing **proxy for reporting** (not an optimization target); the
      existing "reporter, not a gate" / "never an LLM call from code" prose is
      unchanged, and no banned word (`optimize`, `maximize`, `best candidate`) is
      introduced. (Verified by grep in the verify task.)
- [ ] No eval behaviour change: `tests/context/domains/equip/eval`,
      `tests/cli/equip`, and `tests/test_skills_doc_hygiene.py` all pass, and
      `git diff` under `dummyindex/context/domains/equip/eval/` + `cli/equip/eval.py`
      shows **docstring-only** edits. Confirm no doc-sync test
      (`test_cli_doc_sync.py` or similar) asserts on those docstrings.
- [ ] The new SKILL guard lives in `tests/test_skills_doc_hygiene.py`, reuses
      `_equip_skill()`, and is co-located with
      `test_equip_skill_documents_eval_benchmark_loop`; the full suite is green.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `tree-enrich`
- `build-loop`
- `council`
- `preflight`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
