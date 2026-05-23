#!/usr/bin/env python3
"""dummyIndex v0 eval harness.

Per V0_SCOPE §7: run each task in tasks.yaml twice (baseline / treatment),
measure tool calls + tokens + quality, aggregate, report.

This file ships in smoke mode — a mock `run_one()` returns canned numbers so
the harness's plumbing (task parsing, alternation, aggregation, reporting) is
exercisable in CI. To wire a real model, see the docstring on `run_one()`.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    difficulty: str
    acceptance: tuple[str, ...]


@dataclass(frozen=True)
class RunRecord:
    task_id: str
    condition: str  # "baseline" | "treatment"
    repetition: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    wall_seconds: float
    passed: bool
    notes: str = ""


@dataclass(frozen=True)
class AggregateRow:
    task_id: str
    baseline_tool_calls_mean: float
    treatment_tool_calls_mean: float
    tool_calls_delta_pct: float
    baseline_tokens_mean: float
    treatment_tokens_mean: float
    tokens_delta_pct: float
    baseline_pass_rate: float
    treatment_pass_rate: float


# ---- Task loader ------------------------------------------------------------


def load_tasks(path: Path) -> list[Task]:
    text = path.read_text(encoding="utf-8")
    data = _parse_minimal_yaml(text)
    tasks: list[Task] = []
    for entry in data.get("tasks", []):
        tasks.append(
            Task(
                id=str(entry["id"]),
                prompt=str(entry.get("prompt", "")).strip(),
                difficulty=str(entry.get("difficulty", "unknown")),
                acceptance=tuple(entry.get("acceptance", [])),
            )
        )
    return tasks


def _parse_minimal_yaml(text: str) -> dict[str, Any]:
    """Tiny in-process YAML reader for our specific tasks.yaml shape.

    We avoid a YAML dependency in the v0 eval harness scaffold. If tasks.yaml
    grows past trivial shapes, swap this for `pyyaml`.
    """
    out: dict[str, Any] = {"tasks": []}
    current: Optional[dict[str, Any]] = None
    state: str = "top"  # top | task | prompt | acceptance
    prompt_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            if state == "prompt":
                prompt_lines.append("")
            continue
        if line.startswith("tasks:"):
            state = "top"
            continue
        if line.lstrip().startswith("- id:"):
            if current is not None:
                if prompt_lines:
                    current["prompt"] = "\n".join(prompt_lines).strip()
                out["tasks"].append(current)
            current = {"id": line.split(":", 1)[1].strip(), "acceptance": []}
            state = "task"
            prompt_lines = []
            continue
        if current is None:
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if state == "prompt" and indent >= 4:
            prompt_lines.append(stripped)
            continue
        if state == "acceptance" and stripped.startswith("- "):
            current["acceptance"].append(stripped[2:].strip().strip('"'))
            continue
        if stripped.startswith("prompt:"):
            state = "prompt"
            prompt_lines = []
            continue
        if stripped.startswith("acceptance:"):
            if prompt_lines:
                current["prompt"] = "\n".join(prompt_lines).strip()
            state = "acceptance"
            continue
        if stripped.startswith("difficulty:"):
            if prompt_lines:
                current["prompt"] = "\n".join(prompt_lines).strip()
                prompt_lines = []
            current["difficulty"] = stripped.split(":", 1)[1].strip()
            state = "task"
            continue
    if current is not None:
        if prompt_lines:
            current["prompt"] = "\n".join(prompt_lines).strip()
        out["tasks"].append(current)
    return out


# ---- Runner -----------------------------------------------------------------


def run_one(
    *,
    task: Task,
    condition: str,
    repetition: int,
    smoke: bool,
) -> RunRecord:
    """Run a single task in either baseline or treatment condition.

    SMOKE MODE: returns canned numbers (treatment "better" by design) so the
    harness's plumbing can be exercised without real model calls.

    REAL MODE: replace this body with a subprocess call to `claude` CLI (or an
    Anthropic SDK invocation) that:
      1. Sets up the repo in the correct condition (treatment: `dummyindex
         context init`; baseline: ensure no .context/ folder, no managed block).
      2. Spawns a Claude Code session, sends `task.prompt`.
      3. Captures tool calls, token counts, wall time from the session log.
      4. Returns a RunRecord (passed=True/False filled in by human judge).
    """
    start = time.perf_counter()
    if not smoke:
        raise NotImplementedError(
            "Real-model run_one() is intentionally not implemented in PR 6. "
            "See evals/v0/README.md for how to wire it."
        )
    # Smoke mode: synthetic numbers; treatment is "better" by design.
    if condition == "baseline":
        tool_calls, tokens_in, tokens_out = 20, 12_000, 1_200
    else:
        tool_calls, tokens_in, tokens_out = 13, 9_000, 1_100
    passed = True
    return RunRecord(
        task_id=task.id,
        condition=condition,
        repetition=repetition,
        tool_calls=tool_calls,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        wall_seconds=round(time.perf_counter() - start, 4),
        passed=passed,
        notes="smoke" if smoke else "",
    )


def run_all(
    tasks: list[Task],
    *,
    repetitions: int,
    smoke: bool,
) -> list[RunRecord]:
    """Alternate baseline / treatment per task; repeat `repetitions` times."""
    records: list[RunRecord] = []
    for rep in range(1, repetitions + 1):
        for task in tasks:
            for condition in ("baseline", "treatment"):
                records.append(
                    run_one(task=task, condition=condition, repetition=rep, smoke=smoke)
                )
    return records


# ---- Aggregation ------------------------------------------------------------


def aggregate(records: list[RunRecord]) -> list[AggregateRow]:
    rows: list[AggregateRow] = []
    by_task: dict[str, list[RunRecord]] = {}
    for r in records:
        by_task.setdefault(r.task_id, []).append(r)
    for task_id, task_records in sorted(by_task.items()):
        baseline = [r for r in task_records if r.condition == "baseline"]
        treatment = [r for r in task_records if r.condition == "treatment"]
        b_tc = statistics.mean(r.tool_calls for r in baseline) if baseline else 0
        t_tc = statistics.mean(r.tool_calls for r in treatment) if treatment else 0
        b_tk = (
            statistics.mean(r.input_tokens + r.output_tokens for r in baseline)
            if baseline else 0
        )
        t_tk = (
            statistics.mean(r.input_tokens + r.output_tokens for r in treatment)
            if treatment else 0
        )
        rows.append(
            AggregateRow(
                task_id=task_id,
                baseline_tool_calls_mean=round(b_tc, 2),
                treatment_tool_calls_mean=round(t_tc, 2),
                tool_calls_delta_pct=_pct_change(b_tc, t_tc),
                baseline_tokens_mean=round(b_tk, 2),
                treatment_tokens_mean=round(t_tk, 2),
                tokens_delta_pct=_pct_change(b_tk, t_tk),
                baseline_pass_rate=_pass_rate(baseline),
                treatment_pass_rate=_pass_rate(treatment),
            )
        )
    return rows


def _pct_change(before: float, after: float) -> float:
    if before == 0:
        return 0.0
    return round(((after - before) / before) * 100, 2)


def _pass_rate(records: list[RunRecord]) -> float:
    if not records:
        return 0.0
    return round(sum(1 for r in records if r.passed) / len(records), 4)


# ---- Reporting --------------------------------------------------------------


def render_report(rows: list[AggregateRow], *, smoke: bool) -> str:
    lines: list[str] = ["# dummyIndex v0 eval report", ""]
    if smoke:
        lines.append("**SMOKE MODE — numbers are synthetic.**")
        lines.append("")
    lines.append(
        "| Task | Baseline ToolCalls | Treatment ToolCalls | Δ% | "
        "Baseline Tokens | Treatment Tokens | Δ% | Baseline Pass | Treatment Pass |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        lines.append(
            f"| {r.task_id} | {r.baseline_tool_calls_mean} | "
            f"{r.treatment_tool_calls_mean} | {r.tool_calls_delta_pct}% | "
            f"{r.baseline_tokens_mean} | {r.treatment_tokens_mean} | "
            f"{r.tokens_delta_pct}% | {int(r.baseline_pass_rate * 100)}% | "
            f"{int(r.treatment_pass_rate * 100)}% |"
        )
    lines.append("")
    overall_tc = statistics.mean(r.tool_calls_delta_pct for r in rows) if rows else 0
    overall_tk = statistics.mean(r.tokens_delta_pct for r in rows) if rows else 0
    lines.append(
        f"**Overall:** tool calls mean Δ {overall_tc:+.2f}%, "
        f"tokens mean Δ {overall_tk:+.2f}%."
    )
    lines.append("")
    lines.append("v0 pass criteria (per V0_SCOPE §7.4):")
    lines.append("- Tool calls: ≥30% reduction")
    lines.append("- Tokens: ≥15% reduction")
    lines.append("- Quality: no regression")
    lines.append("")
    return "\n".join(lines)


# ---- CLI --------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="dummyIndex v0 eval harness")
    parser.add_argument(
        "--tasks", type=Path, default=_HERE / "tasks.yaml",
        help="Path to tasks.yaml",
    )
    parser.add_argument(
        "--repetitions", type=int, default=3,
        help="Repetitions per (task, condition). Default 3.",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Smoke mode: use canned synthetic numbers (no real model calls).",
    )
    parser.add_argument(
        "--out", type=Path, default=_HERE / "report.md",
        help="Where to write the aggregated report.",
    )
    parser.add_argument(
        "--results-dir", type=Path, default=_HERE / "results",
        help="Where to drop per-run JSON records.",
    )
    args = parser.parse_args(argv)

    tasks = load_tasks(args.tasks)
    if not tasks:
        print("no tasks loaded", file=sys.stderr)
        return 2

    records = run_all(tasks, repetitions=args.repetitions, smoke=args.smoke)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    for r in records:
        out = args.results_dir / f"{r.task_id}_{r.condition}_{r.repetition}.json"
        out.write_text(json.dumps(asdict(r), indent=2) + "\n", encoding="utf-8")

    rows = aggregate(records)
    report = render_report(rows, smoke=args.smoke)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
