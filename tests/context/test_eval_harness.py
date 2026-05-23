"""Smoke test for evals/v0/run_eval.py — the harness itself, not the model."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_RUN_EVAL = _REPO_ROOT / "evals" / "v0" / "run_eval.py"
_TASKS = _REPO_ROOT / "evals" / "v0" / "tasks.yaml"


@pytest.mark.integration
def test_eval_harness_runs_in_smoke_mode(tmp_path: Path) -> None:
    out_report = tmp_path / "report.md"
    results_dir = tmp_path / "results"
    rc = subprocess.run(
        [
            sys.executable,
            str(_RUN_EVAL),
            "--smoke",
            "--tasks",
            str(_TASKS),
            "--repetitions",
            "1",
            "--out",
            str(out_report),
            "--results-dir",
            str(results_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc.returncode == 0, rc.stderr
    assert out_report.exists()
    text = out_report.read_text(encoding="utf-8")
    assert "SMOKE MODE" in text
    assert "Task" in text


@pytest.mark.integration
def test_eval_harness_writes_per_run_records(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    subprocess.run(
        [
            sys.executable,
            str(_RUN_EVAL),
            "--smoke",
            "--tasks",
            str(_TASKS),
            "--repetitions",
            "2",
            "--out",
            str(tmp_path / "report.md"),
            "--results-dir",
            str(results_dir),
        ],
        check=True,
        capture_output=True,
    )
    json_files = list(results_dir.glob("*.json"))
    assert json_files, "expected per-run JSON records"
    # 5 tasks × 2 conditions × 2 reps = 20 records
    assert len(json_files) == 20
    sample = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert "tool_calls" in sample
    assert "condition" in sample


@pytest.mark.unit
def test_load_tasks_parses_yaml() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("dummyindex_eval_run", _RUN_EVAL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules so dataclasses inside the module can resolve
    # their __module__ during definition.
    sys.modules["dummyindex_eval_run"] = module
    try:
        spec.loader.exec_module(module)
        tasks = module.load_tasks(_TASKS)
    finally:
        sys.modules.pop("dummyindex_eval_run", None)
    assert len(tasks) >= 5
    assert all(t.id for t in tasks)
    assert all(t.prompt for t in tasks)
