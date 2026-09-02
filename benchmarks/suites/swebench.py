"""SWE-bench Lite end-to-end suite adapter.

Source: HF ``princeton-nlp/SWE-bench_Lite`` (300 instances, 12 Python repos).
This suite measures the full loop — understand the issue, locate the code,
edit it — so it exercises dummyindex's stated success metric (tool-call
reduction) under real workload, not just retrieval.

Division of labor with the official tooling:
- **Agent**: opencode in the arm's workspace (clone pinned at
  ``base_commit``, arm-specific ``AGENTS.md``).
- **Patch extraction**: ours (`scoring/swebench_patch.py`) — a plain git diff
  of the workspace against ``base_commit`` after the agent stops.
- **Grading**: the official dockerized harness via ``scoring/swegrade.sh``;
  this module only emits its predictions JSONL. Grading never runs inside
  this package's tests.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from benchmarks.arms import Arm, prepare_arm_workspace
from benchmarks.suites import SuiteDataError

HF_DATASET = "princeton-nlp/SWE-bench_Lite"
DEFAULT_SUBSET_SIZE = 50

AGENT_INSTRUCTION = (
    "You are working in a checkout of {repo} at commit {base_sha}. "
    "Resolve the GitHub issue below by making the minimal correct change to "
    "the repository files.\n\n"
    "Rules:\n"
    "- Do not modify tests to make them pass.\n"
    "- Do not create new test files.\n"
    "- When finished, stop; your file changes are collected automatically."
)


@dataclass(frozen=True)
class SweTask:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.repo}.git"


def load_swebench_lite() -> list[SweTask]:
    """Load SWE-bench Lite via the optional ``datasets`` package."""
    try:
        from datasets import load_dataset  # noqa: PLC0415 - optional dep
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise SuiteDataError(
            "the `datasets` package is required for SWE-bench loading; "
            "install it with `uv pip install datasets`"
        ) from exc
    ds = load_dataset(HF_DATASET)["test"]
    tasks: list[SweTask] = []
    for row in ds.to_list():
        if not isinstance(row, dict):
            continue
        record = dict(row)
        instance_id = record.get("instance_id")
        repo = record.get("repo")
        commit = record.get("base_commit")
        statement = record.get("problem_statement")
        if not (instance_id and repo and commit and statement):
            raise SuiteDataError(
                f"SWE-bench record missing required fields: {sorted(record)}"
            )
        tasks.append(
            SweTask(
                instance_id=str(instance_id),
                repo=str(repo),
                base_commit=str(commit),
                problem_statement=str(statement),
            )
        )
    return tasks


def select_subset(tasks: Sequence[SweTask], *, size: int, seed: int) -> list[SweTask]:
    """Deterministic subset stratified round-robin across repos.

    Cycles over repos in sorted order (each repo's pool pre-shuffled with the
    seed) until ``size`` instances are taken or every pool is exhausted, so
    any requested size is honored while staying repo-balanced.
    """
    by_repo: dict[str, list[SweTask]] = {}
    for task in tasks:
        by_repo.setdefault(task.repo, []).append(task)
    rng = random.Random(seed)
    pools = {
        repo: rng.sample(sorted(pool, key=lambda t: t.instance_id), len(pool))
        for repo, pool in sorted(by_repo.items())
    }
    chosen: list[SweTask] = []
    order = sorted(pools)
    while len(chosen) < size and any(pools.values()):
        for repo in order:
            if len(chosen) >= size:
                break
            if pools[repo]:
                chosen.append(pools[repo].pop())
    return sorted(chosen, key=lambda t: t.instance_id)


def build_prompt(task: SweTask) -> str:
    header = AGENT_INSTRUCTION.format(repo=task.repo, base_sha=task.base_commit[:12])
    return f"{header}\n\nGitHub issue:\n{task.problem_statement}"


def prepared_for_task(
    arm: Arm,
    task: SweTask,
    *,
    workspace_root: Path,
    cache_root: Path,
    repeat: int | None = None,
    run_setup: Callable[..., None] | None = None,
) -> Path:
    prepared = prepare_arm_workspace(
        arm,
        task.repo,
        task.base_commit,
        workspace_root,
        cache_root=cache_root,
        repeat=repeat,
        run_setup=run_setup,
    )
    return prepared.path


def write_predictions(rows: Sequence[dict[str, str]], path: Path) -> Path:
    """Emit official-harness predictions JSONL (instance_id + model_patch)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def workspace_for_task(
    arm: Arm,
    task,
    *,
    workspace_root: Path,
    cache_root: Path,
    repeat: int | None = None,
    run_setup=None,
) -> Path:
    """Path-only convenience; see :func:`prepared_for_task` for index_mode."""
    return prepared_for_task(
        arm,
        task,
        workspace_root=workspace_root,
        cache_root=cache_root,
        repeat=repeat,
        run_setup=run_setup,
    ).path


__all__ = [
    "AGENT_INSTRUCTION",
    "DEFAULT_SUBSET_SIZE",
    "HF_DATASET",
    "SweTask",
    "SuiteDataError",
    "build_prompt",
    "prepared_for_task",
    "load_swebench_lite",
    "select_subset",
    "workspace_for_task",
    "write_predictions",
]
