"""Tests for dummyindex.context.cli dispatch."""
from __future__ import annotations

import pytest

from dummyindex.context.cli import dispatch


@pytest.mark.unit
def test_empty_argv_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Usage: dummyindex context" in out
    assert "init" in out
    assert "rebuild" in out
    assert "bootstrap" in out


@pytest.mark.unit
def test_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["--help"])
    assert rc == 0
    assert "Usage: dummyindex context" in capsys.readouterr().out


@pytest.mark.unit
def test_short_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["-h"])
    assert rc == 0
    assert "Usage: dummyindex context" in capsys.readouterr().out


@pytest.mark.unit
def test_unknown_subcommand_errors(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["nonexistent"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "unknown context subcommand" in captured.err
    assert "nonexistent" in captured.err


@pytest.mark.unit
def test_init_stub_returns_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["init"])
    assert rc == 1
    assert "not yet implemented" in capsys.readouterr().err


@pytest.mark.unit
def test_init_accepts_path_arg(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["init", "/some/path"])
    assert rc == 1
    assert "/some/path" in capsys.readouterr().err


@pytest.mark.unit
def test_rebuild_stub_returns_not_implemented() -> None:
    assert dispatch(["rebuild"]) == 1


@pytest.mark.unit
def test_rebuild_accepts_changed_flag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["rebuild", "--changed"])
    assert rc == 1
    assert "changed_only=True" in capsys.readouterr().err


@pytest.mark.unit
def test_rebuild_default_without_changed_flag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["rebuild"])
    assert rc == 1
    assert "changed_only=False" in capsys.readouterr().err


@pytest.mark.unit
def test_bootstrap_stub_returns_not_implemented(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["bootstrap"])
    assert rc == 1
    assert "not yet implemented" in capsys.readouterr().err
