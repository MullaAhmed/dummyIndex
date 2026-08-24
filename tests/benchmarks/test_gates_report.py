"""Gate evaluation + report aggregation tests on synthetic rows."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.gates import (
    SNF_NONINFERIORITY_MARGIN,
    SuiteSummary,
    evaluate_gates,
)
from benchmarks.report import aggregate, load_rows, render_report


def row(arm: str, *, passed: bool = True, tools: int = 4, **extra) -> dict:
    base = {
        "suite": "repoqa",
        "arm": arm,
        "task_id": "t",
        "executed": True,
        "passed": passed,
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_tokens": 10,
        "total_tool_calls": tools,
        "tool_calls": {"grep": tools},
        "wall_time_s": 1.0,
    }
    base.update(extra)
    return base


class TestAggregate:
    def test_counts_and_rates(self) -> None:
        rows = [
            row("baseline", passed=True),
            row("baseline", passed=False),
            row("context", passed=True, tools=2),
        ]
        agg_b = aggregate(rows, "baseline")
        assert agg_b.n == 2
        assert agg_b.graded_n == 2
        assert agg_b.pass_rate == pytest.approx(0.5)
        assert agg_b.mean_tool_calls == pytest.approx(4.0)
        assert agg_b.tool_breakdown == {"grep": 8}
        agg_c = aggregate(rows, "context")
        assert agg_c.mean_tool_calls == pytest.approx(2.0)
        assert agg_c.tokens_per_correct == pytest.approx((100 + 50) / 1)

    def test_planned_rows_excluded(self) -> None:
        planned = row("baseline")
        planned["executed"] = False
        assert aggregate([planned], "baseline").n == 0

    def test_ungraded_pass_rate_zero_not_crash(self) -> None:
        ungraded = {k: v for k, v in row("context").items() if k != "passed"}
        agg = aggregate([ungraded], "context")
        assert agg.graded_n == 0
        assert agg.pass_rate == 0.0


class TestGates:
    def _summaries(
        self, base_rate: float, ctx_rate: float, base_tools=4.0, ctx_tools=2.0
    ) -> list[SuiteSummary]:
        return [
            SuiteSummary("repoqa", "baseline", 100, base_rate, base_tools),
            SuiteSummary("repoqa", "context", 100, ctx_rate, ctx_tools),
        ]

    def test_all_good_passes(self) -> None:
        report = evaluate_gates(self._summaries(0.70, 0.71))
        assert report.all_passed

    def test_accuracy_within_margin_passes(self) -> None:
        report = evaluate_gates(self._summaries(0.80, 0.80 - SNF_NONINFERIORITY_MARGIN))
        acc = [g for g in report.results if "accuracy" in g.name][0]
        assert acc.passed

    def test_accuracy_beyond_margin_fails(self) -> None:
        report = evaluate_gates(
            self._summaries(0.90, 0.90 - SNF_NONINFERIORITY_MARGIN - 0.01)
        )
        assert not report.all_passed

    def test_tool_call_regression_fails(self) -> None:
        report = evaluate_gates(self._summaries(0.7, 0.7, ctx_tools=5.0))
        ratio_gate = [g for g in report.results if "ratio" in g.name][0]
        assert not ratio_gate.passed

    def test_missing_arm_summary_fails_closed(self) -> None:
        report = evaluate_gates([SuiteSummary("repoqa", "baseline", 10, 0.5, 3.0)])
        assert not report.all_passed

    def test_render_contains_verdicts(self) -> None:
        text = evaluate_gates(self._summaries(0.7, 0.7)).render()
        assert "[PASS]" in text or "[FAIL]" in text


class TestRenderAndLoad:
    def test_render_report_markdown(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        append_rows(results_dir, "repoqa", [row("baseline"), row("context", tools=2)])
        rows_by_suite = {"repoqa": load_rows(results_dir, "repoqa")}
        text = render_report(rows_by_suite)
        assert "# dummyindex benchmark report" in text
        assert "| baseline |" in text and "| context |" in text
        assert "Pre-registered gates" in text

    def test_render_report_flags_gate_failure(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        append_rows(
            results_dir,
            "repoqa",
            [
                row("baseline", passed=True),
                row("context", passed=False, tools=8),
            ],
        )
        text = render_report({"repoqa": load_rows(results_dir, "repoqa")})
        assert "GATE FAILURE" in text

    def test_load_rows_missing_file_empty(self, tmp_path: Path) -> None:
        assert load_rows(tmp_path, "nope") == []


def append_rows(results_dir: Path, suite: str, rows: list[dict]) -> None:
    from benchmarks.runner import append_row

    for r in rows:
        append_row(r, results_dir, suite)


class TestDedupeAndLedger:
    def test_load_rows_keeps_latest_per_cell(self, tmp_path: Path) -> None:
        from benchmarks.report import load_rows
        from benchmarks.runner import append_row

        append_row(
            {
                "arm": "baseline",
                "task_id": "t",
                "repeat_index": 0,
                "executed": True,
                "passed": False,
            },
            tmp_path,
            "repoqa",
        )
        append_row(
            {
                "arm": "baseline",
                "task_id": "t",
                "repeat_index": 0,
                "executed": True,
                "passed": True,
            },
            tmp_path,
            "repoqa",
        )
        rows = load_rows(tmp_path, "repoqa")
        assert len(rows) == 1 and rows[0]["passed"] is True

    def test_enrichment_section_excluded_from_gate_tables(self, tmp_path: Path) -> None:
        from benchmarks.report import render_report

        ledger = [
            {
                "executed": True,
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": 0.01,
                "wall_time_s": 3.0,
                "task_id": "acme/x/f-1/stage1",
            }
        ]
        text = render_report({"__enrichment__": ledger})
        assert "Amortized index-build cost" in text
        assert "| baseline |" not in text

    def test_index_state_breakdown_line(self, tmp_path: Path) -> None:
        from benchmarks.report import render_report

        row_a = {
            "suite": "repoqa",
            "arm": "baseline",
            "task_id": "t",
            "executed": True,
            "passed": True,
            "input_tokens": 1,
            "output_tokens": 1,
            "cache_read_tokens": 0,
            "total_tool_calls": 1,
            "tool_calls": {},
            "wall_time_s": 1.0,
            "index_state": "backbone",
        }
        row_b = dict(row_a, arm="context", index_state="enriched")
        text = render_report({"repoqa": [row_a, row_b]})
        assert "backbone=1" in text and "enriched=1" in text
