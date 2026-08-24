# Checklist — reconcile-guardrails-maintain

> Waves strictly ordered; within a wave items are file-disjoint (proof: `plan.md`
> § Wave disjointness). Same-file successors are separate waves by construction.

## Wave 1 — foundations

- [x] T1 config schema v5: `build.auto_recouncil` + v4→v5 read-migration —
      `dummyindex/context/domains/config.py`
- [x] T2 fleet domain: `FleetRun/FleetUnit`, `create_run/load_run/next_unit/
      mark_done/run_status`, atomic writes — `dummyindex/context/domains/fleet.py` (NEW)

## Wave 2

- [x] T3 estimator `estimate_run` reusing `enrich.build_plan` +
      `council_batch.active_stages` — `dummyindex/context/domains/fleet.py` (after T2)
- [x] T5 anchor auto-heal on stamp behind `--heal-orphaned`; default refusal
      unchanged without flag — `dummyindex/cli/reconcile.py`

## Wave 3 — surfaces

- [x] T4 `context maintain plan|begin|next|done|stamp|status` CLI +
      registry seam — new `dummyindex/cli/maintain.py`, `cli/__init__.py`
- [x] T6 build-skill closing-phase contract (`--no-recouncil`,
      `build.auto_recouncil`) — `dummyindex/skills/build/SKILL.md`,
      `dummyindex/skills/plan/SKILL.md`
- [x] T7 expose `auto_recouncil` in build-loop check/status payloads —
      `dummyindex/cli/build_loop/waves.py`

## Wave 4 — tests (disjoint files)

- [x] T8a create/next/done/status/resume — `tests/context/domains/test_fleet.py` (NEW)
- [x] T8b verb wiring, scope guard, `--all` requirement — `tests/cli/test_maintain.py` (NEW)
- [x] T8c v5 migration + default/false — extend existing config test file
- [x] T8d orphan heal path + unchanged default refusal —
      `tests/context/build/test_reconcile.py`

## Wave 5 — acceptance

- [x] A1 maintain lifecycle test green (plan/begin/next/done/stamp/status) — via dummyindex-verify
- [x] A2 resume-from-corrupt-state never repeats done units — via dummyindex-verify
- [x] A3 scope guard: truncation + `begin --max-features 1` refuses without `--all` — via dummyindex-verify
- [x] A4 v4 config opens; auto_recouncil defaults True; false honoured end-to-end in payload — via dummyindex-verify
- [x] A5 full suite `python -m pytest tests/ -q --tb=short` green — via dummyindex-verify (3202 passed, 2 skipped)
- [x] **GATE** G1 resolved by orchestrator ruling: Q1 = opt-in `--heal-orphaned`
      on reconcile-stamp (default refusal unchanged); Q2 = `.context/fleet/` owned by
      fleet-runner; maintain runs use the `maintain-*` prefix under it (HOW_TO_USE's
      committed-layout table is NOT edited here — fleet-runner adds that row)
- [x] A6 landing commit uses `feat:` type; body names schema v5 and the fleet dir.
      No hand-edit of `CHANGELOG.md`.
