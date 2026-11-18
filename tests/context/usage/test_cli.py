"""The `dummyindex usage` CLI boundary: the 0/1/2 exit-code contract (§8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.__main__ import _run_usage


@pytest.fixture
def usage_env(
    usage_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the CLI at the synthetic corpus (CLAUDE_CONFIG_DIR/projects)."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    return usage_corpus


@pytest.mark.unit
def test_chat_happy_path(
    usage_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    assert _run_usage([]) == 0
    assert "Context window now" in capsys.readouterr().out


@pytest.mark.unit
def test_daily_happy_path(usage_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_usage(["daily"]) == 0
    assert "2026-06-01" in capsys.readouterr().out


@pytest.mark.unit
def test_unknown_kind_is_exit_2(
    usage_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_usage(["bogus"]) == 2
    assert "unknown usage report" in capsys.readouterr().err


@pytest.mark.unit
def test_extra_argument_is_exit_2(
    usage_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_usage(["daily", "extra"]) == 2
    assert "unexpected argument" in capsys.readouterr().err


@pytest.mark.unit
def test_help_is_exit_0(usage_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_usage(["--help"]) == 0
    assert "chat" in capsys.readouterr().out


@pytest.mark.unit
def test_usage_error_is_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Empty projects dir → build_report raises UsageError → exit 1.
    (tmp_path / "projects").mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert _run_usage(["daily"]) == 1
    assert "error:" in capsys.readouterr().err
