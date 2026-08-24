"""Headless opencode driver: plan freely, pay only behind two gates.

Every paid invocation requires BOTH:
- ``--execute`` on the CLI (absent = dry-run planner), and
- ``DUMMYINDEX_BENCH_ALLOW_PAY=1`` in the environment (opt-in discipline
  mirroring ``tests/eval/test_behavior_arms.py``'s
  ``DUMMYINDEX_BEHAVIOR_ARMS=1``).

Transport: ``opencode run --format json --auto --pure -m <model> --dir <ws>
--title <title> <prompt>``. ``--auto`` approves permissions (the harness must
not block on interactive prompts); ``--pure`` drops external plugins so no
user-level skill/MCP can leak into either arm. JSON events stream on stdout
and are parsed by :mod:`benchmarks.telemetry`; stderr is captured for hard
failures. A non-zero exit or zero-event stream is a :class:`RunnerError` — a
broken transport never reads as a passing or failing arm (the
``behavior_arms.py`` rule).

Contamination control: each paid run executes under sandboxed
``XDG_CONFIG_HOME`` / ``XDG_DATA_HOME`` pointing at empty per-run dirs, with
only ``opencode/auth.json`` copied from the real data home so provider auth
still works. User config, skills, plugins, and session state therefore cannot
reach the agent.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from benchmarks import PAY_GATE_ENV
from benchmarks.telemetry import RunMetrics, metrics_from_stream

DEFAULT_MODEL = "opencode/x-preview-f-free"
DEFAULT_OPENCODE_BIN = "opencode"
DEFAULT_TIMEOUT_S = 1800.0


class RunnerError(Exception):
    """Hard transport failure — never silently treated as an arm result."""


class PayGateError(Exception):
    """Raised when a run would spend money without both gates open."""


def pay_gate_open() -> bool:
    return os.environ.get(PAY_GATE_ENV) == "1"


@dataclass(frozen=True)
class RunnerConfig:
    model: str = DEFAULT_MODEL
    opencode_bin: str = DEFAULT_OPENCODE_BIN
    timeout_s: float = DEFAULT_TIMEOUT_S
    results_dir: Path = Path("results/benchmarks")
    real_data_home: Path | None = None

    def argv(self, *, prompt: str, workspace: Path, title: str) -> list[str]:
        """The exact headless invocation for one task."""
        return [
            self.opencode_bin,
            "run",
            "--format",
            "json",
            "--auto",
            "--pure",
            "-m",
            self.model,
            "--dir",
            str(workspace),
            "--title",
            title,
            prompt,
        ]


@dataclass(frozen=True)
class RunOutcome:
    suite: str
    arm_value: str
    task_id: str
    repeat_index: int
    workspace: str
    prompt_sha256: str
    wall_time_s: float
    metrics: RunMetrics
    executed: bool
    argv: list[str]
    stderr_tail: str = ""

    def to_row(self) -> dict[str, object]:
        row: dict[str, object] = {
            "suite": self.suite,
            "arm": self.arm_value,
            "task_id": self.task_id,
            "repeat_index": self.repeat_index,
            "workspace": self.workspace,
            "prompt_sha256": self.prompt_sha256,
            "wall_time_s": round(self.wall_time_s, 3),
            "executed": self.executed,
        }
        if self.executed:
            row.update(self.metrics.to_row())
            row["stderr_tail"] = self.stderr_tail[-500:]
        else:
            row["argv"] = self.argv
        return row


def _real_opencode_data_home() -> Path:
    override = os.environ.get("XDG_DATA_HOME")
    base = Path(override) if override else Path.home() / ".local" / "share"
    return base / "opencode"


def sandbox_env(real_data_home: Path | None) -> tuple[dict[str, str], Path]:
    """Isolated env for one run; only provider auth crosses the boundary.

    Every call gets its OWN sandbox root: concurrent opencode children must
    never share a state database (they take ``database is locked`` exits).
    The caller removes the returned root when the run ends.
    """
    import uuid

    root = (
        Path(
            os.environ.get("DUMMYINDEX_BENCH_SANDBOX")
            or (Path(tempfile.gettempdir()) / "bi-bench-sandbox")
        )
        / f"run-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    )
    config_home = root / "config"
    data_home = root / "data"
    config_home.mkdir(parents=True, exist_ok=True)
    data_home.mkdir(parents=True, exist_ok=True)
    source = real_data_home or _real_opencode_data_home()
    auth_src = source / "auth.json"
    if auth_src.exists():
        dest_dir = data_home / "opencode"
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not (dest_dir / "auth.json").exists():
            shutil.copy2(auth_src, dest_dir / "auth.json")
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(config_home)
    env["XDG_DATA_HOME"] = str(data_home)
    return env, root


def default_stream(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_s: float,
) -> tuple[Iterator[str], subprocess.Popen]:
    """Start opencode yielding parsed stdout lines; injectable in tests."""
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:  # pragma: no cover - defensive
        raise RunnerError("failed to capture opencode stdout")

    def lines() -> Iterator[str]:
        assert proc.stdout is not None
        with proc.stdout:
            yield from proc.stdout

    return lines(), proc


StreamFn = Callable[[list[str]], Callable[..., tuple[Iterator[str], subprocess.Popen]]]


def run_one_task(
    *,
    suite: str,
    arm_value: str,
    task_id: str,
    repeat_index: int,
    prompt: str,
    workspace: Path,
    config: RunnerConfig,
    execute: bool = False,
    stream_fn: Callable[..., tuple[Iterator[str] | list[str], subprocess.Popen]]
    | None = None,
) -> RunOutcome:
    """Run (or plan) one (suite, arm, task, repeat) cell.

    With ``execute=False`` this returns a planned outcome carrying the exact
    argv and spends nothing. With ``execute=True`` both gates must be open.
    """
    title = f"{suite}/{arm_value}/{task_id}/r{repeat_index}"
    argv = config.argv(prompt=prompt, workspace=workspace, title=title)
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()

    if not execute:
        return RunOutcome(
            suite=suite,
            arm_value=arm_value,
            task_id=task_id,
            repeat_index=repeat_index,
            workspace=str(workspace),
            prompt_sha256=prompt_sha,
            wall_time_s=0.0,
            metrics=RunMetrics(),
            executed=False,
            argv=argv,
        )

    if not pay_gate_open():
        raise PayGateError(
            f"refusing to invoke {config.opencode_bin}: set "
            f"{PAY_GATE_ENV}=1 (and pass --execute) to acknowledge real "
            "token spend"
        )

    started = time.monotonic()
    env, sandbox_root = sandbox_env(config.real_data_home)
    try:
        streaming = stream_fn or default_stream
        lines, proc = streaming(
            argv, cwd=workspace, env=env, timeout_s=config.timeout_s
        )
        if callable(lines):
            lines = lines()
        collected: list[str] = []
        try:
            for line in lines:
                collected.append(line)
            try:
                proc.wait(timeout=config.timeout_s)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                raise RunnerError(
                    f"opencode timed out after {config.timeout_s}s for {title!r}"
                ) from exc
        finally:
            if proc.poll() is None:  # pragma: no cover - defensive
                proc.kill()

        wall = time.monotonic() - started
        stderr_text = ""
        if proc.stderr is not None:
            stderr_text = proc.stderr.read()

        if proc.returncode != 0:
            raise RunnerError(
                f"{config.opencode_bin} exited {proc.returncode} for "
                f"{title!r}: stderr={stderr_text[-500:]!r}"
            )

        metrics = metrics_from_stream(collected)
        if metrics.event_count == 0:
            raise RunnerError(
                f"{config.opencode_bin} produced zero parseable JSON events "
                f"for {title!r} — treating as transport failure"
            )
        if metrics.model is None:
            metrics = replace(metrics, model=config.model)
        _maybe_dump_stream(suite, arm_value, task_id, repeat_index, collected)

        return RunOutcome(
            suite=suite,
            arm_value=arm_value,
            task_id=task_id,
            repeat_index=repeat_index,
            workspace=str(workspace),
            prompt_sha256=prompt_sha,
            wall_time_s=wall,
            metrics=metrics,
            executed=True,
            argv=argv,
            stderr_tail=stderr_text[-500:],
        )
    finally:
        shutil.rmtree(sandbox_root, ignore_errors=True)


def _maybe_dump_stream(
    suite: str,
    arm_value: str,
    task_id: str,
    repeat_index: int,
    collected: list[str],
) -> None:
    """Persist raw JSON events when DUMMYINDEX_BENCH_KEEP_STREAMS=1.

    The capture is the ground truth for evolving ``telemetry.py`` against
    real opencode output; safe to leave on during a sweep (one small file
    per executed cell).
    """
    if os.environ.get("DUMMYINDEX_BENCH_KEEP_STREAMS") != "1":
        return
    slug = task_id.replace("/", "__")
    out = (
        Path(os.environ.get("DUMMYINDEX_BENCH_STREAM_DIR", "results/benchmarks"))
        / suite
        / "streams"
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{slug}.{arm_value}.r{repeat_index}.jsonl").write_text("".join(collected))


def append_row(row: dict[str, object], results_dir: Path, suite: str) -> Path:
    """Append one outcome row to the suite's JSONL log, returning its path."""
    out_dir = results_dir / suite
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "runs.jsonl"
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path
