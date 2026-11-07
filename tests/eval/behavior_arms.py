"""Two-arm, model-dependent behavior-gate run over ``ALWAYS_ON_OUTPUT_POLICY``.

Wires the ``tests/eval/behavior_gate.py`` grader (imported unchanged) to two
real arms, following ``DietrichGebert/ponytail`` (MIT, © 2026 DietrichGebert)
``benchmarks/arms/``: each arm shells out to the real ``claude`` CLI and costs
real tokens, and the arms differ by exactly the policy text. Opt-in: imported
only by ``tests/eval/test_behavior_arms.py`` when ``DUMMYINDEX_BEHAVIOR_ARMS=1``.
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
    """The ``claude`` CLI failed: missing, timed out, non-zero exit or empty stdout.

    A hard error, so a broken transport never reads as a passing arm.
    """


class Arm(str, Enum):
    """The two arms, mirroring ponytail's ``arms/baseline.js`` and ``arms/ponytail.js``."""

    CONTROL = "control"
    GUIDANCE = "guidance"

    # Render as the value, like BehaviorCheck and dummyindex.context.enums.DocConfidence.
    __str__ = str.__str__


# The control arm appends nothing: the unmodified host default is the true
# no-guidance control, as ponytail's ``arms/baseline.js`` sends no system message.
_CONTROL_APPENDED_GUIDANCE = ""

_CLI_EXECUTABLE = "claude"
# One long probe took ~95s standalone and a 180s ceiling aborted a real sweep.
# A timeout is a harness failure, not an arm signal, and wastes the paid calls before it.
_DEFAULT_TIMEOUT_S = 600.0


@dataclass(frozen=True)
class Probe:
    """One task prompt plus the :class:`BehaviorCheck`\\(s) it targets.

    :func:`~tests.eval.behavior_gate.grade_response` scores all four checks; only
    ``targets``, the ones this task is designed to move, decide whether the probe
    passed (ponytail's ``behavior.js`` ``CHECKS[probe]`` dispatch).
    """

    id: str
    task: str
    targets: tuple[BehaviorCheck, ...]


# Three probes, since each costs real tokens. Each is a realistic open-ended ask,
# not a prompt engineered to trip one regex (cf. ponytail's ``behavior.yaml`` probes).
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

    ``--safe-mode`` drops this repo's CLAUDE.md/skills/plugins/hooks: its managed
    CLAUDE.md block carries the policy and would leak into the control arm.
    ``--append-system-prompt`` adds to the host default; ``--system-prompt``
    replaced it, making the guidance arm an ablation (0.33 vs the control's 0.56).
    ``--tools ""`` forces a plain-text completion.
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
    """Run every probe across both arms ``repeats`` times and grade each response.

    Raises :class:`BehaviorArmError` on the first CLI failure.
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
    """Fraction of ``arm``'s runs of ``probe`` that passed all of ``probe.targets``."""
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
    """Fraction of ``arm``'s runs that passed all four checks, not just the targets.

    Recorded, never gated: a probe aimed at one check need not satisfy the others.
    """
    cells = [r for r in results if r.arm is arm]
    if not cells:
        return 0.0
    return sum(1 for r in cells if r.verdict.all_passed) / len(cells)


# ponytail leaves the delta to ``promptfoo view``; this port asserts it. Fixed before
# the first paid run, not tuned to its result. Loose and asymmetric: a probe makes
# the unguided failure plausible, not guaranteed, so the control ceiling is not 0.0.
_CONTROL_GATE_CEILING = 0.5
_GUIDANCE_GATE_FLOOR = 0.6


@dataclass(frozen=True)
class TwoArmReport:
    """The measured delta for one two-arm run.

    ``per_check`` holds :func:`~tests.eval.behavior_gate.pass_rate` per check, as
    (control, guidance); ``per_probe`` and the ``*_overall``/``*_all_four`` rates
    are this module's targeted aggregation.
    """

    control_overall: float
    guidance_overall: float
    control_all_four: float
    guidance_all_four: float
    per_probe: dict[str, tuple[float, float]]
    per_check: dict[BehaviorCheck, tuple[float, float]]

    @property
    def control_gate_passed(self) -> bool:
        """True iff the control arm FAILED the gates (a low targeted rate is the goal)."""
        return self.control_overall <= _CONTROL_GATE_CEILING

    @property
    def guidance_gate_passed(self) -> bool:
        """True iff the guidance arm PASSED the gates."""
        return self.guidance_overall >= _GUIDANCE_GATE_FLOOR

    @property
    def acceptance_held(self) -> bool:
        """The acceptance: control fails the gates, guidance passes them."""
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
    """Render a :class:`TwoArmReport` as a plain-text table for ``pytest -s``/CI logs."""
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
