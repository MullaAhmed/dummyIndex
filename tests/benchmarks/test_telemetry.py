"""Unit tests for the benchmarks package — no network, no LLM, no opencode.

The paid-run discipline mirrors ``tests/eval/test_behavior_arms.py``:
everything here is deterministic and free; anything that would shell out to
the real ``opencode`` CLI is exercised only through injectable fakes or the
dry-run planner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class TestStreamParsing:
    def test_parses_fixture_stream(self) -> None:
        from benchmarks.telemetry import metrics_from_stream

        lines = FIXTURES.joinpath("opencode_stream.jsonl").read_text().splitlines()
        metrics = metrics_from_stream(lines)
        assert metrics.session_id == "ses-abc123"
        assert metrics.model == "x-preview-f-free"
        assert metrics.event_count == 10

    def test_tokens_deduped_by_message_id(self) -> None:
        from benchmarks.telemetry import metrics_from_stream

        lines = FIXTURES.joinpath("opencode_stream.jsonl").read_text().splitlines()
        metrics = metrics_from_stream(lines)
        # msg_1 and msg_2 each report step-level totals once.
        assert metrics.input_tokens == 1200 + 1600
        assert metrics.output_tokens == 300 + 500
        assert metrics.cache_read_tokens == 400 + 700
        assert metrics.cache_write_tokens == 50 + 90

    def test_tool_calls_counted_once_per_call(self) -> None:
        from benchmarks.telemetry import metrics_from_stream

        lines = FIXTURES.joinpath("opencode_stream.jsonl").read_text().splitlines()
        metrics = metrics_from_stream(lines)
        # The tool_use wrapper must NOT add an extra unnamed count.
        assert "unknown" not in metrics.tool_calls
        assert metrics.tool_calls == {"glob": 1, "grep": 1, "read": 1}
        assert metrics.total_tool_calls == 3

    def test_response_text_nested_and_top_level(self) -> None:
        from benchmarks.telemetry import metrics_from_stream

        lines = FIXTURES.joinpath("opencode_stream.jsonl").read_text().splitlines()
        metrics = metrics_from_stream(lines)
        assert metrics.response_text == (
            "The answer is authenticate_user.Fallback top-level text."
        )

    def test_cost_takes_cumulative_max(self) -> None:
        from benchmarks.telemetry import metrics_from_stream

        lines = FIXTURES.joinpath("opencode_stream.jsonl").read_text().splitlines()
        metrics = metrics_from_stream(lines)
        assert metrics.cost_usd == pytest.approx(0.009)

    def test_blank_and_garbage_lines_ignored(self) -> None:
        from benchmarks.telemetry import metrics_from_stream

        metrics = metrics_from_stream(["", "not json", '{"type":"x"}'])
        assert metrics.event_count == 1

    def test_real_capture_shape_smoke(self) -> None:
        """Pin the exact wrapper shape observed in a live capture."""
        from benchmarks.telemetry import metrics_from_stream

        raw = (
            '{"type":"tool_use","sessionID":"s1","messageID":"m1",'
            '"part":{"type":"tool","tool":"bash","callID":"c9",'
            '"state":{"status":"completed"}}}\n'
            '{"type":"text","sessionID":"s1","part":{"type":"text",'
            '"text":"done"}}\n'
        )
        metrics = metrics_from_stream(raw.splitlines())
        assert metrics.tool_calls == {"bash": 1}
        assert metrics.response_text == "done"
        assert metrics.session_id == "s1"


class TestExportParsing:
    def test_export_document(self) -> None:
        from benchmarks.telemetry import metrics_from_export

        export = {
            "sessionID": "ses-exp",
            "messages": [
                {
                    "info": {"id": "m1"},
                    "tokens": {"input": 100, "output": 20},
                    "parts": [
                        {"type": "text", "text": "done"},
                        {"type": "tool", "tool": "glob"},
                    ],
                }
            ],
        }
        metrics = metrics_from_export(export)
        assert metrics.session_id == "ses-exp"
        assert metrics.input_tokens == 100
        assert metrics.output_tokens == 20
        assert metrics.tool_calls == {"glob": 1}
        assert metrics.response_text == "done"

    def test_export_invalid_json_raises(self) -> None:
        from benchmarks.telemetry import TelemetryError, metrics_from_export

        with pytest.raises(TelemetryError):
            metrics_from_export("{broken")

    def test_anonymous_usage_keeps_largest_not_sum(self) -> None:
        from benchmarks.telemetry import metrics_from_export

        export = {
            "messages": [
                {"tokens": {"input": 500, "output": 50}},
                {"tokens": {"input": 700, "output": 80}},
            ]
        }
        metrics = metrics_from_export(export)
        assert (metrics.input_tokens, metrics.output_tokens) == (700, 80)


class TestMetricsRow:
    def test_row_is_json_serializable_and_sorted(self) -> None:
        from benchmarks.telemetry import RunMetrics

        row = RunMetrics(tool_calls={"z": 1, "a": 2}).to_row()
        encoded = json.dumps(row)
        decoded = json.loads(encoded)
        assert list(decoded["tool_calls"]) == ["a", "z"]
