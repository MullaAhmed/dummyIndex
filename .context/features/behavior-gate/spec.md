# Behavior gate — spec

confidence: INFERRED

## Intent

Prove that managed guidance *produces* the behavior it describes. Carrying the text is not enough. dummyindex could already assert that a policy string is present in every managed doc. It had no way to tell a working rule from a rule that is present and inert.

That gap was not hypothetical. `ALWAYS_ON_OUTPUT_POLICY` once *named* the `i-have-adhd` skill instead of stating its rules. That skill ships `disable-model-invocation: true`, so the ADHD half of the policy was silently dead in every managed repo. No test failed. The doc-sync guard was green. A present-but-inert rule scored identically to a working one.

The gate closes that by measuring output shape, not vocabulary. It is a two-arm A/B where the control arm is *expected to fail*.

Ported from `DietrichGebert/ponytail` (MIT, © 2026 DietrichGebert):

- `benchmarks/behavior.js`: the grader.
- `benchmarks/behavior.yaml` and `benchmarks/arms/{baseline,ponytail}.js`: the arms.
- The `--selftest` discipline in `benchmarks/robustness-audit.js`.

## User-visible behavior

### The grader (`behavior_gate.py`) — deterministic, always runs

Scores one response against four observable rules of `ALWAYS_ON_OUTPUT_POLICY`: `action_first`, `numbered_steps`, `specific_quantities`, `closing_action`. Pure functions over a string. No model, no network, no third-party dependency.

`grade_response` returns a frozen `BehaviorVerdict`. `pass_rate` reduces a batch to a per-check rate. An arm-vs-arm delta is computed from that rate.

The load-bearing design constraint is that it must measure **shape, not vocabulary**. An earlier cut treated any inline backtick as a "concrete artifact". A reply could then pass by backticking the policy's own words while being verbose, unstructured, and open-ended. That reintroduced the defect the feature exists to catch. An artifact now requires a slash, a dot-extension, or a `file:line` shape.

### The selftest (`test_behavior_gate.py`) — proves the instrument at zero cost

Multiple known-passing and known-failing references per check. Each one exercises one branch. Disabling any single discriminator turns the suite red. The selftest ships in the default `pytest -q` path.

Trap fixtures, plain and backticked, talk about being concise while being none of it. They must fail all four checks.

### The two-arm run (`behavior_arms.py`) — opt-in, model-dependent

This is the only model-dependent test in the repo. It shells out to the real `claude` CLI, with no API key and no SDK. It is skipped at collection time unless `DUMMYINDEX_BEHAVIOR_ARMS=1`. It carries the `behavior_arms` pytest marker.

Both arms share the host's default system prompt. The guidance arm adds `ALWAYS_ON_OUTPUT_POLICY` via `--append-system-prompt`. The control arm adds nothing. That symmetry is the whole experiment.

An earlier revision used `--system-prompt`, which *replaces* the default. That made the guidance arm an ablation ("the policy instead of the assistant"), not a comparison. It measured the ablation and reported the guidance arm as worse.

## Contracts

- The grader never calls a model, opens a socket, or shells out. Only the arms module does, and only under the opt-in gate.
- `ALWAYS_ON_OUTPUT_POLICY` is imported from `dummyindex/context/output/bootstrap.py`. It is never copied. This is one source of truth, the same rule the rule-copy canary enforces for the docs.
- Gate thresholds (`_CONTROL_GATE_CEILING`, `_GUIDANCE_GATE_FLOOR`) are fixed before a paid run. They are **not** retuned to fit an observed result.
- Measured numbers live in `tests/eval/BEHAVIOR_BASELINE.md`. That file includes runs that were discarded, and why.

## Known limits

- **The acceptance has not been met.** The recorded run has the control arm failing its ceiling (0.33 ≤ 0.50, as designed). The guidance arm reached 0.56 against a 0.60 floor. Guidance beat control on all four checks, so the direction is unambiguous. With 9 targeted observations per arm, the *level* is not established. Raising the repeat count is the legitimate next step. The floor was deliberately left alone.
- The grader detects a rule being **dropped** reliably. It detects a rule being **contradicted** only for a named set of inversions. General contradiction detection in free prose is out of reach for a regex instrument. The module docstring says so.
- `incident_response` scores 0.00 in both arms. It is the one probe the policy does not move. Unresolved whether the cause is the probe, its two checks, or a real limit on open-ended triage.

## Related

- `bootstrap` — owns `ALWAYS_ON_OUTPUT_POLICY`, the subject under test.
- `cli-dispatch` — owns the rule-copy canary, the static half of the same problem. The canary proves the docs still *say* it. This gate probes whether saying it changes anything.
- `retrieval-eval` — the sibling eval in `tests/eval/`, and the source of the record-then-gate idiom (also ported from ponytail). Its `BASELINE.md` floors cover only retrieval.
