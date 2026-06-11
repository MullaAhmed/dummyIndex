"""Tests for the `context hooks` CLI: --global/--local + defer-check probe."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import hooks as cli
from dummyindex.context import hooks as H


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def test_defer_check_exit_codes(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    # No local install -> exit 1 (do not defer).
    assert cli.run(["defer-check", "--root", str(tmp_path)]) == 1
    H.install(tmp_path, scope="local")
    # Local install present -> exit 0 (defer).
    assert cli.run(["defer-check", "--root", str(tmp_path)]) == 0


def test_defer_check_is_silent(tmp_path: Path, capsys) -> None:
    cli.run(["defer-check", "--root", str(tmp_path)])
    assert capsys.readouterr().out == ""


def test_install_global_flag_targets_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    rc = cli.run(["install", "--global", "--root", str(tmp_path)])
    assert rc == 0
    assert (home / ".claude" / "settings.json").exists()


def test_status_reports_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    cli.run(["status", "--global", "--root", str(tmp_path)])
    assert "scope=global" in capsys.readouterr().out


def test_unknown_verb_rejected(capsys) -> None:
    assert cli.run(["frobnicate"]) == 2
