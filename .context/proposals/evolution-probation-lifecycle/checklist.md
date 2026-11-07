# Checklist — Evolution probation lifecycle

> Prerequisite: `evolution-evidence-plane` landed. Waves run in order; items inside a wave touch disjoint files.
> Tick only after the named tests pass. Code rule: no long comments. Fixtures only; no live host sessions.

## Wave 1 — units
- [x] Add `probation/enums.py`, `constants.py`, `models.py`, `store.py` with `tests/context/domains/test_probation.py` (plan task 1)

## Wave 2 — pure rules
- [x] Add `probation/rules.py`; extend `tests/context/domains/test_probation.py` (plan task 2)

## Wave 3 — sync, session block, report
- [x] Add `probation/sync.py` and `probation/render.py`; extend `tests/context/domains/test_probation.py` (plan task 3)

## Wave 4 — actions + learning seam
- [x] Add `probation/actions.py`, `probation/__init__.py`; add the `chat:` branch and `_run_dir` to `evolve_learning.py`; add `tests/context/domains/test_probation_actions.py`; update `tests/context/domains/test_evolve_learning.py` (plan task 4)

## Wave 5 — surfaces
- [x] Add `dummyindex/cli/evolve_probation.py`; register in `cli/evolve.py`; two lines in `cli/help.py`; add `tests/cli/test_evolve_probation_cli.py` (plan task 5)
- [x] Print the session block from `dummyindex/cli/memory.py`; extend `tests/context/domains/memory/test_memory_cli.py` (plan task 6)
- [x] Add `dummyindex/skills/evolve/probation-protocol.md`; budget-neutral pointer in `dummyindex/skills/evolve/SKILL.md` (plan task 7)

## Wave 6 — doc reconcile
- [x] Reconcile `.context/features/evolution/spec.md` and `plan.md` (plan task 8)

## Wave 7 — acceptance
- [x] Acceptance (`test_evolve_learning.py`): `chat:` gate pass leaves `evolution.jsonl` and conventions byte-identical, no `gc/evolve/` dir, PROBATION item written
- [x] Acceptance (`test_evolve_learning.py`): closeout and legacy `human:` events still auto-apply
- [x] Acceptance (`test_evolve_learning.py`): high-impact body blocked; bad probe rejected; `applies_when` defaults to cue
- [x] Acceptance (`test_evolve_learning.py`): per-target and repo-wide caps block with `probation cap`
- [x] Acceptance (`test_evolve_learning.py`): no committed file holds the correction text or the rule body
- [x] Acceptance (`test_probation.py`): retraction demotes in the same sync
- [x] Acceptance (`test_probation.py`): harm needs distinct sessions and distinct days
- [x] Acceptance (`test_probation.py`): matched `forbid` counts `ignored`; second sets `needs_enforcement`; state stays PROBATION
- [x] Acceptance (`test_probation.py`): `probe: null` counts `contested` and blocks eligibility; `probes=False` leaves probe attributions unconsumed
- [x] Acceptance (`test_probation.py`): drift suspends and hides; restore returns PROBATION
- [x] Acceptance (`test_probation.py`): injected `now` expires an unexposed item; record kept
- [x] Acceptance (`test_probation.py`): eligibility edges 9 sessions, 10 over 2 days, 10 over 3 days; origin excluded
- [x] Acceptance (`test_probation.py`): every L2 route row; no seed from feature-doc, non-durable or `unknown`
- [x] Acceptance (`test_probation.py`): no seed for a target with a live probation item in that session
- [x] Acceptance (`test_probation.py`): sync write scope by tree hash; no `ledger.json` string in `probation/`
- [x] Acceptance (`test_probation.py`): block ≤1,600 chars; skipped item not exposed; one `Next:` per session by priority; empty session ID logs nothing
- [x] Acceptance (`test_probation.py`): `report` `nothing_new` on equal counts; `null` rates; `resident_bytes` sum
- [x] Acceptance (`test_probation_actions.py`): `promote` edits only the block, records events with `upper_bound_95` ≈ 0.2589, no "improv"
- [x] Acceptance (`test_probation_actions.py`): failing gate keeps PROBATION; content-scan hit QUARANTINED
- [x] Acceptance (`test_probation_actions.py`): `demote` removes only the block and records `rollback`; missing block records DEMOTED
- [x] Acceptance (`test_memory_cli.py`): memory block then probation block; raising block is silent, exit 0
- [x] Acceptance (`test_evolve_probation_cli.py`): empty `--next`; retraction demotes at once; exit 2 on bad flags; disabled line exit 0
- [x] Acceptance: `tests/cli/test_check_budget.py` passes; plan task 9 pytest selection and ruff pass
