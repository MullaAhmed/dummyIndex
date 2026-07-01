# Plan — Fold skill-creator eval/benchmark loop into equip: measure + benchmark generated skills/specialists

> Ordered, file-path-naming tasks. Cite reused symbols from
> `.context/map/symbols.json` where reuse beats new code. Tooling tags: generated
> specialists (`python-implementer`, `python-tester`, `dummyindex-reviewer`,
> `dummyindex-docs-specialist`, `dummyindex-verify`) are keyword-routed by build,
> so those tasks stay **untagged**; only plugin/skill executors get a `— via` tag.

## Tasks

### 1. Pure alphabets & errors

1. Add `EvalOutcome(str, Enum)`
   (`TRUE_POSITIVE`/`FALSE_POSITIVE`/`TRUE_NEGATIVE`/`FALSE_NEGATIVE`) in
   **`dummyindex/context/domains/equip/eval/enums.py`** — follows the closed-alphabet
   `(str, Enum)` rule (`equip/enums.py:EquipmentKind` as the pattern).
2. Add the typed exception hierarchy in
   **`dummyindex/context/domains/equip/eval/errors.py`** — `EvalError(EquipError)`
   base (bases on `EquipError` so the CLI's existing `except EquipError` catches
   it) + `EvalSuiteError`, `ObservationsError`, `EvalSuiteNotFoundError`,
   `ObservationMismatchError`, `MissingObservationError`. Mirrors
   `equip/errors.py`.
3. Add `EVAL` + `BENCHMARK` members to `EquipVerb` in
   **`dummyindex/context/domains/equip/enums.py`**, and `EVALS_REL =
   "equipment-evals"` beside `EQUIPMENT_REL` in
   **`dummyindex/context/domains/equip/lifecycle/manifest.py`** (a sibling dir —
   `EQUIPMENT_REL` is a *filename*, not a dir root, and `.context/equipment/`
   would shadow `equipment.json`). Both existing files; different from the new
   `eval/enums.py`.

### 2. Data shapes

4. Define the frozen dataclasses `EvalCase`, `TriggerObservation`, `EvalResult`,
   `BenchmarkReport` — each with a hand-written `to_dict()` and `tuple[...]`
   collection fields — in **`dummyindex/context/domains/equip/eval/models.py`**,
   following `equip/models.py` and `conventions/coding-practices.md`
   (frozen, data-only, `to_dict()`).

### 3. Pure logic

5. Implement `score_run(cases, observations) -> EvalResult` and
   `aggregate_benchmark(results) -> BenchmarkReport` in
   **`dummyindex/context/domains/equip/eval/score.py`** — pure. Honour the pinned
   conventions: **zero-denominator precision/recall ⇒ `0.0`**, accuracy always
   defined; **bidirectional coverage** (`ObservationMismatchError` for an extra
   observation, `MissingObservationError` for an unobserved case);
   **population** variance (÷N); same-`case_id`-set requirement across runs
   (`EvalError` on mismatch); `<2` runs ⇒ `0.0` variance + empty flaky list.
6. Implement `parse_eval_suite`, `parse_observations`, `suite_to_dict`,
   `result_to_dict`, `benchmark_to_dict` in
   **`dummyindex/context/domains/equip/eval/cases.py`** — pure parse/serialize,
   fail-fast: `EvalSuiteError` on a malformed suite **or a duplicate `case_id`**
   (the join + flaky key), `ObservationsError` on malformed observations (both
   wrap `json.JSONDecodeError`).

### 4. Package surface + unit tests for the pure core

7. Re-export the public surface (`EvalCase`, `TriggerObservation`, `EvalResult`,
   `BenchmarkReport`, `EvalOutcome`, `score_run`, `aggregate_benchmark`, the
   parse/serialize helpers, the error types) from
   **`dummyindex/context/domains/equip/eval/__init__.py`** — the test surface,
   per the canonical-trio layering rule.
8. Unit-test the scorer in
   **`tests/context/domains/equip/eval/test_score.py`** — confusion matrix on
   positive/negative/mixed fixtures, purity (no I/O), `ObservationMismatchError`,
   benchmark mean/variance + flaky-iff-differs.
9. Unit-test parse/serialize + round-trip in
   **`tests/context/domains/equip/eval/test_cases.py`** — malformed input raises
   `EvalSuiteError`; `dict → parse → to_dict` round-trips.

### 5. CLI eval/benchmark handlers

10. Implement `run_eval(rest) -> int`, `run_benchmark(rest) -> int`, and a shared
    `_safe_tool_name(tool) -> str` in **`dummyindex/cli/equip/eval.py`** —
    wire-only, following the `cli/equip/install.py` handler shape:
    - `_safe_tool_name` validates `^[A-Za-z0-9._-]+$` (reject `/`, `..`, leading
      `.`) and exits **2** on an unsafe name — **before** any path is built
      (vendored tool names are attacker-controllable).
    - Resolve paths under `EVALS_REL` (`.context/equipment-evals/`), read suite +
      observations, call the pure `score_run`, write with
      `atomic_io.write_text_atomic`. **Exit codes**: `2` = bad flags / unsafe name
      / missing suite; `1` = malformed suite or observations content (catch
      `OSError`/`json.JSONDecodeError` for **both** files); `0` = scored. Reject a
      `--run-label` collision unless `--force`. Print each misfire's `case_id` +
      `EvalOutcome`.
    - `run_benchmark`: guard `evals_dir.is_dir()`, glob `<tool>.run-*.result.json`
      **excluding `*.tmp`**, aggregate, write `<tool>.benchmark.json`. **Fail-open**
      (warn + exit `0`, write nothing) on missing dir / zero runs; a labelless
      `<tool>.result.json` with no `run-*` files warns to re-run with `--run-label`.

### 6. Routing + result-shape contract test

11. Route `EVAL` + `BENCHMARK` to the new handlers in
    **`dummyindex/cli/equip/dispatch.py`** (sibling to the existing
    `run_install`/`run_discover` routing at `dispatch.py:96-134`); extend the
    module docstring's verb table.
12. CLI + **schema contract test** in
    **`tests/cli/equip/test_equip_eval_cli.py`** — end-to-end `equip eval`
    (writes `<tool>.result.json` in the pinned shape; lists FP/FN cases; missing
    suite ⇒ exit 2), `equip benchmark` (aggregates ≥2 runs; absent runs ⇒ warn +
    exit 0), and a contract test that fails on any result/benchmark JSON drift.
13. Add guard tests in
    **`tests/context/domains/equip/eval/test_no_llm_in_eval.py`**: an **AST
    import-scan** of `eval/*.py` asserting no `subprocess`/network import, **and**
    a positive purity test that runs `score_run` with `open`/`Path.read_text`
    monkeypatched to raise — proving trigger decisions arrive only as in-memory
    data, not read from disk.

### 7. Skill-side loop + optional wiring

14. Add the "evaluate a generated tool" procedure to the **`dummyindex-equip`
    skill markdown** (repo source under `dummyindex/skills/equip/`) — **required,
    not stretch** (the eval verb is dead without a suite): document (a) the
    **suite JSON schema and how to hand-author one**, (b) the
    dispatch → observe (blind LLM firing judgment) → `equip eval` → `equip
    benchmark` → `equip patch` improve loop, and (c) a warning to use **synthetic,
    non-secret prompts** (suites are committed under `.context/`). A grep-able
    assertion (extend `tests/test_skills_doc_hygiene.py` or a sibling) checks the
    three CLI touchpoints + the blind-judgment step are named.
15. **(Optional / stretch — ship only if Waves 1–6 land clean)** Two additive
    wirings, each honouring the pure-domain / CLI-boundary split:
    - Seed a starter `<tool>.suite.json` per generated tool **in the
      `cli/equip/dispatch.py` `_apply_write` path only** (NOT the pure
      `generate/catalog.py`), under the atomic never-clobber guard, deriving
      positive cases from the item's `capabilities`.
    - Surface **"unevaluated"** tools in `equip status` via a **new
      `StatusReport.unevaluated: tuple[str, ...]` field**
      (**`dummyindex/context/domains/equip/lifecycle/status.py`**), populated at
      the **CLI status handler** (globs the evals dir). Do **not** touch
      `ItemState` — evaluation-state is orthogonal to the origin-hash lifecycle.

### 8. Verify, review, reconcile

16. Run the full suite green (`conventions/testing.md`) — via `/dummyindex-verify`.
17. Review the diff against equip's conventions & concerns — via `/code-review`.
18. Reconcile the new eval stage into `.context/features/equip/*`
    (`spec.md`/`flows`) — main-session reconcile procedure (build closes this loop).
