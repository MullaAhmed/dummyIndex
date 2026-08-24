# Checklist — self-improvement-loop

> Waves strictly ordered; within-wave items file-disjoint (proof: `plan.md`
> § Wave disjointness).
>
> **G1 settled (orchestrator ruling):** targeted pytest subset = subprocess
> `python -m pytest <tests-matching-changed-path-segments> -q`; when no
> segment matches any test file, record stage `not_applicable` honestly.
> Implemented in `domains/evolve.py::_matching_test_files`/`_stage_pytest`;
> pinned by `test_pytest_stage_runs_matching_subset_or_records_not_applicable`.

## Wave 1 — domain + fixtures

- [x] T1 evolve domain: harvest parsers (audits, session-memory, gc learnings,
      reconcile blockers, usage adoption), candidate validation + scope guard,
      gate runner, JSONL recorder — `dummyindex/context/domains/evolve.py` (NEW)
- [x] T5f fixtures: audit snippet, session-memory snippet, usage transcript —
      `tests/fixtures/evolve/` (NEW)

## Wave 2

- [x] T2 prediction re-check against fresh harvest —
      `dummyindex/context/domains/evolve.py` (after T1)

## Wave 3 — surfaces

- [x] T3 `context evolve` subverbs + full registration seam — new
      `dummyindex/cli/evolve.py`, `context/enums.py`, `cli/__init__.py`,
      `cli/help.py`
- [x] T4 skill + packaging + docs: `dummyindex/skills/evolve/SKILL.md` (NEW),
      `pyproject.toml` package-data, `installer/common.py` sibling entry +
      derived-test updates, HOW_TO_USE.md gc/ note, playbooks/gc-context.md

## Wave 4 — tests

- [x] T5a domain tests: parse/citations/validation/scope/predictions —
      `tests/context/domains/test_evolve.py` (NEW)
- [x] T5b CLI lifecycle + one JSONL line per transition —
      `tests/cli/test_evolve_cli.py` (NEW)
- [x] T5c installer/doc-sync tests updated for the evolve family

## Wave 5 — acceptance

> Seam landing order GATE: B lands after C's USAGE edits (shared enums/_HANDLERS/help.py
> seam); append-only discipline for USAGE rows.

- [x] A1 domain tests green — via dummyindex-verify
- [x] A2 lifecycle green incl. gate-fail rollback, gate-pass promote, and blocked-verdict on all four observation shapes (absent/partial/duplicated/mismatched); promote-without-override refused — via dummyindex-verify
- [x] A2b sleep no-op exits 0 — via dummyindex-verify
- [x] A3 flipped prediction flagged in next harvest — via dummyindex-verify
- [x] A4 scope guard rejects source-code target — via dummyindex-verify
- [x] A5 full suite `python -m pytest tests/ -q --tb=short` green — via dummyindex-verify
- [x] **GATE** G1 settle spec Q1 (targeted-pytest subset definition) before landing.
- [x] A6 landing commit uses `feat:` type; body names evolution.jsonl as the decision
      history. No hand-edit of `CHANGELOG.md`.
