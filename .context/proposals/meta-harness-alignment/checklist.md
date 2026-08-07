# Checklist — meta-harness-alignment

> Work wave-by-wave, top-to-bottom. Items in a wave are mutually independent
> (disjoint files) and may run in parallel; a wave starts only when the previous
> one is fully ticked. Tick `- [x]` only after verifying.

## Wave 1 — framing edits + decision records (disjoint files, parallel)

- [x] SKILL proxy-vs-prize framing + guard (TDD): edit `dummyindex/skills/equip/SKILL.md` — `## Evaluate a generated tool` gains a `proxy`/`prize` callout, improve-loop step gains an `overfit`/`reporter` caution, `blind`/`synthetic`/`equip patch` wording kept; extend `tests/test_skills_doc_hygiene.py` (reuse `_equip_skill()`, co-locate with `test_equip_skill_documents_eval_benchmark_loop`) with a POSITIVE token guard (`proxy`,`prize`,`overfit`,`reporter`) + a regex-scoped negative for a runnable `equip evolve-loop` command (never a bare-word check) — RED then GREEN
- [x] Add one proxy-for-reporting clause to the eval docstrings in `dummyindex/cli/equip/eval.py` and `dummyindex/context/domains/equip/eval/score.py` — no logic edits, existing "reporter, not a gate" prose unchanged, no `optimize`/`maximize`/`best candidate`
- [x] Durable decision line in `.context/features/equip/spec.md` eval Contracts bullet — trigger-accuracy evolve-loop `contraindicated`, cites `2603.28052` + the memory note (self-contained, survives proposal GC)
- [x] Write the ephemeral working record `.context/proposals/meta-harness-alignment/decisions.md` — council verdict + the two falsification experiments (all cells `1.00`) + the `contraindicated` decision + the upstream corroboration (harbor pilot rewards task-outcome, probe-before-loop, `forbidden_references`; cite `meta-harness@44b9942:experimental/harbor_meta_harness/README.md` + `controller.py`) + the second corroborating exhibit (prime-agent `/refine` self-judged, outcome channel dropped; cite `prime-agent@87e7a7f:...refinement/refinement.ts` + `prompts/rlm.ts:29`); contains `2603.28052`, `contraindicated`, `1.00`, `harbor_meta_harness`, `44b9942`, `prime-agent`
- [x] R3 reanalysis record `.context/proposals/meta-harness-alignment/r3-repo-reanalysis.md` written (2026-08-07, in-session; 13-source verdict table + priority backlog + corrected host-coverage premise + incident note) and extended same-day with the prime-agent first-round survey addendum (verdict row + 7 ADAPT ideas + interop fact + future queue) — grep-verified to contain `13/13`, `0 refuted`, `probity`, `prime-agent`, `87e7a7f`; backlog and ADAPT items are recorded, NOT built, in this proposal

## Wave 2 — acceptance + verification (depends on Wave 1)

- [ ] Run `tests/context/domains/equip/eval`, `tests/cli/equip`, `tests/test_skills_doc_hygiene.py` — all green
- [x] Grep-verify: `eval.py`/`score.py` docstrings contain the proxy clause and none of `optimize`/`maximize`/`best candidate`; `equip/spec.md` contains `contraindicated`+`2603.28052`; `decisions.md` contains `2603.28052`/`contraindicated`/`1.00`/`harbor_meta_harness`/`44b9942`/`prime-agent`; `r3-repo-reanalysis.md` contains `13/13`/`0 refuted`/`probity`/`prime-agent`/`87e7a7f`
- [x] Confirm `git diff` under `dummyindex/context/domains/equip/eval/` + `cli/equip/eval.py` is docstring-only, and no doc-sync test (`test_cli_doc_sync.py`-style) asserts on those docstrings
- [x] Acceptance: the reporter/proxy-not-prize story is consistent across SKILL ↔ code docstrings ↔ feature spec, and no eval behaviour changed
