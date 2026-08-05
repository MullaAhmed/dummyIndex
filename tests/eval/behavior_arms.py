"""Two-arm, model-dependent behavior-gate run over ``ALWAYS_ON_OUTPUT_POLICY``.

This is the spec's Item 1 (ADOPT), task 3:
`.context/proposals/repo-adoptions-ponytail-headroom/plan.md`. Wires the
task 2 grader (`tests/eval/behavior_gate.py`, imported **unchanged**) to two
real arms, following ``DietrichGebert/ponytail`` (MIT, © 2026 DietrichGebert)
per the credit idiom at ``tests/eval/test_retrieval_eval.py:11``:

- **Arm construction mirrors ``benchmarks/arms/{baseline,ponytail}.js``.**
  ``baseline.js`` (`:1-2`) sends only the user task, no system message; this
  port's :data:`Arm.CONTROL` appends nothing to the host's default system
  prompt, which is the faithful analogue — ponytail's baseline adds nothing
  rather than substituting a stand-in. Both arms therefore share an identical
  base and differ by exactly the policy text. ``ponytail.js`` (`:1-8`) reads the repo's
  own ``skills/ponytail/SKILL.md`` off disk at eval time and sends it as the
  system message ahead of the same task, so the literal shipped file is under
  test, not a paraphrase; this port's :data:`Arm.GUIDANCE` does the same by
  **importing** ``ALWAYS_ON_OUTPUT_POLICY`` from
  ``dummyindex.context.output.bootstrap`` (not copying its text) as the
  system prompt ahead of the same task — one source of truth, exactly as
  Task 1 (the rule-copy canary) does.
- **Probe shape mirrors ``benchmarks/behavior.yaml``'s ``tests:`` block**
  (`:31-40`): each probe is a ``(id, task)`` pair, run across both arms and
  ``--repeat``-many times. Kept to 3 probes here (every probe costs real
  tokens on the user's account) — see :data:`PROBES` for which check(s) each
  one targets and why.
- **Grading dispatch mirrors ``behavior.js``'s per-probe ``CHECKS`` lookup**
  (`:39-54``), not ``grade_response``'s "score everything" default: this
  module scores a response with :func:`~tests.eval.behavior_gate.grade_response`
  (all four checks, unchanged) but then reads only the check(s) named in a
  probe's :attr:`Probe.targets` when deciding whether that probe passed — the
  same one-probe-one-relevant-check idea as ``behavior.js``'s ``CHECKS[probe]``
  dispatch, adapted to a grader that (per ``behavior_gate.py``'s module
  docstring) always runs all four checks rather than picking one.

**How ponytail computes (or rather, does not compute) the delta** — recorded
in spec.md's "How the delta is computed": no ponytail script *asserts* a
delta anywhere; ``behavior.yaml``'s header comment states the intent (the
baseline arm "should mostly FAIL these gates, the ponytail arm should pass
them") but leaves the arithmetic to ``promptfoo view``'s own side-by-side
per-prompt-label aggregation — a human or CI step eyeballs the two rows.
**This port chooses to assert the delta explicitly instead**, for the reason
spec.md gives when raising the question: dummyindex's own
``tests/eval/BASELINE.md`` idiom is to record an observed number and set a
gate a documented margin below it, and a two-arm behavior run with a real
pass/fail acceptance criterion (plan.md task 3: "the control arm fails the
gates, the guidance arm passes") is exactly the kind of claim that idiom
exists to make checkable rather than eyeballed. Unlike ``BASELINE.md``'s
retrieval floors, there was no pre-existing baseline to observe here — this
is the first run — so :data:`_CONTROL_GATE_CEILING` /
:data:`_GUIDANCE_GATE_FLOOR` are conservative separation thresholds fixed
**before** the paid run in this module's history, not tuned to the observed
result afterward (see ``tests/eval/BASELINE.md``'s sibling record of the
actual measured numbers for this run).

**Transport.** Shells out to the real ``claude`` CLI (already installed and
authed — no API key, no SDK, mirroring headroom's own ``_CLI_BACKENDS``
subprocess fallback in spirit, though that path is explicitly rejected
elsewhere in this proposal as non-deterministic; here the model call *is*
the point). ``--safe-mode`` disables this repo's own ``CLAUDE.md``, skills,
plugins, and hooks for the session — without it, this repo's managed
``CLAUDE.md`` block (which itself carries ``ALWAYS_ON_OUTPUT_POLICY``) would
leak into the control arm and erase the very delta under test.
``--append-system-prompt`` **adds** the policy on top of the host default for
the guidance arm while the control arm appends nothing, so the two arms share
an identical base and differ by exactly the policy text. (An earlier revision
used ``--system-prompt``, which *replaces* the default outright; that made the
guidance arm an ablation — the policy INSTEAD OF the assistant's normal
scaffolding — and it scored 0.33 against the control's 0.56 in the first real
sweep. Both sweeps are recorded in ``tests/eval/BASELINE.md``'s sibling
record; the first is kept there because a discarded measurement that is not
written down is a measurement no one can check.) ``--tools ""`` disables tool
use so both arms produce a plain text completion, not a tool-call transcript.
A non-zero exit or empty stdout is a hard error (:class:`BehaviorArmError`),
never a silently-passing arm.

This module is imported only when the opt-in test
(``tests/eval/test_behavior_arms.py``) actually runs — see that module for
the ``DUMMYINDEX_BEHAVIOR_ARMS=1`` gate and the ``behavior_arms`` pytest
marker that keep this off the default ``pytest -q`` path.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from dummyindex.context.output.bootstrap import ALWAYS_ON_OUTPUT_POLICY
from tests.eval.behavior_gate import (
    BehaviorCheck,
    BehaviorVerdict,
    grade_response,
    pass_rate,
)


class BehaviorArmError(Exception):
    """Raised when the ``claude`` CLI transport fails.

    A non-zero exit code or empty stdout is a hard error here, never treated
    as a silently-passing arm — the task brief's explicit requirement.
    """


class Arm(str, Enum):
    """The two arms, matching ponytail's ``arms/baseline.js`` /
    ``arms/ponytail.js`` structure."""

    CONTROL = "control"
    GUIDANCE = "guidance"

    # Render as the value, matching BehaviorCheck's __str__ pin
    # (behavior_gate.py:100) and dummyindex.context.enums.DocConfidence.
    __str__ = str.__str__


# The control arm appends NOTHING — the host default system prompt, unchanged.
# That is the faithful analogue of ``arms/baseline.js:2`` ("no system message"):
# ponytail's baseline does not swap the provider's defaults for a stand-in, it
# simply adds nothing. An earlier revision sent a bland "You are a helpful
# assistant." via ``--system-prompt``, which *replaced* the default in both
# arms and confounded the first real sweep (see ``_run_cli``).
_CONTROL_APPENDED_GUIDANCE = ""

_CLI_EXECUTABLE = "claude"
# A single long-form probe measured ~95s standalone; sequential calls under
# load run slower still, and a 180s ceiling aborted a real run mid-sweep.
# Generous on purpose: a timeout here is a harness failure, not a signal about
# the arm under test, and aborting a paid sweep wastes every call before it.
_DEFAULT_TIMEOUT_S = 600.0


@dataclass(frozen=True)
class Probe:
    """One task prompt plus the :class:`BehaviorCheck`\\(s) it targets.

    Mirrors ``behavior.yaml``'s ``tests:`` block (a ``vars.probe`` id plus a
    ``vars.task`` prompt, `:31-40`) — but see the module docstring: because
    :func:`~tests.eval.behavior_gate.grade_response` always scores all four
    checks (unlike ``behavior.js``'s single-check-per-probe dispatch), a
    probe here names which of the four results are the ones its task is
    actually designed to move.
    """

    id: str
    task: str
    targets: tuple[BehaviorCheck, ...]


# Three probes — every probe costs real tokens on the user's account, so this
# stays small (task brief: "3-4 probes is right"). Each is a realistic
# open-ended engineering ask, not a synthetic prompt engineered to trip one
# regex — the same spirit as ponytail's hardware/explanation/onecheck probes
# (``behavior.yaml:31-40``), just retargeted at dummyindex's four checks
# instead of ponytail's three domain-specific ones.
PROBES: tuple[Probe, ...] = (
    # Open-ended incident triage invites hedging ("it could be several
    # things...") without guidance, and rewards a decisive first line plus a
    # stated next step with it.
    Probe(
        id="incident_response",
        task=(
            "Our checkout service is returning intermittent 500 errors under "
            "load. Investigate and tell me what's likely wrong and how to "
            "fix it."
        ),
        targets=(BehaviorCheck.ACTION_FIRST, BehaviorCheck.CLOSING_ACTION),
    ),
    # A genuinely multi-step how-to invites unnumbered running prose without
    # guidance; the numbered-steps check is squarely this probe's target.
    Probe(
        id="dependency_migration",
        task=(
            "Walk me through migrating a Python project from a "
            "requirements.txt setup to a pyproject.toml-based src layout, "
            "covering the full process end to end."
        ),
        targets=(BehaviorCheck.NUMBERED_STEPS,),
    ),
    # Asking for an "improvement" invites a vague answer ("noticeably
    # faster") without guidance; a concrete estimate is the specific-
    # quantities check's target.
    Probe(
        id="loop_optimization",
        task=(
            "I profiled a data-processing script and found a nested loop "
            "doing O(n^2) dictionary lookups over a list of 50,000 records. "
            "How would you fix it, and what improvement should I expect?"
        ),
        targets=(BehaviorCheck.SPECIFIC_QUANTITIES,),
    ),
)


def _run_cli(appended_guidance: str, task: str, *, timeout: float) -> str:
    """Shell out to the real ``claude`` CLI and return its stdout.

    ``--safe-mode`` disables this repo's own ``CLAUDE.md``/skills/plugins/
    hooks so neither arm is contaminated by this repo's own managed guidance.
    ``--tools ""`` disables tool use so the result is a plain text completion
    in both arms. ``--no-session-persistence`` avoids leaving resumable
    session state behind for a throwaway eval call.

    **Why ``--append-system-prompt`` and not ``--system-prompt``.** The first
    real sweep used ``--system-prompt``, which *replaces* the default system
    prompt outright. That made the guidance arm "the output policy INSTEAD OF
    the assistant's normal scaffolding" rather than "baseline PLUS the
    policy" — the guidance arm scored 0.33 against the control's 0.56, an
    artifact of the ablation, not a measurement of the policy. ponytail's own
    arms are additive (``arms/baseline.js`` sends the task with no system
    prompt; ``arms/ponytail.js`` adds ``SKILL.md`` on top of the same
    provider defaults), so the faithful port keeps the host default fixed in
    both arms and only appends. The control arm therefore appends nothing at
    all — it is the unmodified host default, which is the true no-guidance
    control.
    """
    argv = [
        _CLI_EXECUTABLE,
        "-p",
        task,
        "--safe-mode",
        "--tools",
        "",
        "--output-format",
        "text",
        "--no-session-persistence",
    ]
    if appended_guidance:
        argv[4:4] = ["--append-system-prompt", appended_guidance]
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise BehaviorArmError(
            f"`{_CLI_EXECUTABLE}` not found on PATH — cannot run the "
            "behavior-arms harness without the approved CLI transport"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BehaviorArmError(
            f"`{_CLI_EXECUTABLE}` timed out after {timeout}s for task {task[:60]!r}"
        ) from exc
    if result.returncode != 0:
        raise BehaviorArmError(
            f"`{_CLI_EXECUTABLE}` exited {result.returncode} for task "
            f"{task[:60]!r}: stderr={result.stderr[:500]!r}"
        )
    output = result.stdout.strip()
    if not output:
        raise BehaviorArmError(
            f"`{_CLI_EXECUTABLE}` produced empty stdout for task "
            f"{task[:60]!r} — treating as a hard error, not a passing arm"
        )
    return output


def run_arm(arm: Arm, probe: Probe, *, timeout: float = _DEFAULT_TIMEOUT_S) -> str:
    """Run one (arm, probe) cell once and return the raw response text."""
    appended_guidance = (
        ALWAYS_ON_OUTPUT_POLICY if arm is Arm.GUIDANCE else _CONTROL_APPENDED_GUIDANCE
    )
    return _run_cli(appended_guidance, probe.task, timeout=timeout)


@dataclass(frozen=True)
class ArmRunResult:
    """One graded (arm, probe, repeat) cell."""

    arm: Arm
    probe_id: str
    repeat_index: int
    response: str
    verdict: BehaviorVerdict

    def targeted_pass(self, targets: tuple[BehaviorCheck, ...]) -> bool:
        """True iff every check named in ``targets`` passed for this cell."""
        return all(self.verdict.passed(check) for check in targets)


def run_two_arm(
    probes: Sequence[Probe] = PROBES,
    *,
    repeats: int = 3,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> list[ArmRunResult]:
    """Run every probe across both arms, ``repeats`` times each, and grade
    every response with the task 2 grader, unchanged.

    Raises :class:`BehaviorArmError` immediately on any CLI failure — a
    broken transport must never silently read as a passing or failing arm.
    """
    results: list[ArmRunResult] = []
    for probe in probes:
        for arm in (Arm.CONTROL, Arm.GUIDANCE):
            for repeat_index in range(repeats):
                response = run_arm(arm, probe, timeout=timeout)
                verdict = grade_response(response)
                results.append(
                    ArmRunResult(
                        arm=arm,
                        probe_id=probe.id,
                        repeat_index=repeat_index,
                        response=response,
                        verdict=verdict,
                    )
                )
    return results


def targeted_pass_rate(
    results: Sequence[ArmRunResult], arm: Arm, probe: Probe
) -> float:
    """Fraction of ``arm``'s runs of ``probe`` that passed ALL of
    ``probe.targets`` — the per-probe analogue of
    :func:`~tests.eval.behavior_gate.pass_rate`, dispatched the way
    ``behavior.js`` dispatches ``CHECKS[probe]`` (see module docstring)."""
    cells = [r for r in results if r.arm is arm and r.probe_id == probe.id]
    if not cells:
        return 0.0
    return sum(1 for r in cells if r.targeted_pass(probe.targets)) / len(cells)


def overall_targeted_pass_rate(
    results: Sequence[ArmRunResult], arm: Arm, probes: Sequence[Probe] = PROBES
) -> float:
    """Fraction of ``arm``'s runs, across all ``probes``, whose own targeted
    check(s) passed — the single number the two-arm acceptance gate reads."""
    by_probe = {p.id: p for p in probes}
    cells = [r for r in results if r.arm is arm and r.probe_id in by_probe]
    if not cells:
        return 0.0
    return sum(1 for r in cells if r.targeted_pass(by_probe[r.probe_id].targets)) / len(
        cells
    )


def all_four_pass_rate(results: Sequence[ArmRunResult], arm: Arm) -> float:
    """Fraction of ``arm``'s runs that passed all four
    :class:`BehaviorCheck`\\(s), not just the probe's targeted subset —
    recorded alongside the targeted rate, never gated on its own (a probe
    designed to exercise one check is not expected to also produce, e.g., a
    numbered list for a one-line diagnosis)."""
    cells = [r for r in results if r.arm is arm]
    if not cells:
        return 0.0
    return sum(1 for r in cells if r.verdict.all_passed) / len(cells)


# Fixed BEFORE the paid run this module's history records (see the module
# docstring's "How ponytail computes the delta" section) — not tuned to the
# observed result afterward. The gate is deliberately asymmetric and loose:
# a probe's task was written to make the unguided failure mode plausible,
# not guaranteed, so the control ceiling is not 0.0.
_CONTROL_GATE_CEILING = 0.5
_GUIDANCE_GATE_FLOOR = 0.6


@dataclass(frozen=True)
class TwoArmReport:
    """The measured delta for one two-arm run.

    ``per_check`` reuses :func:`~tests.eval.behavior_gate.pass_rate`
    unchanged, one rate per :class:`BehaviorCheck`, per arm — the primitive
    the task brief asks be used rather than reimplemented. ``per_probe`` and
    the two ``*_overall``/``*_all_four`` fields are this module's own
    aggregation on top of it (see the module docstring's "How ponytail
    computes the delta").
    """

    control_overall: float
    guidance_overall: float
    control_all_four: float
    guidance_all_four: float
    per_probe: dict[str, tuple[float, float]]
    per_check: dict[BehaviorCheck, tuple[float, float]]

    @property
    def control_gate_passed(self) -> bool:
        """True iff the control arm FAILED the gates, as the acceptance
        criterion requires (a *low* targeted-pass rate is the desired
        outcome for the control arm)."""
        return self.control_overall <= _CONTROL_GATE_CEILING

    @property
    def guidance_gate_passed(self) -> bool:
        """True iff the guidance arm PASSED the gates."""
        return self.guidance_overall >= _GUIDANCE_GATE_FLOOR

    @property
    def acceptance_held(self) -> bool:
        """The plan.md task 3 acceptance: control fails, guidance passes."""
        return self.control_gate_passed and self.guidance_gate_passed


def build_report(
    results: Sequence[ArmRunResult], probes: Sequence[Probe] = PROBES
) -> TwoArmReport:
    """Aggregate a completed two-arm run into a :class:`TwoArmReport`."""
    control_verdicts = [r.verdict for r in results if r.arm is Arm.CONTROL]
    guidance_verdicts = [r.verdict for r in results if r.arm is Arm.GUIDANCE]
    return TwoArmReport(
        control_overall=overall_targeted_pass_rate(results, Arm.CONTROL, probes),
        guidance_overall=overall_targeted_pass_rate(results, Arm.GUIDANCE, probes),
        control_all_four=all_four_pass_rate(results, Arm.CONTROL),
        guidance_all_four=all_four_pass_rate(results, Arm.GUIDANCE),
        per_probe={
            probe.id: (
                targeted_pass_rate(results, Arm.CONTROL, probe),
                targeted_pass_rate(results, Arm.GUIDANCE, probe),
            )
            for probe in probes
        },
        per_check={
            check: (
                pass_rate(control_verdicts, check),
                pass_rate(guidance_verdicts, check),
            )
            for check in BehaviorCheck
        },
    )


def format_report(report: TwoArmReport) -> str:
    """Render a :class:`TwoArmReport` as a plain-text table for ``pytest -s``
    / CI log output — the human-readable form of the delta."""
    lines = [
        "behavior-gate two-arm delta (control vs guidance):",
        f"{'check':<24}{'control':>10}{'guidance':>10}{'delta':>10}",
    ]
    for check, (control_rate, guidance_rate) in report.per_check.items():
        lines.append(
            f"{str(check):<24}{control_rate:>10.2f}{guidance_rate:>10.2f}"
            f"{guidance_rate - control_rate:>10.2f}"
        )
    lines.append("")
    lines.append(f"{'per-probe (targeted)':<24}{'control':>10}{'guidance':>10}")
    for probe_id, (control_rate, guidance_rate) in report.per_probe.items():
        lines.append(f"{probe_id:<24}{control_rate:>10.2f}{guidance_rate:>10.2f}")
    lines.append("")
    lines.append(
        f"{'overall (targeted)':<24}{report.control_overall:>10.2f}"
        f"{report.guidance_overall:>10.2f}"
        f"{report.guidance_overall - report.control_overall:>10.2f}"
    )
    lines.append(
        f"{'overall (all-four)':<24}{report.control_all_four:>10.2f}"
        f"{report.guidance_all_four:>10.2f}"
        f"{report.guidance_all_four - report.control_all_four:>10.2f}"
    )
    return "\n".join(lines)
