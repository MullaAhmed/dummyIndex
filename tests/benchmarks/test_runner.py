"""Runner contract tests: pay-gates, dry-run purity, fake-transport flow.

No test here ever invokes the real ``opencode`` binary; the transport is
injected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from benchmarks.runner import (
    DEFAULT_MODEL,
    PayGateError,
    RunnerConfig,
    RunnerError,
    append_row,
    pay_gate_open,
    run_one_task,
)

STREAM_LINES = [
    '{"type":"session","sessionID":"ses-x"}',
    '{"type":"text","text":"42"}',
    '{"type":"assistant","info":{"id":"m1"},"tokens":{"input":10,"output":5}}',
]


@dataclass
class FakeProc:
    returncode: int = 0
    stderr: object = None

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int | None:
        return self.returncode


def fake_stream_factory(lines: list[str], returncode: int = 0):
    def factory(argv, *, cwd, env, timeout_s):
        assert env["XDG_DATA_HOME"]  # sandbox present
        proc = FakeProc(returncode=returncode)
        return (lambda: iter(lines)), proc

    return factory


@pytest.fixture()
def isolated_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUMMYINDEX_BENCH_ALLOW_PAY", raising=False)


class TestPayGate:
    def test_gate_closed_by_default(self, isolated_gate: None) -> None:
        assert not pay_gate_open()

    def test_execute_without_env_refuses(
        self, tmp_path: Path, isolated_gate: None
    ) -> None:
        config = RunnerConfig(real_data_home=tmp_path)
        with pytest.raises(PayGateError):
            run_one_task(
                suite="repoqa",
                arm_value="baseline",
                task_id="t",
                repeat_index=0,
                prompt="p",
                workspace=tmp_path,
                config=config,
                execute=True,
                stream_fn=fake_stream_factory(STREAM_LINES),
            )

    def test_dry_run_spends_nothing_and_returns_argv(
        self, tmp_path: Path, isolated_gate: None
    ) -> None:
        calls: list[str] = []

        def spy(argv, **kwargs):
            calls.append(argv[0])
            raise AssertionError("must not spawn")

        config = RunnerConfig(model=DEFAULT_MODEL, real_data_home=tmp_path)
        outcome = run_one_task(
            suite="s",
            arm_value="baseline",
            task_id="t1",
            repeat_index=2,
            prompt="hello",
            workspace=tmp_path / "ws",
            config=config,
            execute=False,
            stream_fn=spy,
        )
        assert calls == []
        assert outcome.executed is False
        assert "--execute" not in outcome.argv
        assert outcome.argv[0] == "opencode"
        assert "run" in outcome.argv
        assert "-m" in outcome.argv and DEFAULT_MODEL in outcome.argv
        row = outcome.to_row()
        assert "input_tokens" not in row
        assert json.dumps(row)


class TestTransport:
    def test_success_parses_metrics_and_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DUMMYINDEX_BENCH_ALLOW_PAY", "1")
        config = RunnerConfig(real_data_home=tmp_path)
        outcome = run_one_task(
            suite="repoqa",
            arm_value="context",
            task_id="t9",
            repeat_index=0,
            prompt="q",
            workspace=tmp_path,
            config=config,
            execute=True,
            stream_fn=fake_stream_factory(STREAM_LINES),
        )
        assert outcome.executed
        assert outcome.metrics.session_id == "ses-x"
        assert outcome.wall_time_s >= 0.0
        row = outcome.to_row()
        assert row["total_tool_calls"] == 0

    def test_nonzero_exit_is_runner_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DUMMYINDEX_BENCH_ALLOW_PAY", "1")
        config = RunnerConfig(real_data_home=tmp_path)
        with pytest.raises(RunnerError):
            run_one_task(
                suite="s",
                arm_value="baseline",
                task_id="t",
                repeat_index=0,
                prompt="q",
                workspace=tmp_path,
                config=config,
                execute=True,
                stream_fn=fake_stream_factory([], returncode=7),
            )

    def test_zero_events_is_runner_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DUMMYINDEX_BENCH_ALLOW_PAY", "1")
        config = RunnerConfig(real_data_home=tmp_path)
        with pytest.raises(RunnerError, match="zero parseable"):
            run_one_task(
                suite="s",
                arm_value="baseline",
                task_id="t",
                repeat_index=0,
                prompt="q",
                workspace=tmp_path,
                config=config,
                execute=True,
                stream_fn=fake_stream_factory([]),
            )


class TestSandboxEnv:
    def test_auth_copied_across_boundary(self, tmp_path, monkeypatch) -> None:
        from benchmarks.runner import sandbox_env

        fake_home = tmp_path / "home" / "opencode"
        fake_home.mkdir(parents=True)
        (fake_home / "auth.json").write_text("{}")
        monkeypatch.setenv("DUMMYINDEX_BENCH_SANDBOX", str(tmp_path / "box"))
        env, sandbox_root = sandbox_env(fake_home)
        assert env["XDG_CONFIG_HOME"] == str(sandbox_root / "config")
        assert (sandbox_root / "data" / "opencode" / "auth.json").exists()

    def test_sandboxes_unique_per_call(self, tmp_path, monkeypatch) -> None:
        from benchmarks.runner import sandbox_env

        monkeypatch.setenv("DUMMYINDEX_BENCH_SANDBOX", str(tmp_path / "box"))
        _, root_a = sandbox_env(tmp_path)
        _, root_b = sandbox_env(tmp_path)
        assert root_a != root_b


class TestAppendRow:
    def test_appends_jsonl(self, tmp_path: Path) -> None:
        path = append_row({"a": 1}, tmp_path, "repoqa")
        path = append_row({"a": 2}, tmp_path, "repoqa")
        lines = path.read_text().strip().splitlines()
        assert [json.loads(x)["a"] for x in lines] == [1, 2]
