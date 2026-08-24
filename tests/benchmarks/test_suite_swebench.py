"""SWE-bench suite tests — selection, patch extraction (local git only)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from benchmarks.scoring.swebench_patch import PatchError, extract_model_patch
from benchmarks.suites.swebench import SweTask, build_prompt, select_subset


def make_tasks(
    n_per_repo: int = 3, repos: tuple[str, ...] = ("a/x", "b/y")
) -> list[SweTask]:
    tasks: list[SweTask] = []
    for repo in repos:
        for i in range(n_per_repo):
            tasks.append(
                SweTask(
                    instance_id=f"{repo.replace('/', '-')}-{i}",
                    repo=repo,
                    base_commit="0" * 40,
                    problem_statement=f"issue {repo} #{i} crashes on empty input",
                )
            )
    return tasks


class TestSubset:
    def test_deterministic_and_stratified(self) -> None:
        a = select_subset(make_tasks(), size=4, seed=11)
        b = select_subset(list(reversed(make_tasks())), size=4, seed=11)
        assert [t.instance_id for t in a] == [t.instance_id for t in b]
        repos = {t.repo for t in a}
        assert repos == {"a/x", "b/y"}
        counts = [sum(1 for t in a if t.repo == r) for r in sorted(repos)]
        assert max(counts) - min(counts) <= 1

    def test_size_respected(self) -> None:
        tasks = make_tasks(n_per_repo=10)
        subset = select_subset(tasks, size=5, seed=2)
        assert len(subset) == 5


class TestPrompt:
    def test_contains_repo_issue_and_rules(self) -> None:
        task = make_tasks()[0]
        prompt = build_prompt(task)
        assert task.repo in prompt
        assert task.problem_statement in prompt
        assert "Do not modify tests" in prompt


def _git(argv: list[str], cwd: Path) -> None:
    subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def git_workspace(tmp_path: Path) -> tuple[Path, str]:
    ws = tmp_path / "ws"
    ws.mkdir()
    _git(["init", "-q"], ws)
    _git(["config", "user.email", "bench@example.com"], ws)
    _git(["config", "user.name", "Bench"], ws)
    (ws / "base.txt").write_text("hello\n")
    _git(["add", "-A"], ws)
    _git(["commit", "-q", "-m", "base"], ws)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ws, capture_output=True, text=True, check=True
    ).stdout.strip()
    return ws, base


class TestPatchExtraction:
    def test_no_changes_empty_patch(self, git_workspace) -> None:
        ws, base = git_workspace
        assert extract_model_patch(ws, base) == ""

    def test_modified_and_new_files_in_patch(self, git_workspace) -> None:
        ws, base = git_workspace
        (ws / "base.txt").write_text("changed\n")
        (ws / "new.txt").write_text("brand new\n")
        patch = extract_model_patch(ws, base)
        assert "diff --git" in patch
        assert "base.txt" in patch
        assert "new.txt" in patch
        assert "+brand new" in patch

    def test_index_reset_afterwards(self, git_workspace) -> None:
        ws, base = git_workspace
        (ws / "new.txt").write_text("x\n")
        extract_model_patch(ws, base)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ws,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "?? new.txt" in status

    def test_non_git_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PatchError):
            extract_model_patch(tmp_path, "0" * 40)
