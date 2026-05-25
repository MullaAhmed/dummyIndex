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
    # CLAUDE.md must live inside .claude/, never at the project root.
    assert (target / ".claude" / "CLAUDE.md").exists()
    assert not (target / "CLAUDE.md").exists()


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
    claude_md = target / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    assert "dummyindex" in claude_md.read_text(encoding="utf-8")
    # Never write to the project root.
    assert not (target / "CLAUDE.md").exists()


@pytest.mark.integration
def test_refresh_indexes_migrates_root_claude_md(tmp_path) -> None:
    """A pre-v0.7.2 install has the managed block at <root>/CLAUDE.md.
    refresh-indexes should relocate it to .claude/CLAUDE.md and leave the
    root file empty of our block (preserving any user-authored content)."""
    import shutil
    from pathlib import Path as _P

    from dummyindex.context.bootstrap import (
        BEGIN_MARKER,
        END_MARKER,
        bootstrap_claude_md,
    )

    fixture = _P(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "migrate_target"
    shutil.copytree(fixture, target)

    # Seed the legacy state: managed block at the project root, no .claude/.
    legacy_claude = target / "CLAUDE.md"
    legacy_claude.write_text(
        f"# Project notes\n\nUser content above.\n\n"
        f"{BEGIN_MARKER}\nstale body\n{END_MARKER}\n\nUser content below.\n",
        encoding="utf-8",
    )
    # Need a .context/ for refresh-indexes to do anything.
    assert dispatch(["init", str(target)]) == 0

    rc = dispatch(["refresh-indexes", str(target)])
    assert rc == 0

    new_claude = target / ".claude" / "CLAUDE.md"
    assert new_claude.exists()
    assert BEGIN_MARKER in new_claude.read_text(encoding="utf-8")

    if legacy_claude.exists():
        leftover = legacy_claude.read_text(encoding="utf-8")
        assert BEGIN_MARKER not in leftover
        assert END_MARKER not in leftover
        # User content must survive the migration.
        assert "User content above." in leftover
        assert "User content below." in leftover


@pytest.mark.integration
def test_conventions_write_cli_places_file(tmp_path) -> None:
    """`dummyindex context conventions-write` atomically drops an
    agent-authored markdown into .context/conventions/<section>.md."""
    import shutil
    from pathlib import Path as _P

    fixture = _P(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "conv_target"
    shutil.copytree(fixture, target)
    assert dispatch(["init", str(target), "--no-hooks"]) == 0

    body = tmp_path / "agent_output.md"
    body.write_text(
        "# Folder organization\n\nGrouped by feature, not by layer.\n",
        encoding="utf-8",
    )
    rc = dispatch([
        "conventions-write",
        "--root", str(target),
        "--section", "folder-organization",
        "--from-file", str(body),
    ])
    assert rc == 0
    written = target / ".context" / "conventions" / "folder-organization.md"
    assert written.exists()
    assert "Grouped by feature" in written.read_text(encoding="utf-8")


@pytest.mark.unit
def test_conventions_write_cli_requires_section_and_source(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch([
        "conventions-write",
        "--root", str(tmp_path),
        "--section", "testing",
    ])
    assert rc == 2
    assert "required" in capsys.readouterr().err.lower()


@pytest.mark.integration
def test_conventions_write_cli_rejects_unknown_section(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil
    from pathlib import Path as _P

    fixture = _P(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "conv_bad_section"
    shutil.copytree(fixture, target)
    assert dispatch(["init", str(target), "--no-hooks"]) == 0

    body = tmp_path / "x.md"
    body.write_text("body", encoding="utf-8")
    rc = dispatch([
        "conventions-write",
        "--root", str(target),
        "--section", "naming",  # naming is statistical, not agent-authored
        "--from-file", str(body),
    ])
    assert rc == 2
    assert "unknown convention section" in capsys.readouterr().err


@pytest.mark.integration
def test_refresh_indexes_removes_pure_managed_root_claude_md(tmp_path) -> None:
    """When root CLAUDE.md contains ONLY our managed block (and nothing else),
    the migration should delete it entirely so the project root is clean."""
    import shutil
    from pathlib import Path as _P

    from dummyindex.context.bootstrap import BEGIN_MARKER, END_MARKER

    fixture = _P(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "migrate_pure_target"
    shutil.copytree(fixture, target)

    legacy_claude = target / "CLAUDE.md"
    legacy_claude.write_text(
        f"{BEGIN_MARKER}\nstale body\n{END_MARKER}\n",
        encoding="utf-8",
    )
    assert dispatch(["init", str(target)]) == 0

    rc = dispatch(["refresh-indexes", str(target)])
    assert rc == 0

    assert not legacy_claude.exists(), (
        f"root CLAUDE.md should be removed when it held only our block, "
        f"got leftover: {legacy_claude.read_text(encoding='utf-8') if legacy_claude.exists() else '(removed)'}"
    )
    assert (target / ".claude" / "CLAUDE.md").exists()
