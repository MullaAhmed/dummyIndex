# Checklist — fleet-runner

> Waves strictly ordered; within-wave items file-disjoint (proof: `plan.md`
> § Wave disjointness).

## Wave 1 — domain + fixtures

- [x] T1 fleetrun domain: `init_run/load_run/next_units/checkpoint/add_spend/
      merge_order`, committed RUN-MANIFEST + state.json, budget breaker, gated-skip,
      disjointness frozen from intake paths[] / member_files; revision+retry RMW;
      loud-fail with repair instructions; init ordering; deterministic sort key —
      `dummyindex/context/domains/fleetrun.py` (NEW)
- [x] T4f fixture proposals (overlapping + disjoint member sets) —
      `tests/fixtures/fleetrun/` (NEW)

## Wave 2 — surfaces

- [x] T2 `context fleet init|next|checkpoint|spend|merge-order|status` CLI +
      full registration seam — new `dummyindex/cli/fleet.py`, `context/enums.py`,
      `cli/__init__.py`, `cli/help.py`

## Wave 3 — skill + packaging

- [x] T3 packaged babysitter skill (intake, grouping, forks, orchestrator ground
      rules, dormant probes, resume-from-state, opt-in merge; zero hardcoded
      identifiers) — `dummyindex/skills/fleet/SKILL.md` (NEW); pyproject package-data;
      `installer/common.py` sibling entry + derived-test updates

## Wave 4 — tests

- [x] T4a domain: priority/cap/disjointness/gated/budget-halt/resume —
      `tests/context/domains/test_fleetrun.py` (NEW)
- [x] T4b CLI lifecycle to done; stable merge-order; anti-stall empty envelope —
      `tests/cli/test_fleet_cli.py` (NEW)
- [x] T4c installer/doc-sync tests updated for the fleet family; HOW_TO_USE.md
      committed-layout table gains the `.context/fleet/` row (this proposal owns the
      namespace decision, resolving reconcile-guardrails-maintain Q2)

## Wave 4 — acceptance

- [x] A1 domain matrix green incl. breaker trip + explicit `spend --adjust` resume;
      concurrent checkpoint/spend under retry-RMW never loses increments — via dummyindex-verify
- [x] A1b init refuses zero-unit runs and duplicate slugs; missing paths[] warns and
      serializes — via dummyindex-verify
- [x] A2 lifecycle green; merge-order deterministic — via dummyindex-verify
- [x] A3 fully-gated run terminates with valid empty envelope, exit 0 — via dummyindex-verify
- [x] A4 doc grep: red-flag rules present; no hardcoded project identifiers — via dummyindex-verify
- [x] A5 full suite `python -m pytest tests/ -q --tb=short` green — via dummyindex-verify
- [x] A6 landing commit uses `feat:` type; body names the committed run-manifest
      contract. No hand-edit of `CHANGELOG.md`.
