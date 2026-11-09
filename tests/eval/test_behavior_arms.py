"""Opt-in two-arm behavior-gate run: the suite's only model-dependent test.

It shells out to the real ``claude`` CLI and costs real tokens, so unless
``DUMMYINDEX_BEHAVIOR_ARMS`` is exactly ``"1"`` the module skips at collection,
before ``tests.eval.behavior_arms`` is imported. Run it with
``DUMMYINDEX_BEHAVIOR_ARMS=1 uv run pytest tests/eval/test_behavior_arms.py -q -s``.
A miss fails loudly with the real numbers; never retune the thresholds to pass.
"""

from __future__ import annotations

import os

import pytest

_ENV_VAR = "DUMMYINDEX_BEHAVIOR_ARMS"

pytestmark = pytest.mark.behavior_arms

if os.environ.get(_ENV_VAR) != "1":
    pytest.skip(
        f"opt-in only: set {_ENV_VAR}=1 to run this test. It shells out to "
        "the real `claude` CLI and costs real tokens on the user's account "
        "— see tests/eval/behavior_arms.py's module docstring.",
        allow_module_level=True,
    )

from tests.eval.behavior_arms import (  # noqa: E402
    PROBES,
    build_report,
    format_report,
    run_two_arm,
)

_REPEATS = 3


@pytest.mark.integration
def test_two_arm_behavior_gate() -> None:
    """Run every probe across both arms ``_REPEATS`` times; assert guidance beats
    control, the control arm fails the gates and the guidance arm passes them."""
    results = run_two_arm(PROBES, repeats=_REPEATS)
    report = build_report(results, PROBES)

    print("\n" + format_report(report))

    assert report.guidance_overall > report.control_overall, (
        "guidance arm did not even out-perform the control arm on their "
        f"probes' targeted checks: control={report.control_overall:.2f} "
        f"guidance={report.guidance_overall:.2f} — this contradicts the "
        "acceptance criterion; report the real numbers, do not retune"
    )
    assert report.control_gate_passed, (
        f"control (no-guidance) arm did not fail the gates as expected: "
        f"targeted pass rate {report.control_overall:.2f} exceeds the "
        f"ceiling of {0.5:.2f}"
    )
    assert report.guidance_gate_passed, (
        f"guidance arm did not pass the gates: targeted pass rate "
        f"{report.guidance_overall:.2f} is below the floor of {0.6:.2f}"
    )
