# Behavior gate — spec

confidence: INFERRED

## Intent

Prove that managed guidance *produces* the behavior it describes, rather than
merely carrying the text. dummyindex could already assert that a policy string
is present in every managed doc; it had no way to tell a rule that works from a
rule that is present and inert.

That gap was not hypothetical. `ALWAYS_ON_OUTPUT_POLICY` once *named* the
`i-have-adhd` skill instead of stating its rules, and because that skill ships
`disable-model-invocation: true`, the ADHD half of the policy was silently
dead in every managed repo. No test failed. The doc-sync guard was green. A
present-but-inert rule scored identically to a working one.

The gate closes that by measuring output shape, not vocabulary — a two-arm A/B
where the control arm is *expected to fail*. Ported from
`DietrichGebert/ponytail` (MIT, © 2026 DietrichGebert): `benchmarks/behavior.js`
(the grader), `benchmarks/behavior.yaml` + `benchmarks/arms/{baseline,ponytail}.js`
(the arms), and the `--selftest` discipline in `benchmarks/robustness-audit.js`.

## User-visible behavior

### The grader (`behavior_gate.py`) — deterministic, always runs

Scores one response against four observable rules of `ALWAYS_ON_OUTPUT_POLICY`:
`action_first`, `numbered_steps`, `specific_quantities`, `closing_action`.
Pure functions over a string — no model, no network, no third-party dependency.
`grade_response` returns a frozen `BehaviorVerdict`; `pass_rate` reduces a batch
to a per-check rate, which is what an arm-vs-arm delta is computed from.

The load-bearing design constraint is that it must measure **shape, not
vocabulary**. An earlier cut treated any inline backtick as a "concrete
artifact", so a reply could pass by backticking the policy's own words while
being verbose, unstructured and open-ended — reintroducing the exact defect the
feature exists to catch. An artifact now requires a slash, a dot-extension, or
a `file:line` shape.

### The selftest (`test_behavior_gate.py`) — proves the instrument at zero cost

Multiple known-passing and known-failing references per check, each chosen to
exercise one branch, so disabling any single discriminator turns the suite red.
Ships in the default `pytest -q` path. Includes trap fixtures — plain and
backticked — that talk about being concise while being none of it, and must
fail all four checks.

### The two-arm run (`behavior_arms.py`) — opt-in, model-dependent

The only model-dependent test in the repo. Shells out to the real `claude` CLI
(no API key, no SDK). Skipped at collection time unless
`DUMMYINDEX_BEHAVIOR_ARMS=1`, and carries the `behavior_arms` pytest marker.

Both arms share the host's default system prompt; the guidance arm adds
`ALWAYS_ON_OUTPUT_POLICY` via `--append-system-prompt` and the control arm adds
nothing. That symmetry is the whole experiment: an earlier revision used
`--system-prompt`, which *replaces* the default, making the guidance arm an
ablation ("the policy instead of the assistant") rather than a comparison. It
measured the ablation and reported the guidance arm as worse.

## Contracts

- The grader never calls a model, opens a socket, or shells out. Only the arms
  module does, and only under the opt-in gate.
- `ALWAYS_ON_OUTPUT_POLICY` is imported from
  `dummyindex/context/output/bootstrap.py`, never copied — one source of truth,
  the same rule the rule-copy canary enforces for the docs.
- Gate thresholds (`_CONTROL_GATE_CEILING`, `_GUIDANCE_GATE_FLOOR`) are fixed
  before a paid run and are **not** retuned to fit an observed result.
- Measured numbers live in `tests/eval/BEHAVIOR_BASELINE.md`, including runs
  that were discarded and why.

## Known limits

- **The acceptance has not been met.** The recorded run has the control arm
  failing its ceiling (0.33 ≤ 0.50, as designed) but the guidance arm at 0.56
  against a 0.60 floor. Guidance beat control on all four checks, so the
  direction is unambiguous; with 9 targeted observations per arm the *level* is
  not established. Raising the repeat count is the legitimate next step. The
  floor was deliberately left alone.
- The grader detects a rule being **dropped** reliably. It detects a rule being
  **contradicted** only for a named set of inversions — general contradiction
  detection in free prose is out of reach for a regex instrument, and the module
  docstring says so rather than implying otherwise.
- `incident_response` scores 0.00 in both arms — the one probe the policy does
  not move. Unresolved whether that is the probe, its two checks, or a real
  limit of the policy on open-ended triage.

## Related

- `bootstrap` — owns `ALWAYS_ON_OUTPUT_POLICY`, the subject under test.
- `cli-dispatch` — owns the rule-copy canary, the static half of the same
  problem: the canary proves the docs still *say* it, this gate probes whether
  saying it changes anything.
- `retrieval-eval` — the sibling eval in `tests/eval/`, and the source of the
  record-then-gate idiom (also ported from ponytail). Its `BASELINE.md` floors
  cover only retrieval.
