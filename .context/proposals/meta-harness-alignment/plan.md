# Plan — Meta-Harness alignment: keep equip-eval a reporter (proxy-not-prize framing + decision record)

> Ordered, file-path-naming tasks. Cite reused symbols from
> `.context/map/symbols.json` where you can reuse instead of writing new.
> This proposal writes **no new code symbols** — it edits docs, two module
> docstrings, and adds one guard test. All grounded in the `equip` feature
> (`.context/features/equip/spec.md`).

> **Panel-folded (2026-07-05):** decision moved to a non-GC home (equip feature
> spec, not only the proposal); guard made positive + regex-negative (a bare
> "no evolve-loop" check self-contradicts the caution we add and would never go
> GREEN); "held-out" dropped from SKILL claims (not in the shipped skill — only
> `blind`/`synthetic` are); docstring task scoped to a single added clause;
> guard/docstring edits split across disjoint test homes so waves stay parallel.

> **R3-folded (2026-08-07):** a 13-source adversarially-verified reanalysis
> (24 agents, 0 verdicts refuted) corroborated the contraindication upstream —
> `experimental/harbor_meta_harness/` (upstream PR #12) rewards task-outcome
> only, trigger accuracy appears nowhere, and its README mandates a measured
> headroom probe before any loop. Folded: task 3's feature-spec line and task
> 4's decisions.md now carry the upstream citation; new task 4b records the full
> reanalysis in `r3-repo-reanalysis.md` (written in-session — verify only). The
> R3 backlog itself is recorded, not built: each item routes through its own
> proposal. All anchors re-verified EXACT on main v0.34.0 (SKILL.md sections at
> :483 and :571).

> **Prime-agent-folded (2026-08-07):** a first-round 3-lens survey (+ refutes,
> 0 refuted) of `PrimeIntellect-ai/prime-agent` @ `87e7a7f` found a SECOND
> corroborating exhibit: its Continual Harness `/refine` loop ships self-judged
> — the paper's outcome channel was dropped in the coding port — i.e. the exact
> shape this proposal contraindicates, running in production. Folded: task 4's
> decisions.md gains exhibit (e) + the `prime-agent` token; task 4b's record now
> includes the survey addendum. Its 7 ADAPT ideas (rollback ledger, audit
> fields, scope policy, noise criteria, fail-open gate-loop fold, context-handle
> doc, delegation-miner pilot) are recorded in the addendum, NOT built here.

## Tasks

1. **SKILL proxy-vs-prize framing + guard (TDD in one item).** Edit
   `dummyindex/skills/equip/SKILL.md`: (a) in `## Evaluate a generated tool`
   (~L421) add a short **proxy-vs-prize** callout — trigger accuracy = *routing
   quality (a proxy)*, NOT toolkit/task-outcome quality (the *prize* the paper's
   50.0 measures); (b) in the improve-loop step (~L512) add a caution that tuning
   the `description` against the suite tends to **overfit** it and that `equip
   eval` is a **reporter**, not a search-optimization target/gate; (c) leave the
   existing `blind` + `synthetic`-prompt + `equip patch` wording intact. TDD:
   first extend `tests/test_skills_doc_hygiene.py` (reuse `_equip_skill()`,
   co-locate with `test_equip_skill_documents_eval_benchmark_loop`) with a guard
   that asserts (positive) the tokens `proxy`, `prize`, `overfit`, `reporter` are
   present, and (negative, regex-scoped like
   `test_gc_skill_no_runnable_gc_delete_without_yes`) that no runnable
   `equip evolve-loop` command line is documented — **never** a bare
   `"evolve-loop" not in text` check (it would false-positive on the caution we
   just added). Run RED, then edit the SKILL until GREEN.
   Files: `dummyindex/skills/equip/SKILL.md`, `tests/test_skills_doc_hygiene.py`.

2. **Add the one proxy clause to the eval docstrings.** In
   `dummyindex/cli/equip/eval.py` and
   `dummyindex/context/domains/equip/eval/score.py` module docstrings, **add a
   single clause** stating the confusion-matrix score is a routing-accuracy
   **proxy for reporting**, not a value to optimize/search against. The existing
   "reporter, not a gate" / "never an LLM call from code" prose is already correct
   — **do not rewrite it** (churn, no value). No logic edits: `score_run`,
   `aggregate_benchmark`, `run_eval`, `run_benchmark` reused unchanged. Do not
   introduce the words `optimize`/`maximize`/`best candidate`.
   Files: `dummyindex/cli/equip/eval.py`,
   `dummyindex/context/domains/equip/eval/score.py`.

3. **Durable decision line in the feature spec (non-GC home).** Add one line to
   the eval Contracts bullet of `.context/features/equip/spec.md`: a
   trigger-accuracy **evolve-loop is contraindicated** — cite arXiv 2603.28052,
   the durable memory note `meta-harness-vs-dummyindex-verdict.md`, and the
   upstream corroboration
   (`meta-harness@44b9942:experimental/harbor_meta_harness/README.md`
   probe-before-loop) (self-contained so it survives even if the proposal dir is
   later GC-swept). This is the reconcile-owned home the panel flagged; keep it
   to one sentence.
   File: `.context/features/equip/spec.md`.

4. **Ephemeral working record** `.context/proposals/meta-harness-alignment/decisions.md`.
   Rich detail for now (the durable copy is task 3): (a) the council verdict —
   Meta-Harness lens applies to `equip` only, not `.context/`; `.context/` is a
   navigation map, not the paper's "compressed-feedback bottleneck"; (b) the two
   falsification experiments (`dummyindex-db-specialist` and
   `dummyindex-security-specialist`; every baseline/tuned × search/held-out cell
   = **1.00**; the tuner overfit both times) → **no headroom → the
   trigger-accuracy `equip evolve-loop` is CONTRAINDICATED**; (c) what stays true:
   `equip eval` is a reporter of a routing *proxy*; the real *prize* (task-outcome
   quality via the repo's own test suite) is the only future direction worth
   revisiting; (d) **the upstream corroboration (R3, 2026-08-07)**: the harbor
   pilot rewards task-outcome (Harbor verifier suites — mean/min/fraction_solved),
   trigger accuracy appears nowhere; README mandates "Probe each collection
   before using it"; `forbidden_references` ≈ the observed tuner-overfit mode —
   cite `meta-harness@44b9942:experimental/harbor_meta_harness/README.md` and
   `controller.py` (~127-149, `validate_source` ~272+); (e) **the second
   corroborating exhibit (prime-agent, 2026-08-07)**: `/refine` is self-judged
   (evidence = the proposing LLM's own rationale; `expectedOutcome` recorded,
   never validated; kernel CRUD ungated; the paper's outcome channel dropped in
   the coding port) — cite
   `prime-agent@87e7a7f:packages/coding-agent/src/core/refinement/refinement.ts`
   and `prompts/rlm.ts:29`. Contain the strings
   `2603.28052`, `contraindicated`, `1.00`, `harbor_meta_harness`, `44b9942`,
   `prime-agent`.
   Mirror the memory note + the experiment artifact
   `scratchpad/mh-falsify/RESULT.md` (summarise — don't assume the scratchpad
   persists).
   File: `.context/proposals/meta-harness-alignment/decisions.md`.

4b. **R3 reanalysis record + prime-agent addendum (verify only).**
   `.context/proposals/meta-harness-alignment/r3-repo-reanalysis.md` was written
   in-session on 2026-08-07 (13-source verdict table, priority backlog, corrected
   host-coverage premise, incident note) and extended the same day with the
   prime-agent first-round survey addendum (verdict row, 7 ADAPT ideas, interop
   fact, future survey queue). Build-time work: confirm it exists and contains
   `13/13`, `0 refuted`, `probity`, `prime-agent`, `87e7a7f`. Durable copies live
   in the `dummyindex-repo-adoption-verdict` and `harness-landscape-2026-07`
   memories; this file is GC-swept with the proposal. Do NOT build backlog or
   ADAPT items from it here.
   File: `.context/proposals/meta-harness-alignment/r3-repo-reanalysis.md`.

5. **Acceptance / verify (depends on 1–4b).** Run `tests/context/domains/equip/eval`,
   `tests/cli/equip`, and `tests/test_skills_doc_hygiene.py` — all green. Then
   grep-verify the acceptance assertions: `eval.py`/`score.py` docstrings contain
   the proxy clause and none of `optimize`/`maximize`/`best candidate`;
   `equip/spec.md` contains `contraindicated` + `2603.28052`; `decisions.md`
   contains `2603.28052`/`contraindicated`/`1.00`/`harbor_meta_harness`/`44b9942`/`prime-agent`;
   `r3-repo-reanalysis.md` contains `13/13`/`0 refuted`/`probity`/`prime-agent`/`87e7a7f`. Confirm `git diff` under
   `dummyindex/context/domains/equip/eval/` + `cli/equip/eval.py` is
   **docstring-only**, and that no `test_cli_doc_sync.py`-style doc-sync test
   asserts on those docstrings.

## Reuse notes

- **No new modules, classes, or functions.** The eval domain (`score_run`,
  `aggregate_benchmark`, `run_eval`, `run_benchmark`) and the doc-hygiene harness
  (`_equip_skill()` in `tests/test_skills_doc_hygiene.py`) are reused as-is.
- The "reporter, not a gate" language already at `SKILL.md:509` and in
  `cli/equip/eval.py`'s docstring is the anchor the new framing extends —
  consistent, not contradictory.
- **Wave-independence:** tasks 1–4 touch disjoint files (only task 1 touches the
  test file), so they parallelize safely; task 5 verifies after.
