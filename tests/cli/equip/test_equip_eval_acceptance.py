"""ACCEPTANCE gate for the ``equip-eval-benchmark`` proposal (one bullet).

Proves the whole eval feature's user-facing contract in three drives of the
**real** CLI through :func:`dispatch.run` against a ``tmp_path`` repo:

> ``equip eval`` writes a pinned-shape result and lists FP/FN cases;
> ``equip benchmark`` reports variance + flaky cases; absent runs fail-open
> (exit 0).

Each test is named + docstringed to the sub-clause it proves. This is a focused
acceptance gate, deliberately narrower than the broader wire-boundary coverage in
``test_equip_eval_cli.py`` (exit codes, path resolution, schema-shape sweep) —
here we assert only the three promises in the bullet, end to end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import dispatch

_TOOL = "pg-tuner"


# ----- fixture helpers (small, on purpose) ----------------------------------


def _evals_dir(root: Path) -> Path:
    """The dir the CLI resolves for ``--root root`` (``.context/equipment-evals``)."""
    return root / ".context" / "equipment-evals"


def _write_suite(root: Path, cases: list[dict]) -> None:
    """Write ``<tool>.suite.json`` under the evals dir the CLI reads from."""
    evals = _evals_dir(root)
    evals.mkdir(parents=True, exist_ok=True)
    (evals / f"{_TOOL}.suite.json").write_text(
        json.dumps({"cases": cases}), encoding="utf-8"
    )


def _write_observations(root: Path, obs: list[dict], *, name: str) -> Path:
    """Write a named observations file under ``root`` and return its path."""
    path = root / name
    path.write_text(json.dumps({"observations": obs}), encoding="utf-8")
    return path


# A mixed suite: one case per confusion-matrix cell. Paired with the observations
# below it yields exactly one TP, one FN, one FP, and one TN.
_MIXED_CASES: list[dict] = [
    {"case_id": "tp1", "prompt": "tune this postgres query", "expects_trigger": True},
    {"case_id": "fn1", "prompt": "add an index to users", "expects_trigger": True},
    {"case_id": "fp1", "prompt": "write a haiku", "expects_trigger": False},
    {"case_id": "tn1", "prompt": "translate hello", "expects_trigger": False},
]
# fired vs expects_trigger -> outcome:
#   tp1: expects True,  fired True  -> true-positive
#   fn1: expects True,  fired False -> false-negative  (misfire)
#   fp1: expects False, fired True  -> false-positive  (misfire)
#   tn1: expects False, fired False -> true-negative
_MIXED_OBS: list[dict] = [
    {"case_id": "tp1", "fired": True},
    {"case_id": "fn1", "fired": False},
    {"case_id": "fp1", "fired": True},
    {"case_id": "tn1", "fired": False},
]


# ----- clause 1: eval writes a pinned-shape result AND lists FP/FN -----------


@pytest.mark.unit
def test_eval_writes_pinned_shape_result_and_lists_fp_fn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``equip eval`` writes a pinned-shape result and lists FP/FN cases.

    Drives a mixed suite (1 TP, 1 FN, 1 FP, 1 TN) through the real CLI: asserts
    exit 0, the exact top-level / counts key sets on the written
    ``<tool>.result.json``, that ``misfires`` holds exactly the FP + FN case_ids
    (never the TP/TN ones), and that stdout names both misfire ids + outcomes.
    """
    _write_suite(tmp_path, _MIXED_CASES)
    obs = _write_observations(tmp_path, _MIXED_OBS, name="obs.json")

    rc = dispatch.run(
        ["eval", _TOOL, "--observations", str(obs), "--root", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert rc == 0

    result_path = _evals_dir(tmp_path) / f"{_TOOL}.result.json"
    assert result_path.is_file(), "eval must write <tool>.result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))

    # Pinned shape: exact top-level key set and exact counts key set.
    assert set(result.keys()) == {
        "tool_name",
        "cases",
        "counts",
        "precision",
        "recall",
        "accuracy",
        "misfires",
    }
    assert set(result["counts"].keys()) == {
        "true-positive",
        "false-positive",
        "true-negative",
        "false-negative",
    }

    # misfires == exactly the FP + FN case_ids (not the correctly-classified ones).
    misfire_ids = {m["case_id"] for m in result["misfires"]}
    assert misfire_ids == {"fp1", "fn1"}
    assert "tp1" not in misfire_ids and "tn1" not in misfire_ids

    # stdout names both misfire case_ids and their outcomes.
    assert "fp1" in out and "fn1" in out
    assert "false-positive" in out and "false-negative" in out


# ----- clause 2: benchmark reports variance + flaky cases --------------------


@pytest.mark.unit
def test_benchmark_reports_variance_and_flaky_cases(tmp_path: Path) -> None:
    """``equip benchmark`` reports variance + flaky cases.

    Writes two labelled runs (via ``eval --run-label``) engineered so ``fp1``
    flips outcome between them — so the two runs differ in accuracy and ``fp1``'s
    outcome is not identical across runs. Asserts benchmark exits 0, writes the
    report, ``accuracy_variance`` is a number > 0, and ``fp1`` is flaky.
    """
    _write_suite(tmp_path, _MIXED_CASES)
    # Run A: fp1 fires (false-positive).
    obs_a = _write_observations(tmp_path, _MIXED_OBS, name="obs_a.json")
    assert (
        dispatch.run(
            [
                "eval",
                _TOOL,
                "--observations",
                str(obs_a),
                "--run-label",
                "a",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    # Run B: fp1 now stays silent (true-negative) -> outcome flips, accuracy rises.
    obs_b = _write_observations(
        tmp_path,
        [
            {"case_id": "tp1", "fired": True},
            {"case_id": "fn1", "fired": False},
            {"case_id": "fp1", "fired": False},
            {"case_id": "tn1", "fired": False},
        ],
        name="obs_b.json",
    )
    assert (
        dispatch.run(
            [
                "eval",
                _TOOL,
                "--observations",
                str(obs_b),
                "--run-label",
                "b",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )

    rc = dispatch.run(["benchmark", _TOOL, "--root", str(tmp_path)])
    assert rc == 0

    bench_path = _evals_dir(tmp_path) / f"{_TOOL}.benchmark.json"
    assert bench_path.is_file(), "benchmark must write <tool>.benchmark.json"
    report = json.loads(bench_path.read_text(encoding="utf-8"))

    # Variance is a real, positive number (the two runs differ in accuracy).
    assert isinstance(report["accuracy_variance"], (int, float))
    assert report["accuracy_variance"] > 0.0

    # The flipped case is reported flaky.
    assert "fp1" in report["flaky_case_ids"]


# ----- clause 3: absent runs fail-open (exit 0, writes nothing) --------------


@pytest.mark.unit
def test_benchmark_absent_runs_fail_open(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Absent runs fail-open: exit 0, no benchmark file, a stderr warning.

    ``equip benchmark`` with no run files present is a reporter, not a gate: it
    returns 0, writes NO ``<tool>.benchmark.json``, and emits a stderr warning.
    """
    rc = dispatch.run(["benchmark", _TOOL, "--root", str(tmp_path)])
    err = capsys.readouterr().err

    assert rc == 0
    assert not (_evals_dir(tmp_path) / f"{_TOOL}.benchmark.json").exists()
    assert "warning" in err.lower()
