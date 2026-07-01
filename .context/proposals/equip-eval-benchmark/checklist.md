# Checklist — equip-eval-benchmark

> Wave headings group mutually-independent items (disjoint files). Waves run in
> order. Tick `- [x]` only after verifying each item. Generated specialists are
> keyword-routed (untagged); `— via` tags name plugin/skill executors.

## Wave 1 — pure alphabets & errors
- [x] `EvalOutcome(str, Enum)` in `dummyindex/context/domains/equip/eval/enums.py`
- [x] `EvalError(EquipError)` hierarchy (`EvalSuiteError`, `ObservationsError`, `EvalSuiteNotFoundError`, `ObservationMismatchError`, `MissingObservationError`) in `dummyindex/context/domains/equip/eval/errors.py`
- [x] Add `EVAL` + `BENCHMARK` to `EquipVerb` (`equip/enums.py`) and `EVALS_REL = "equipment-evals"` (`equip/lifecycle/manifest.py`)

## Wave 2 — data shapes
- [x] Frozen `EvalCase` / `TriggerObservation` / `EvalResult` / `BenchmarkReport` + `to_dict()` in `dummyindex/context/domains/equip/eval/models.py`

## Wave 3 — pure logic
- [x] `score_run` + `aggregate_benchmark` in `dummyindex/context/domains/equip/eval/score.py`
- [x] `parse_eval_suite` / `parse_observations` / `*_to_dict` in `dummyindex/context/domains/equip/eval/cases.py`

## Wave 4 — package surface + pure-core unit tests
- [x] Public re-exports in `dummyindex/context/domains/equip/eval/__init__.py`
- [x] Scorer unit tests in `tests/context/domains/equip/eval/test_score.py`
- [x] Parse/serialize + round-trip tests in `tests/context/domains/equip/eval/test_cases.py`
- [x] No-LLM guard test in `tests/context/domains/equip/eval/test_no_llm_in_eval.py`

## Wave 5 — CLI eval/benchmark handlers
- [x] `_safe_tool_name` + `run_eval` + `run_benchmark` (wire-only; `EVALS_REL` paths, tool-name sanitization → exit 2, exit codes 2/1/0, `--run-label` collision guard, fail-open benchmark that writes nothing, glob excludes `*.tmp`) in `dummyindex/cli/equip/eval.py`

## Wave 6 — routing + contract test
- [x] Route `EVAL` + `BENCHMARK` (+ verb-table docstring) in `dummyindex/cli/equip/dispatch.py`
- [x] CLI end-to-end + schema contract test in `tests/cli/equip/test_equip_eval_cli.py`

## Wave 7 — skill loop + optional wiring
- [x] **(Required)** Document the suite JSON schema, hand-authoring steps, synthetic-prompt warning, and the dispatch → observe → `equip eval` → `benchmark` → `patch` loop in the `dummyindex-equip` skill markdown (`dummyindex/skills/equip/`); grep-able doc assertion
- [x] **(Optional)** Seed starter `<tool>.suite.json` in the `dispatch.py` `_apply_write` path (NOT pure `catalog.py`) + surface "unevaluated" via new `StatusReport.unevaluated` field at the CLI status handler (`lifecycle/status.py`, not `ItemState`) — ship only if Waves 1–6 are clean

## Wave 8 — verify, review, reconcile
- [x] Full suite green — via `/dummyindex-verify`
- [x] Review the diff against equip conventions & concerns — via `/code-review`
- [x] **GATE** Reconcile the new eval stage into `.context/features/equip/*` (main-session reconcile procedure)
- [x] Acceptance: `equip eval` writes a pinned-shape result and lists FP/FN cases; `equip benchmark` reports variance + flaky cases; absent runs fail-open (exit 0)
