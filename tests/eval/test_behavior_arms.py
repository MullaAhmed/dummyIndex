"""Opt-in two-arm behavior-gate run — plan.md task 3
(`.context/proposals/repo-adoptions-ponytail-headroom/plan.md`).

This is the **only** model-dependent test in the suite (spec.md's stated
risk). It shells out to the real ``claude`` CLI, costs real tokens, and takes
several minutes — it must never run as part of a plain ``pytest -q``.

**The opt-in gate, and why it is provably inert by default.** This module is
skipped at COLLECTION time (``pytest.skip(..., allow_module_level=True)``)
before the line that imports ``tests.eval.behavior_arms`` even executes,
whenever ``DUMMYINDEX_BEHAVIOR_ARMS`` is not exactly ``"1"``. A skipped
module's test functions are never called, so
:func:`tests.eval.behavior_arms.run_two_arm` — the only function in this
harness that shells out — is never invoked. This is not merely "the test
reports skipped"; it is checkable independently of pytest's own bookkeeping:
running the default suite with ``claude`` removed from ``PATH`` still passes
(see the verification transcript this task recorded), which would be
impossible if this module's CLI calls executed unconditionally. The
``behavior_arms`` pytest marker (registered in ``pyproject.toml``) documents
the same opt-in on the collection side, for ``pytest -m`` filtering.

Run it explicitly with::

    DUMMYINDEX_BEHAVIOR_ARMS=1 uv run pytest tests/eval/test_behavior_arms.py -q -s

The acceptance (plan.md task 3): the control arm fails the gates, the
guidance arm passes, and the measured delta is recorded next to
``tests/eval/BASELINE.md``. If a real run does not clear that bar, this test
is written to report the actual numbers and fail loudly — never to have its
thresholds adjusted after the fact to force a green result (task brief:
"DO NOT tune the grader or cherry-pick probes to force it").
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
    """Run every probe across both arms ``_REPEATS`` times, grade every
    response with the unchanged task 2 grader, and assert the plan.md task 3
    acceptance: the control arm fails the gates, the guidance arm passes."""
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
