"""RepoQA suite unit tests — official release schema, subsets, prompts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.suites.repoqa import (
    NAME_INSTRUCTION,
    SnfTask,
    SuiteDataError,
    build_prompt,
    repo_record,
    select_subset,
    tasks_from_records,
)


def make_records() -> dict:
    """Tiny stand-in for the official nested schema (2 langs x 1 repo x 3)."""

    def needle(name: str) -> dict:
        return {
            "name": name,
            "description": f"does {name}",
            "path": f"src/{name}.py",
            "start_line": 0,
            "end_line": 2,
        }

    def repo_record(repo: str) -> dict:
        return {
            "repo": repo,
            "commit_sha": "a" * 40,
            "topic": "t",
            "entrypoint_path": ".",
            "needles": [needle(f"{repo.split('/')[-1]}_fn{i}") for i in range(3)],
            "content": {},
        }

    return {
        "python": [repo_record("acme/pylib")],
        "rust": [repo_record("acme/rslib")],
    }


class TestTasksFromRecords:
    def test_flattens_official_schema(self) -> None:
        tasks = tasks_from_records(make_records())
        assert len(tasks) == 6
        first = tasks[0]
        assert first.language == "python"
        assert first.repo == "acme/pylib"
        assert first.commit == "a" * 40
        assert first.task_id == f"python/acme/pylib/{first.func}"
        assert first.start_line == 0 and first.end_line == 2

    def test_missing_fields_fail_loudly(self) -> None:
        bad = {
            "python": [{"repo": "x/y", "commit_sha": "c", "needles": [{"name": "n"}]}]
        }
        with pytest.raises(SuiteDataError, match="malformed needle"):
            tasks_from_records(bad)

    def test_empty_records_fail(self) -> None:
        with pytest.raises(SuiteDataError):
            tasks_from_records({})


class TestRepoRecord:
    def test_lookup_and_error(self) -> None:
        records = make_records()
        found = repo_record(records, "python", "acme/pylib")
        assert found["topic"] == "t"
        with pytest.raises(SuiteDataError, match="no record"):
            repo_record(records, "python", "nope/none")


def make_tasks() -> list[SnfTask]:
    return tasks_from_records(make_records())


class TestSubsetSelection:
    def test_deterministic_across_shuffles(self) -> None:
        tasks = make_tasks()
        a = select_subset(tasks, per_lang_per_repo=2, seed=7)
        b = select_subset(list(reversed(tasks)), per_lang_per_repo=2, seed=7)
        assert [t.task_id for t in a] == [t.task_id for t in b]

    def test_stratified_per_lang_per_repo(self) -> None:
        subset = select_subset(make_tasks(), per_lang_per_repo=2, seed=1)
        counts: dict[tuple[str, str], int] = {}
        for t in subset:
            key = (t.language, t.repo)
            counts[key] = counts.get(key, 0) + 1
        assert set(counts.values()) == {2}
        assert len(counts) == 2

    def test_overshoot_clamped(self) -> None:
        subset = select_subset(make_tasks(), per_lang_per_repo=99, seed=3)
        assert len(subset) == len(make_tasks())


class TestPromptProtocols:
    def test_name_protocol(self) -> None:
        task = make_tasks()[0]
        prompt = build_prompt(task, protocol="name")
        assert NAME_INSTRUCTION.splitlines()[0] in prompt
        assert task.description in prompt

    def test_function_protocol(self) -> None:
        task = make_tasks()[0]
        prompt = build_prompt(task, protocol="function")
        assert "COMPLETE code" in prompt
        assert task.description in prompt

    def test_protocols_differ(self) -> None:
        task = make_tasks()[0]
        assert build_prompt(task, protocol="name") != build_prompt(
            task, protocol="function"
        )

    def test_unknown_protocol_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_prompt(make_tasks()[0], protocol="bogus")


class TestLoaderOverride:
    def test_override_env_loads_local_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from benchmarks.suites import repoqa

        data_file = tmp_path / "records.json"
        data_file.write_text(json.dumps(make_records()))
        monkeypatch.setenv(repoqa.DATA_OVERRIDE_ENV, str(data_file))
        records = repoqa.load_repoqa_records(tmp_path / "unused-cache")
        assert set(records) == {"python", "rust"}

    def test_override_env_missing_file_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from benchmarks.suites import repoqa

        monkeypatch.setenv(repoqa.DATA_OVERRIDE_ENV, str(tmp_path / "gone.json"))
        with pytest.raises(SuiteDataError, match="not found"):
            repoqa.load_repoqa_records(tmp_path)
