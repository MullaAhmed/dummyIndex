# Behavior gate — plan

confidence: INFERRED

## Bounded context

This feature lives **wholly under `tests/eval/`** and adds nothing to
`dummyindex/`. Six files:

- `behavior_gate.py` — the grader: `BehaviorCheck`, `CheckVerdict`,
  `BehaviorVerdict`, `grade_response`, `grade_batch`, `pass_rate`.
- `behavior_gate_fixtures.json` — known-passing / known-failing references,
  multiple per check, each chosen to exercise one branch.
- `test_behavior_gate.py` — the selftest. Default `pytest -q` path.
- `behavior_arms.py` — the two-arm harness: `Arm`, `Probe`, `run_arm`,
  `run_two_arm`, `build_report`, `format_report`.
- `test_behavior_arms.py` — the opt-in runner.
- `BEHAVIOR_BASELINE.md` — the measured record.

The production surface is consumed **read-only** through exactly one import
seam: `ALWAYS_ON_OUTPUT_POLICY` from `dummyindex/context/output/bootstrap.py`.
Nothing under `dummyindex/` imports this feature, and nothing here mutates
repo state.

## Layering

```
test_behavior_arms.py  (opt-in gate: DUMMYINDEX_BEHAVIOR_ARMS=1)
        │
behavior_arms.py  ──subprocess──>  `claude` CLI
        │                            (--safe-mode, --tools "",
        │                             --append-system-prompt <policy|nothing>)
        ▼
behavior_gate.py  (pure; no I/O, no model, no network)
        ▲
test_behavior_gate.py  +  behavior_gate_fixtures.json   (default path)
```

The grader never learns which arm produced a response. That separation is what
lets the same instrument score both arms and lets the selftest prove the
instrument without spending anything.

## Ordering rationale

The grader and its selftest landed **before** the arms, deliberately — ponytail's
`--selftest` discipline ("no API: prove every check is correct") applied to the
first model-dependent gate in this repo. An instrument that has not been proven
at zero cost should not be pointed at a paid run.

## Design decisions

1. **Score output shape, never vocabulary.** A grader that greps for the
   policy's words would score a present-but-inert rule identically to a working
   one — reproducing the exact defect the feature exists to catch. Trap
   fixtures (plain and backticked) enforce this from the test side.
2. **All four checks run on every response**, unlike ponytail's
   single-check-per-probe dispatch (`behavior.js:48-53`). The caller selects
   which check a probe targets via `Probe.targets`, so the divergence is in
   where selection happens, not in what is measured.
3. **Both arms share the host default system prompt.** Only the guidance arm
   appends. See the spec's note on why `--system-prompt` was wrong.
4. **Thresholds are pre-registered.** `_CONTROL_GATE_CEILING = 0.5`,
   `_GUIDANCE_GATE_FLOOR = 0.6`, fixed before the first paid run and not
   adjusted afterward.
5. **Assert the delta rather than eyeball it.** ponytail leaves arm comparison
   to `promptfoo view`; this port asserts, matching `BASELINE.md`'s
   record-a-number-then-gate-below-it idiom.

## Follow-ups

- Raise the repeat count to separate 0.56 from the 0.60 floor. The threshold
  stays fixed; only `n` moves.
- Decide whether `incident_response` is a bad probe or a real limit of the
  policy on open-ended triage.
- The grader is importable but unused outside `tests/eval/`. If anything in
  `dummyindex/` ever needs it, it has to move out of `tests/`.
