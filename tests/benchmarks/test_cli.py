"""CLI contract tests — plan is free; paid commands refuse without gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks import __main__ as cli


class TestPlanCommand:
    def test_plan_runs_free_and_prints_matrix(
        self, capsys: pytest.CaptureFixture[str], monkeypatch
    ) -> None:
        monkeypatch.delenv("DUMMYINDEX_BENCH_ALLOW_PAY", raising=False)
        rc = cli.main(["plan"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "total planned agent runs" in out
        assert "nothing was executed" in out
        assert "opencode run --format json --auto --pure" in out


class TestPayGateRefusal:
    def test_run_repoqa_execute_refused_without_env(
        self, capsys: pytest.CaptureFixture[str], monkeypatch
    ) -> None:
        monkeypatch.delenv("DUMMYINDEX_BENCH_ALLOW_PAY", raising=False)
        rc = cli.main(["run-repoqa", "--execute"])
        assert rc == 3
        assert "DUMMYINDEX_BENCH_ALLOW_PAY" in capsys.readouterr().err

    def test_run_swebench_execute_refused_without_env(
        self, capsys: pytest.CaptureFixture[str], monkeypatch
    ) -> None:
        monkeypatch.delenv("DUMMYINDEX_BENCH_ALLOW_PAY", raising=False)
        rc = cli.main(["run-swebench", "--execute"])
        assert rc == 3


class TestModuleExecution:
    def test_plan_via_subprocess(self) -> None:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "benchmarks", "plan"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "plan mode" in result.stdout

    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        from benchmarks import BENCHMARKS_VERSION

        with pytest.raises(SystemExit) as excinfo:
            cli.main(["--version"])
        assert excinfo.value.code == 0
        assert BENCHMARKS_VERSION in capsys.readouterr().out


class TestResolvedMap:
    def test_resolved_map_typechecked(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("[1,2]")
        with pytest.raises(ValueError, match="JSON object"):
            cli._load_resolved_map(str(bad))


class TestResetCellsCLI:
    def _seed(self, tmp_path: Path) -> None:
        from benchmarks.runner import append_row

        results = tmp_path / "results"
        append_row(
            {"arm": "baseline", "task_id": "b1", "repeat_index": 0},
            results,
            "repoqa",
        )
        append_row(
            {
                "arm": "context",
                "task_id": "c1",
                "repeat_index": 0,
                "index_state": "backbone",
            },
            results,
            "repoqa",
        )

    def test_drops_context_rows_keeps_baseline(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from benchmarks.report import load_rows

        self._seed(tmp_path)
        monkeypatch.setattr(cli, "RESULTS_DIR", tmp_path / "results")
        args = type(
            "A", (), {"suite": "repoqa", "arm": "context", "index_state": None}
        )()
        rc = cli.cmd_reset_cells(args)
        rows = load_rows(tmp_path / "results", "repoqa")
        assert rc == 0
        assert [r["task_id"] for r in rows] == ["b1"]

    def test_backup_written_before_drop(self, tmp_path: Path, monkeypatch) -> None:
        self._seed(tmp_path)
        results = tmp_path / "results"
        monkeypatch.setattr(cli, "RESULTS_DIR", results)
        args = type("A", (), {"suite": "repoqa", "arm": None, "index_state": None})()
        cli.cmd_reset_cells(args)
        backup = results / "repoqa" / "runs.jsonl.bak"
        assert len(backup.read_text().strip().splitlines()) == 2


class TestEnrichDryRun:
    def test_enrich_without_gate_fails_closed(
        self, capsys: pytest.CaptureFixture[str], monkeypatch
    ) -> None:
        monkeypatch.delenv("DUMMYINDEX_BENCH_ALLOW_PAY", raising=False)
        rc = cli.main(["enrich", "--suite", "swebench", "--limit", "1", "--execute"])
        assert rc == 3
        assert "DUMMYINDEX_BENCH_ALLOW_PAY" in capsys.readouterr().err
