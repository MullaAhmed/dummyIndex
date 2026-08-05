# Behavior-gate two-arm baseline

Measured record for the model-dependent two-arm run
(`test_behavior_arms.py`, opt-in via `DUMMYINDEX_BEHAVIOR_ARMS=1`). Sibling of
`BASELINE.md`, which covers the deterministic retrieval eval only — the two
evals share a directory and nothing else.

This file exists because plan task 3's acceptance is a claim about a *measured*
delta, and `BASELINE.md`'s idiom is to write the observed number down rather
than eyeball it. ponytail itself never asserts its delta (see spec.md, "How the
delta is computed"); this port does, so the observation has to be recorded to
be checkable.

## Conditions

| | |
|---|---|
| Date | 2026-07-29 |
| Transport | `claude` CLI (`-p`, `--safe-mode`, `--tools ""`, `--output-format text`, `--no-session-persistence`) |
| Guidance arm | host default system prompt **+ `--append-system-prompt ALWAYS_ON_OUTPUT_POLICY`** |
| Control arm | host default system prompt, nothing appended |
| Probes | 3 (`incident_response`, `dependency_migration`, `loop_optimization`) |
| Repeats | 3 |
| Observations | 9 targeted per arm |
| Grader | `behavior_gate.py`, unchanged |
| Wall clock | ~11 min per sweep |

## Run 2 — the measurement of record

Guidance beats control on **every one of the four checks**.

| Check | Control | Guidance | Delta |
|---|---|---|---|
| `action_first` | 0.00 | 0.11 | **+0.11** |
| `numbered_steps` | 0.22 | 0.33 | **+0.11** |
| `specific_quantities` | 0.44 | 0.67 | **+0.22** |
| `closing_action` | 0.00 | 0.33 | **+0.33** |
| overall (targeted) | 0.33 | 0.56 | **+0.22** |
| overall (all four at once) | 0.00 | 0.00 | 0.00 |

Per probe (targeted checks only):

| Probe | Control | Guidance |
|---|---|---|
| `incident_response` | 0.00 | 0.00 |
| `dependency_migration` | 0.33 | 0.67 |
| `loop_optimization` | 0.67 | 1.00 |

### Acceptance: half held

Plan task 3 asks for two things.

- **"The control arm fails the gates" — HELD.** Control's targeted rate of
  0.33 is at or under `_CONTROL_GATE_CEILING = 0.5`.
- **"The guidance arm passes" — DID NOT HOLD.** Guidance reached 0.56 against
  `_GUIDANCE_GATE_FLOOR = 0.6`. The test fails, by design, and the floor was
  **not** lowered to make it green. Both thresholds were fixed before the first
  paid run; retuning them after seeing the number is the exact dishonesty this
  eval exists to prevent, and a 0.56 recorded as a pass would be worth less
  than a 0.56 recorded as a miss.

Two things are worth separating here. The *direction* is unambiguous and
consistent: four checks out of four moved the right way, and no check regressed.
The *level* is not established: with 9 targeted observations per arm, 0.56 is
5/9, and this sample cannot distinguish 0.56 from 0.60. Raising the repeat count
would tighten the estimate without touching the threshold; that is the legitimate
next step, and it is deliberately left undone rather than guessed at.

`incident_response` scored 0.00 in both arms — it is the only probe the policy
did not move at all, and the likeliest single cause of the shortfall. Whether
that is the probe, the two checks it targets (`action_first`, `closing_action`),
or a real limit of the policy on open-ended triage is unresolved.

## Run 1 — discarded, and why it is still written down

The first sweep measured control 0.56 / guidance 0.33 — the guidance arm
apparently *worse*, on every aggregate.

That result was an artifact, not a finding. The harness used
`--system-prompt`, which **replaces** the host's default system prompt rather
than adding to it. So the guidance arm was not "baseline plus the policy"; it
was "the policy *instead of* the assistant's ordinary scaffolding", with the
control arm meanwhile running a hand-written `"You are a helpful assistant."`
stand-in. That is an ablation of the system prompt, and it measured the
ablation. ponytail's own arms are additive — `arms/baseline.js` adds no system
message and `arms/ponytail.js` adds `SKILL.md` on top of the same provider
defaults — so the faithful port holds the base fixed and appends. Switching to
`--append-system-prompt`, with the control arm appending nothing, reversed the
sign on all four checks.

| Check | Run 1 (confounded) | Run 2 (corrected) |
|---|---|---|
| `action_first` | −0.33 | +0.11 |
| `numbered_steps` | −0.11 | +0.11 |
| `specific_quantities` | +0.11 | +0.22 |
| `closing_action` | +0.22 | +0.33 |
| overall (targeted) | −0.22 | +0.22 |

Run 1 is kept because a discarded measurement that is not written down is a
measurement nobody can check. It is also the more useful of the two for a
future reader: it shows that this eval's headline number is sensitive to how
the arms are constructed, and that a plausible-looking harness can invert its
own result.
