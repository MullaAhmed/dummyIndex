## Correctness of the instrument

- **The grader is a regex heuristic, and its ceiling is real.** It reliably
  detects a rule being *dropped*. It detects a rule being *contradicted* only
  for a named set of inversions. An adversarial pass applied 7 fresh
  contradiction shapes — a hedge that guts the rule, an appended exception
  clause, reversed precedence, a "prefer X but Y is fine" softener — and most
  passed. The module docstring states this rather than implying coverage it
  does not have. Do not reword it into a stronger claim.
- **Held-out agreement is ~97%, not 100%.** An independent 32-case set found
  one disagreement (a past-tense statement read as a next action). Treat the
  per-check rate as a signal with a few points of noise, not a measurement.
- **`action_first` is lead-only by design.** A reply whose first line names a
  real path but is otherwise pure hedging passes. Consistent with
  one-rule-per-check, but it means a small control-arm leak is expected and is
  not noise.
- **`_is_single_bounded_action` has an escape hatch.** A terse multi-step reply
  built from verbs outside `_ACTION_VERBS` can pass `numbered_steps`
  vacuously. Mitigated by a coordinated-list detector, but the verb list is
  closed and a sufficiently plain reply can still slip.

## Cost and flakiness

- **The arms test spends real tokens on the user's account.** ~11 minutes and
  a few dozen CLI invocations per sweep at 3 probes × 2 arms × 3 repeats. It is
  skipped at *collection* time, before `behavior_arms` is even imported, so a
  default `pytest -q` cannot shell out. Verified by running the default suite
  with `claude` off `PATH`.
- **A CLI timeout is a harness failure, not a signal.** `_DEFAULT_TIMEOUT_S` is
  600s precisely because a 180s ceiling aborted a real sweep mid-run and wasted
  every call before it.
- **The gate is model-version-sensitive.** Both arms run whatever `claude`
  resolves to. A model update moves both rates; the recorded numbers are pinned
  to a date and a transport, not to a model id.

## Discipline

- **Never retune a threshold to fit an observed result.** The recorded run
  misses its floor (0.56 vs 0.60) and the floor was left alone. A green gate
  bought by moving the bar would make this whole feature worse than not having
  it — it is an honesty instrument first.
- **Discarded measurements stay written down.** `BEHAVIOR_BASELINE.md` keeps
  the confounded first run, because a run that is thrown away without a record
  is a run nobody can check. That run is also the more instructive of the two:
  it shows a plausible-looking harness inverting its own result.

## Coupling

- **One source of truth for the policy.** `ALWAYS_ON_OUTPUT_POLICY` is
  imported, never copied. If that import is ever replaced by a literal, this
  feature stops testing the shipped policy and starts testing a stale copy of
  it — the same failure mode the rule-copy canary guards on the docs side.
- **The grader lives under `tests/`.** Importable (`tests.eval.behavior_gate`)
  following the existing `tests/paths.py` precedent, but it is test-support
  code: nothing in `dummyindex/` may depend on it.
