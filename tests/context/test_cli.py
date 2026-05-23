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


@pytest.mark.integration
def test_init_writes_context_folder(tmp_path) -> None:
    import shutil
    from pathlib import Path as _P

    fixture = (
        _P(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    )
    target = tmp_path / "init_target"
    shutil.copytree(fixture, target)
    rc = dispatch(["init", str(target)])
    assert rc == 0
    assert (target / ".context" / "tree.json").exists()
    assert (target / ".context" / "map" / "files.json").exists()
    assert (target / "CLAUDE.md").exists()


@pytest.mark.integration
def test_rebuild_full_writes_context_folder(tmp_path) -> None:
    import shutil
    from pathlib import Path as _P

    fixture = (
        _P(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    )
    target = tmp_path / "rebuild_target"
    shutil.copytree(fixture, target)
    rc = dispatch(["rebuild", str(target)])
    assert rc == 0
    assert (target / ".context" / "tree.json").exists()
    # Full rebuild does NOT touch CLAUDE.md
    assert not (target / "CLAUDE.md").exists()


@pytest.mark.integration
def test_rebuild_changed_skips_when_no_changes(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil
    from pathlib import Path as _P

    fixture = (
        _P(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    )
    target = tmp_path / "rebuild_changed_target"
    shutil.copytree(fixture, target)
    assert dispatch(["init", str(target)]) == 0
    capsys.readouterr()  # drain init output
    rc = dispatch(["rebuild", "--changed", str(target)])
    assert rc == 0
    assert "no source files changed" in capsys.readouterr().out


@pytest.mark.unit
def test_bootstrap_writes_claude_md(tmp_path) -> None:
    target = tmp_path / "cli_bootstrap_target"
    target.mkdir(parents=True)
    rc = dispatch(["bootstrap", str(target)])
    assert rc == 0
    claude_md = target / "CLAUDE.md"
    assert claude_md.exists()
    assert "dummyindex" in claude_md.read_text(encoding="utf-8")
