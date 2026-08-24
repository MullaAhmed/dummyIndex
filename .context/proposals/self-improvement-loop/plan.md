# Plan — self-improvement-loop

> Ordered, file-path-naming tasks; reuse over net-new. All paths verified.

## Tasks

1. **Evolve domain.** New `dummyindex/context/domains/evolve.py`:
   - `harvest(context_dir, since=None) -> HarvestReport` composing parsers: audit
     reports (reuse domain constants `AUDITS_REL`/workspace roots re-exported by
     `gc/constants.py`, not the CLI-private `_workspace_rel`), session-memory md
     (simple section scan), reconcile delta fields (`compute_reconcile_report`:
     drifted_features/unassigned_new_files/awaiting_enrichment), and NEW transcript
     content scanner for adoption misses (discovery reused from
     `dummyindex/usage/transcripts.py`; content analysis net-new).
   - candidate validation `validate_candidate(obj, context_dir) -> list[str]` errors;
     scope guard lives here.
   - gate runner `run_gate(candidate, staged_dir, run_dir) -> GateResult`: when the
     target maps to a suite, deterministic scoring via `equip/eval/score.py::score_run`
     reusing its parsers (`parse_eval_suite`, `parse_observations`) over
     `<run>/observations.json` — catching MissingObservationError/ObservationsError/
     ObservationMismatchError per stage; pytest subset via subprocess `-k`; ruff on
     touched py; any error/missing stage blocks the verdict.
   - JSONL appender `record(event)` for `.context/gc/evolution.jsonl` (tolerant reads).
2. **Prediction re-check.** In `evolve.py`: `check_predictions(report) -> flags`
   comparing open predictions in evolution.jsonl against fresh harvest items sharing
   evidence paths.
3. **CLI subcommand.** New `dummyindex/cli/evolve.py` with subverbs
   `harvest|diagnose|apply|promote|rollback|discard` following the multi-subcommand
   layout of `cli/gc.py`. Full registration seam (shared with proposals B/C/E —
   coordinate landing): `context/enums.py::ContextSubcommand`, `cli/__init__.py`
   `_HANDLERS`, `cli/help.py` USAGE/usage_for.
4. **Skill procedure + packaging.** New packaged skill
   `dummyindex/skills/evolve/SKILL.md`: the host-side loop (harvest -> diagnose via LLM
   writing candidates + producing equipment-eval observations files -> apply/gate/
   promote per CLI verdicts -> falsification round), sleep contract. Thin: all state in
   CLI artifacts. Register for shipping: add `skills/evolve/*.md` to pyproject
   `[tool.setuptools.package-data]`, add `("evolve", "dummyindex-evolve")` to
   `installer/common.py::_SIBLING_SKILLS`, and update the derived installer/doc-sync
   tests they police. Also amend `.context/HOW_TO_USE.md` gc/ layout note +
   `playbooks/gc-context.md` for evolution.jsonl (same landing).
5. **Tests** (disjoint files):
   - new `tests/context/domains/test_evolve.py` - harvest/validation/scope-guard/prediction.
   - new `tests/cli/test_evolve_cli.py` - lifecycle + JSONL transitions.
   - fixtures under `tests/fixtures/evolve/` (audit report snippet, session-memory
     snippet, usage transcript fixture) - new files, disjoint.

## Wave disjointness

| Wave | Items | Files |
|---|---|---|
| 1 | T1 | `domains/evolve.py` (NEW) |
| 1 | T5f | fixtures (disjoint) |
| 2 | T2 | `domains/evolve.py` - serial after T1 |
| 3 | T3 | `cli/evolve.py` (NEW), `context/enums.py`, `cli/__init__.py`, `cli/help.py` |
| 3 | T4 | packaged `skills/evolve/SKILL.md` (NEW), `pyproject.toml`, `installer/common.py`, installer doc-sync tests |
| 4 | T5a-T5c | one distinct test file each |
