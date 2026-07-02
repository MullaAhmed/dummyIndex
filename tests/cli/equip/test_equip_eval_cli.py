"""CLI end-to-end + schema contract for ``equip eval`` / ``equip benchmark``.

Drives the verbs through :func:`dispatch.run` (so the routing the eval verbs
depend on is exercised, not bypassed), against a ``tmp_path`` repo that carries a
committed ``.context/equipment-evals/<tool>.suite.json`` and a hand-written
observations file. Covers the happy path (a run with a real FP + FN), every
documented exit code, the benchmark reporter's fail-open behaviour, and a
**schema contract test** that pins the exact result/benchmark JSON key sets so
any added/renamed/removed field fails loud.

The pure scorer/aggregator are unit-tested elsewhere
(``tests/context/domains/equip/eval/``); this module owns the wire boundary:
flag parsing, path resolution under ``EVALS_REL``, atomic writes, exit codes, and
the on-disk JSON shape.
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


def _write_suite(root: Path, cases: list[dict], *, tool: str = _TOOL) -> Path:
    """Write ``<tool>.suite.json`` under the evals dir and return its path."""
    evals = _evals_dir(root)
    evals.mkdir(parents=True, exist_ok=True)
    path = evals / f"{tool}.suite.json"
    path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return path


def _write_observations(root: Path, obs: list[dict], *, name: str = "obs.json") -> Path:
    """Write an observations file anywhere under ``root`` and return its path."""
    path = root / name
    path.write_text(json.dumps({"observations": obs}), encoding="utf-8")
    return path


# A mixed suite: two positives + two negatives, so a crafted observations file
# below yields exactly one FP and one FN plus a TP and a TN.
_MIXED_CASES: list[dict] = [
    {"case_id": "tp1", "prompt": "tune this postgres query", "expects_trigger": True},
    {
        "case_id": "fn1",
        "prompt": "add an index to the users table",
        "expects_trigger": True,
    },
    {
        "case_id": "fp1",
        "prompt": "write a haiku about the sea",
        "expects_trigger": False,
    },
    {
        "case_id": "tn1",
        "prompt": "translate hello into french",
        "expects_trigger": False,
    },
]

# fired vs expects_trigger:
#   tp1: expects True,  fired True  -> true-positive
#   fn1: expects True,  fired False -> false-negative  (a misfire)
#   fp1: expects False, fired True  -> false-positive  (a misfire)
#   tn1: expects False, fired False -> true-negative
_MIXED_OBS: list[dict] = [
    {"case_id": "tp1", "fired": True},
    {"case_id": "fn1", "fired": False},
    {"case_id": "fp1", "fired": True},
    {"case_id": "tn1", "fired": False},
]

# A clean suite the tool gets 100% right (no misfires) — for the exit-0 cases.
_CLEAN_CASES: list[dict] = [
    {"case_id": "c1", "prompt": "optimize this slow query", "expects_trigger": True},
    {"case_id": "c2", "prompt": "what colour is the sky", "expects_trigger": False},
]
_CLEAN_OBS: list[dict] = [
    {"case_id": "c1", "fired": True},
    {"case_id": "c2", "fired": False},
]


# ----- equip eval: happy path -----------------------------------------------


@pytest.mark.unit
def test_eval_end_to_end_writes_result_and_lists_misfires(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A mixed run (1 FP + 1 FN) exits 0, writes the result, lists both misfires."""
    _write_suite(tmp_path, _MIXED_CASES)
    obs = _write_observations(tmp_path, _MIXED_OBS)

    rc = dispatch.run(
        ["eval", _TOOL, "--observations", str(obs), "--root", str(tmp_path)]
    )
    out = capsys.readouterr().out

    assert rc == 0
    result_path = _evals_dir(tmp_path) / f"{_TOOL}.result.json"
    assert result_path.is_file(), "eval must write <tool>.result.json"

    # Both misfire case_ids AND their EvalOutcome values appear on stdout.
    assert "fp1" in out and "fn1" in out
    assert "false-positive" in out
    assert "false-negative" in out

    # A correctly-classified TP/TN case_id must NOT appear as a misfire line.
    misfire_lines = [ln for ln in out.splitlines() if "misfire" in ln]
    assert misfire_lines, "expected per-misfire lines on stdout"
    joined = "\n".join(misfire_lines)
    assert "tp1" not in joined
    assert "tn1" not in joined


# ----- equip eval: exit codes -----------------------------------------------


@pytest.mark.unit
def test_eval_missing_suite_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No ``<tool>.suite.json`` on disk ⇒ exit 2 (EvalSuiteNotFoundError)."""
    obs = _write_observations(tmp_path, _CLEAN_OBS)
    rc = dispatch.run(
        ["eval", _TOOL, "--observations", str(obs), "--root", str(tmp_path)]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "suite" in err.lower()


@pytest.mark.unit
@pytest.mark.parametrize("evil", ["../evil", "/etc/passwd", "..", ".hidden"])
def test_eval_unsafe_tool_name_exits_2_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], evil: str
) -> None:
    """An unsafe ``<tool>`` name is rejected (exit 2) before any path is built."""
    obs = _write_observations(tmp_path, _CLEAN_OBS)
    rc = dispatch.run(
        ["eval", evil, "--observations", str(obs), "--root", str(tmp_path)]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "unsafe tool name" in err

    # No result/suite file was written ANYWHERE under tmp_path (no traversal).
    written = [p for p in tmp_path.rglob("*.json") if p.name != "obs.json"]
    assert written == [], f"unsafe name wrote files: {written}"


@pytest.mark.unit
def test_eval_malformed_observations_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invalid-JSON observations ⇒ exit 1 (malformed content)."""
    _write_suite(tmp_path, _CLEAN_CASES)
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")
    rc = dispatch.run(
        ["eval", _TOOL, "--observations", str(bad), "--root", str(tmp_path)]
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "error" in err.lower()


@pytest.mark.unit
def test_eval_clean_score_exits_0(tmp_path: Path) -> None:
    """A suite the tool classifies perfectly ⇒ exit 0."""
    _write_suite(tmp_path, _CLEAN_CASES)
    obs = _write_observations(tmp_path, _CLEAN_OBS)
    rc = dispatch.run(
        ["eval", _TOOL, "--observations", str(obs), "--root", str(tmp_path)]
    )
    assert rc == 0


@pytest.mark.unit
def test_eval_run_label_collision_needs_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A re-used ``--run-label`` is rejected without ``--force``, allowed with it."""
    _write_suite(tmp_path, _CLEAN_CASES)
    obs = _write_observations(tmp_path, _CLEAN_OBS)
    base = ["eval", _TOOL, "--observations", str(obs), "--root", str(tmp_path)]

    # First write of label "a" succeeds.
    assert dispatch.run(base + ["--run-label", "a"]) == 0
    capsys.readouterr()

    # Re-using label "a" WITHOUT --force is a non-zero collision.
    rc_collide = dispatch.run(base + ["--run-label", "a"])
    err = capsys.readouterr().err
    assert rc_collide != 0
    assert "already exists" in err or "force" in err

    # WITH --force it overwrites and exits 0.
    assert dispatch.run(base + ["--run-label", "a", "--force"]) == 0


# ----- equip benchmark ------------------------------------------------------


def _write_two_runs(tmp_path: Path, *, tool: str = _TOOL) -> None:
    """Produce two labelled run files via the eval verb (mixed outcomes -> flaky)."""
    _write_suite(tmp_path, _MIXED_CASES, tool=tool)
    # Run A: the mixed observations (fp1 + fn1 misfire).
    obs_a = _write_observations(tmp_path, _MIXED_OBS, name="obs_a.json")
    rc_a = dispatch.run(
        [
            "eval",
            tool,
            "--observations",
            str(obs_a),
            "--run-label",
            "a",
            "--root",
            str(tmp_path),
        ]
    )
    # Run B: fp1 now behaves correctly (silent) -> its outcome differs across
    # runs, so fp1 is flaky and accuracy differs between the two runs.
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
    rc_b = dispatch.run(
        [
            "eval",
            tool,
            "--observations",
            str(obs_b),
            "--run-label",
            "b",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc_a == 0 and rc_b == 0


@pytest.mark.unit
def test_benchmark_aggregates_runs_and_reports_flaky(tmp_path: Path) -> None:
    """≥2 ``run-*.result.json`` files aggregate into a report with a flaky list."""
    _write_two_runs(tmp_path)
    rc = dispatch.run(["benchmark", _TOOL, "--root", str(tmp_path)])
    assert rc == 0

    bench_path = _evals_dir(tmp_path) / f"{_TOOL}.benchmark.json"
    assert bench_path.is_file(), "benchmark must write <tool>.benchmark.json"
    report = json.loads(bench_path.read_text(encoding="utf-8"))
    assert isinstance(report["flaky_case_ids"], list)
    assert "fp1" in report["flaky_case_ids"]  # outcome differs across the two runs
    assert isinstance(report["accuracy_variance"], (int, float))
    assert report["accuracy_variance"] > 0.0  # the two runs differ in accuracy


@pytest.mark.unit
def test_benchmark_missing_evals_dir_warns_exit_0_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No evals dir at all ⇒ stderr warning + exit 0 + no benchmark file."""
    rc = dispatch.run(["benchmark", _TOOL, "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 0
    assert "warning" in err.lower() or "nothing to benchmark" in err.lower()
    assert not (_evals_dir(tmp_path) / f"{_TOOL}.benchmark.json").exists()


@pytest.mark.unit
def test_benchmark_no_run_files_warns_exit_0_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A present evals dir with a suite but zero run-* files ⇒ warn + exit 0."""
    _write_suite(tmp_path, _CLEAN_CASES)  # dir exists, but no run-* files
    rc = dispatch.run(["benchmark", _TOOL, "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 0
    assert "warning" in err.lower()
    assert not (_evals_dir(tmp_path) / f"{_TOOL}.benchmark.json").exists()


@pytest.mark.unit
def test_benchmark_labelless_only_warns_to_use_run_label(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A labelless ``<tool>.result.json`` with no run-* files ⇒ 're-run --run-label'."""
    _write_suite(tmp_path, _CLEAN_CASES)
    obs = _write_observations(tmp_path, _CLEAN_OBS)
    # A labelless eval writes <tool>.result.json but no run-* file.
    assert (
        dispatch.run(
            ["eval", _TOOL, "--observations", str(obs), "--root", str(tmp_path)]
        )
        == 0
    )
    capsys.readouterr()

    rc = dispatch.run(["benchmark", _TOOL, "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 0
    assert "run-label" in err
    assert not (_evals_dir(tmp_path) / f"{_TOOL}.benchmark.json").exists()


# ----- schema contract: pin the exact JSON shape ----------------------------

# Exact key sets — any added / renamed / removed field must fail these tests.
_RESULT_KEYS = {
    "tool_name",
    "cases",
    "counts",
    "precision",
    "recall",
    "accuracy",
    "misfires",
}
_COUNTS_KEYS = {
    "true-positive",
    "false-positive",
    "true-negative",
    "false-negative",
}
_CASE_KEYS = {"case_id", "outcome"}
_MISFIRE_KEYS = {"case_id", "prompt", "expects_trigger"}
_BENCHMARK_KEYS = {
    "tool_name",
    "runs",
    "mean_accuracy",
    "accuracy_variance",
    "flaky_case_ids",
}


def _assert_result_shape(result: dict) -> None:
    """Assert one result dict matches the pinned schema exactly (set-equality)."""
    assert set(result.keys()) == _RESULT_KEYS
    assert set(result["counts"].keys()) == _COUNTS_KEYS
    assert isinstance(result["cases"], list) and result["cases"], "cases non-empty"
    for case in result["cases"]:
        assert set(case.keys()) == _CASE_KEYS
    for misfire in result["misfires"]:
        assert set(misfire.keys()) == _MISFIRE_KEYS


@pytest.mark.unit
def test_result_schema_contract(tmp_path: Path) -> None:
    """The written ``<tool>.result.json`` matches the pinned key sets exactly."""
    _write_suite(tmp_path, _MIXED_CASES)
    obs = _write_observations(tmp_path, _MIXED_OBS)
    assert (
        dispatch.run(
            ["eval", _TOOL, "--observations", str(obs), "--root", str(tmp_path)]
        )
        == 0
    )

    result = json.loads(
        (_evals_dir(tmp_path) / f"{_TOOL}.result.json").read_text(encoding="utf-8")
    )
    _assert_result_shape(result)
    # The mixed run has at least one misfire, so the misfire-shape check is real.
    assert result["misfires"], "mixed run must produce misfires"


@pytest.mark.unit
def test_benchmark_schema_contract(tmp_path: Path) -> None:
    """The written ``<tool>.benchmark.json`` — and each nested run — match the schema."""
    _write_two_runs(tmp_path)
    assert dispatch.run(["benchmark", _TOOL, "--root", str(tmp_path)]) == 0

    report = json.loads(
        (_evals_dir(tmp_path) / f"{_TOOL}.benchmark.json").read_text(encoding="utf-8")
    )
    assert set(report.keys()) == _BENCHMARK_KEYS
    assert isinstance(report["runs"], list) and len(report["runs"]) >= 2
    # Every nested run carries the full result shape.
    for run in report["runs"]:
        _assert_result_shape(run)
