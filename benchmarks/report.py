"""Aggregate run rows into the arm-vs-arm comparison report.

Input: the JSONL logs written by :func:`benchmarks.runner.append_row` (one
row per executed or planned cell). Output: a markdown report with, per
suite x arm — n, pass rate, mean/stddev tokens (input/output/cache), mean
tool calls with per-tool breakdown, wall time, and tokens-per-correct-answer
— followed by the pre-registered gate evaluation.

Grading joins: RepoQA rows carry their verdict at report time (the grader is
pure and cheap); SWE-bench resolve status is merged in from the official
harness's report when present. Both arrive as ``passed`` booleans on the row
via :func:`load_rows` consumers; this module only aggregates what it is
given.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from benchmarks.gates import SuiteSummary, evaluate_gates


@dataclass(frozen=True)
class Aggregates:
    n: int
    graded_n: int
    pass_rate: float
    mean_input: float
    mean_output: float
    mean_cache_read: float
    std_output: float
    mean_tool_calls: float
    tool_breakdown: dict[str, int]
    total_wall_s: float
    tokens_per_correct: float | None


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def aggregate(rows: Sequence[dict[str, object]], arm_value: str) -> Aggregates:
    cells = [r for r in rows if r.get("arm") == arm_value and r.get("executed")]
    if not cells:
        return Aggregates(
            n=0,
            graded_n=0,
            pass_rate=0.0,
            mean_input=0.0,
            mean_output=0.0,
            mean_cache_read=0.0,
            std_output=0.0,
            mean_tool_calls=0.0,
            tool_breakdown={},
            total_wall_s=0.0,
            tokens_per_correct=None,
        )
    graded = [r for r in cells if isinstance(r.get("passed"), bool)]
    passes = sum(1 for r in graded if r["passed"])
    inputs = [float(r["input_tokens"]) for r in cells]
    outputs = [float(r["output_tokens"]) for r in cells]
    caches = [float(r["cache_read_tokens"]) for r in cells]
    tools = [float(r.get("total_tool_calls") or 0) for r in cells]
    walls = [float(r["wall_time_s"]) for r in cells]
    breakdown: dict[str, int] = {}
    for row in cells:
        raw = row.get("tool_calls")
        if isinstance(raw, dict):
            for name, count in raw.items():
                breakdown[name] = breakdown.get(name, 0) + int(count)
    std_output = statistics.pstdev(outputs) if len(outputs) > 1 else 0.0
    correct_tokens = (
        sum(float(r["output_tokens"]) for r in graded if r["passed"])
        + sum(float(r["input_tokens"]) for r in graded if r["passed"])
        if graded
        else 0.0
    )
    tokens_per_correct = correct_tokens / passes if passes else None
    return Aggregates(
        n=len(cells),
        graded_n=len(graded),
        pass_rate=passes / len(graded) if graded else 0.0,
        mean_input=_mean(inputs),
        mean_output=_mean(outputs),
        mean_cache_read=_mean(caches),
        std_output=std_output,
        mean_tool_calls=_mean(tools),
        tool_breakdown=dict(sorted(breakdown.items(), key=lambda kv: -kv[1])),
        total_wall_s=math.fsum(walls),
        tokens_per_correct=tokens_per_correct,
    )


def load_rows(results_dir: Path, suite: str) -> list[dict[str, object]]:
    """Load a suite's rows, keeping only the LAST row per cell.

    Resume-safe sweeps can append a second row for the same
    (arm, task_id, repeat) after a reset-and-rerun; latest observation wins.
    """
    path = results_dir / suite / "runs.jsonl"
    if not path.exists():
        return []
    latest: dict[tuple, dict[str, object]] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        row = json.loads(stripped)
        key = (row.get("arm"), row.get("task_id"), row.get("repeat_index"))
        latest[key] = row
    return list(latest.values())


def enrichment_totals(rows: Sequence[dict[str, object]]) -> dict[str, float]:
    """Aggregate an enrichment-ledger row list into one-time cost numbers."""
    cells = [r for r in rows if r.get("executed")]
    inputs = [float(r["input_tokens"]) for r in cells]
    outputs = [float(r["output_tokens"]) for r in cells]
    costs = [
        float(r["cost_usd"])
        for r in cells
        if isinstance(r.get("cost_usd"), (int, float))
    ]
    walls = [float(r["wall_time_s"]) for r in cells]
    return {
        "agent_calls": len(cells),
        "input_tokens": math.fsum(inputs),
        "output_tokens": math.fsum(outputs),
        "cost_usd": math.fsum(costs),
        "wall_s": math.fsum(walls),
    }


def render_enrichment_section(rows: Sequence[dict[str, object]]) -> str:
    """The one-time index-build cost block; never part of gate math."""
    totals = enrichment_totals(rows)
    lines = [
        "## Amortized index-build cost (phase 0)",
        "",
        "One-time council enrichment of target repos, tracked separately",
        "from sweep metrics by design.",
        "",
        "| agent calls | input tokens | output tokens | cost USD | wall s |",
        "|---|---|---|---|---|",
        f"| {totals['agent_calls']} | {totals['input_tokens']:,.0f} "
        f"| {totals['output_tokens']:,.0f} | {totals['cost_usd']:.4f} "
        f"| {totals['wall_s']:,.1f} |",
        "",
    ]
    per_repo: dict[str, int] = {}
    for row in rows:
        repo = str(row.get("task_id", "?")).split("/")[0]
        per_repo[repo] = per_repo.get(repo, 0) + 1
    if per_repo:
        lines.append("Calls per repo (top 10):")
        for repo, count in sorted(per_repo.items(), key=lambda kv: -kv[1])[:10]:
            lines.append(f"- `{repo}` × {count}")
        lines.append("")
    return "\n".join(lines)


def render_report(
    rows_by_suite: dict[str, list[dict[str, object]]],
    *,
    title: str = "dummyindex benchmark report",
) -> str:
    """Render the full markdown comparison across suites.

    Suite keys wrapped in dunder (``__enrichment__``) are rendered as the
    amortized-cost section instead of an arm table, and never touch gates.
    """
    lines: list[str] = [f"# {title}", ""]
    enrichment_rows = rows_by_suite.get("__enrichment__") or []
    if enrichment_rows:
        lines.append(render_enrichment_section(enrichment_rows))
    summaries: list[SuiteSummary] = []
    for suite in sorted(k for k in rows_by_suite if not k.startswith("__")):
        rows = rows_by_suite[suite]
        lines.append(f"## Suite: {suite}")
        lines.append("")
        states: dict[str, int] = {}
        for row in rows:
            state = row.get("index_state")
            if isinstance(state, str):
                states[state] = states.get(state, 0) + 1
        if states:
            breakdown = ", ".join(f"{k}={v}" for k, v in sorted(states.items()))
            lines.append(f"Index condition of measured cells: {breakdown}")
            lines.append("")
        lines.append(
            "| arm | n | graded | pass rate | mean in tok | mean out tok "
            "(±σ) | cache read | mean tool calls | wall s | tok/correct |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for arm_value in ("baseline", "context"):
            agg = aggregate(rows, arm_value)
            summaries.append(
                SuiteSummary(
                    suite=suite,
                    arm_value=arm_value,
                    n=agg.n,
                    pass_rate=agg.pass_rate,
                    mean_tool_calls=agg.mean_tool_calls,
                )
            )
            tpc = (
                f"{agg.tokens_per_correct:,.0f}"
                if agg.tokens_per_correct is not None
                else "n/a"
            )
            lines.append(
                f"| {arm_value} | {agg.n} | {agg.graded_n} "
                f"| {agg.pass_rate:.3f} | {agg.mean_input:,.0f} "
                f"| {agg.mean_output:,.0f} (±{agg.std_output:,.0f}) "
                f"| {agg.mean_cache_read:,.0f} "
                f"| {agg.mean_tool_calls:.2f} "
                f"| {agg.total_wall_s:,.1f} | {tpc} |"
            )
        lines.append("")
        for arm_value in ("baseline", "context"):
            agg = aggregate(rows, arm_value)
            if agg.tool_breakdown:
                top = ", ".join(
                    f"{name}×{count}"
                    for name, count in list(agg.tool_breakdown.items())[:8]
                )
                lines.append(f"- `{arm_value}` tools: {top}")
        lines.append("")

    gates = evaluate_gates(summaries)
    lines.append("## Pre-registered gates")
    lines.append("")
    lines.append("```")
    lines.append(gates.render())
    lines.append("```")
    lines.append("")
    lines.append(
        "**Verdict:** " + ("all gates passed" if gates.all_passed else "GATE FAILURE")
    )
    lines.append("")
    return "\n".join(lines)


def write_report(
    rows_by_suite: dict[str, list[dict[str, object]]],
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(rows_by_suite))
    return path
