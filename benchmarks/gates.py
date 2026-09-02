"""Pre-registered acceptance gates — fixed before the first paid sweep.

The repo's baseline idiom (``tests/eval/BASELINE.md``,
``behavior_arms._CONTROL_GATE_CEILING``) is: write the threshold and its
rationale down BEFORE looking at measured results, then let the report read
against it. These constants follow that discipline. They may be revised at
most once, now, before any paid run happens — never afterwards, and never to
paper over a regression.

Gates (per suite):

- **Accuracy non-inferiority.** The context arm must not lose meaningful
  accuracy versus the baseline arm. Margin 0.02 absolute on RepoQA SNF
  (500-task granularity makes 0.02 = 10 tasks; a smaller true drop than that
  is within repetition noise). Margin 0.05 absolute on SWE-bench resolve
  rate (50 instances make single-digit-instance noise unavoidable; 0.05 = 2.5
  instances).
- **Efficiency expectation (recorded, only softly gated).** dummyindex's
  stated claim is >=50% tool-call reduction (`docs/guide/01-purpose.md`).
  Pre-registering a hard gate on a first-ever measurement would be theater;
  instead the report records the observed reduction ratio and this module
  gates it against a deliberately conservative floor of 1.15x fewer mean
  tool calls, so a *massive* regression (context arm doing far MORE work)
  still fails loudly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

SNF_NONINFERIORITY_MARGIN = 0.02
SWE_NONINFERIORITY_MARGIN = 0.05
TOOL_CALL_RATIO_FLOOR = 1.15


@dataclass(frozen=True)
class SuiteSummary:
    suite: str
    arm_value: str
    n: int
    pass_rate: float
    mean_tool_calls: float


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GateReport:
    results: tuple[GateResult, ...]

    @property
    def all_passed(self) -> bool:
        return all(g.passed for g in self.results)

    def render(self) -> str:
        lines = ["pre-registered gates:"]
        for gate in self.results:
            marker = "PASS" if gate.passed else "FAIL"
            lines.append(f"  [{marker}] {gate.name}: {gate.detail}")
        return "\n".join(lines)


def _summary_for(
    summaries: Sequence[SuiteSummary], arm_value: str
) -> SuiteSummary | None:
    for summary in summaries:
        if summary.arm_value == arm_value:
            return summary
    return None


def evaluate_gates(summaries: Sequence[SuiteSummary]) -> GateReport:
    """Evaluate every pre-registered gate from per-(suite, arm) summaries."""
    results: list[GateResult] = []
    for suite in sorted({s.suite for s in summaries}):
        rows = [s for s in summaries if s.suite == suite]
        base = _summary_for(rows, "baseline")
        ctx = _summary_for(rows, "context")
        if base is None or ctx is None or base.n == 0 or ctx.n == 0:
            results.append(
                GateResult(
                    name=f"{suite}:gate",
                    passed=False,
                    detail="missing arm summaries — cannot evaluate",
                )
            )
            continue
        margin = (
            SNF_NONINFERIORITY_MARGIN
            if suite == "repoqa"
            else SWE_NONINFERIORITY_MARGIN
        )
        delta = ctx.pass_rate - base.pass_rate
        # 1e-9 absorbs binary-float noise when delta lands exactly on -margin.
        results.append(
            GateResult(
                name=f"{suite}:accuracy-noninferiority",
                passed=delta >= -margin - 1e-9,
                detail=(
                    f"context {ctx.pass_rate:.3f} vs baseline "
                    f"{base.pass_rate:.3f} (delta {delta:+.3f}, "
                    f"margin -{margin:.2f})"
                ),
            )
        )
        ratio = (
            base.mean_tool_calls / ctx.mean_tool_calls
            if ctx.mean_tool_calls > 0
            else float("inf")
        )
        results.append(
            GateResult(
                name=f"{suite}:tool-call-ratio-floor",
                passed=ratio >= TOOL_CALL_RATIO_FLOOR,
                detail=(
                    f"baseline/context mean tool calls = "
                    f"{base.mean_tool_calls:.2f}/"
                    f"{ctx.mean_tool_calls:.2f} "
                    f"(ratio {ratio:.2f}, floor {TOOL_CALL_RATIO_FLOOR:.2f})"
                ),
            )
        )
    return GateReport(results=tuple(results))
