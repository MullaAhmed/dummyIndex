"""Tests for the v0.6 auto-refresh hooks (git post-commit + Claude Code
PostToolUse + SessionStart) and the `hooks` CLI verb."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.cli import dispatch
from dummyindex.context.hooks import (
    HookStatus,
    install,
    status,
    uninstall,
)


def _init_git_repo(path: Path) -> None:
    """Minimal git init so the post-commit hook has a place to land."""
    subprocess.run(
        ["git", "init", "-q"], cwd=str(path), check=True, capture_output=True
    )


# ----- install --------------------------------------------------------------


@pytest.mark.integration
def test_install_writes_all_three_hooks(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = install(tmp_path)
    assert set(result.installed) == {
        "git/post-commit",
        "claude/PostToolUse",
        "claude/SessionStart",
    }
    assert result.skipped == ()
    assert result.errors == ()

    assert (tmp_path / ".git" / "hooks" / "post-commit").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "hooks" in settings
    assert "PostToolUse" in settings["hooks"]
    assert "SessionStart" in settings["hooks"]


@pytest.mark.integration
def test_install_is_idempotent(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    second = install(tmp_path)
    assert second.installed == ()
    # All three are reported as skipped (already current).
    assert len(second.skipped) == 3


@pytest.mark.integration
def test_install_skips_git_hook_outside_repo(tmp_path: Path) -> None:
    # No .git/ → git hook should skip gracefully, Claude hooks still install.
    result = install(tmp_path)
    assert "claude/PostToolUse" in result.installed
    assert "claude/SessionStart" in result.installed
    assert "git/post-commit" in result.skipped


@pytest.mark.integration
def test_install_refuses_to_overwrite_user_hook(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    target = tmp_path / ".git" / "hooks" / "post-commit"
    target.write_text("#!/bin/bash\n# user's hook\necho hi\n", encoding="utf-8")

    result = install(tmp_path)
    # Must error out on git hook but continue with Claude hooks.
    assert any("git/post-commit" in name for name, _ in result.errors)
    assert "claude/PostToolUse" in result.installed


@pytest.mark.integration
def test_install_preserves_other_claude_hooks(tmp_path: Path) -> None:
    """User's pre-existing hooks under another matcher must survive."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    pre_existing = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo user-hook"}],
                }
            ]
        }
    }
    settings_path.write_text(json.dumps(pre_existing), encoding="utf-8")

    install(tmp_path)
    after = json.loads(settings_path.read_text())
    # User's hook is preserved + our hook is added → 2 entries.
    assert len(after["hooks"]["PostToolUse"]) == 2


# ----- uninstall ------------------------------------------------------------


@pytest.mark.integration
def test_uninstall_removes_all_three(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    result = uninstall(tmp_path)
    assert set(result.removed) == {
        "git/post-commit",
        "claude/PostToolUse",
        "claude/SessionStart",
    }


@pytest.mark.integration
def test_uninstall_leaves_other_hooks_alone(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    # User's hook
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "echo user"}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    install(tmp_path)
    uninstall(tmp_path)
    after = json.loads(settings_path.read_text())
    # User's hook remains.
    user_hooks = after.get("hooks", {}).get("PostToolUse", [])
    assert len(user_hooks) == 1
    assert user_hooks[0]["matcher"] == "Bash"


@pytest.mark.integration
def test_uninstall_idempotent_when_nothing_present(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = uninstall(tmp_path)
    assert result.removed == ()
    assert len(result.skipped) > 0


# ----- status ---------------------------------------------------------------


@pytest.mark.integration
def test_status_all_false_when_absent(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    s = status(tmp_path)
    assert s == HookStatus(
        git_post_commit=False, claude_post_tool_use=False, claude_session_start=False
    )
    assert not s.all_installed


@pytest.mark.integration
def test_status_all_true_after_install(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    s = status(tmp_path)
    assert s.all_installed


# ----- CLI dispatch ---------------------------------------------------------


@pytest.mark.integration
def test_cli_hooks_install_status_uninstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert dispatch(["hooks", "install"]) == 0
    assert "installed" in capsys.readouterr().out

    assert dispatch(["hooks", "status"]) == 0
    out = capsys.readouterr().out
    assert "✓" in out

    assert dispatch(["hooks", "uninstall"]) == 0
    assert "removed" in capsys.readouterr().out

    # Status now non-zero (not all installed).
    assert dispatch(["hooks", "status"]) == 1


@pytest.mark.integration
def test_cli_hooks_unknown_verb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = dispatch(["hooks", "fictional"])
    assert rc == 2
    assert "unknown hooks verb" in capsys.readouterr().err


# ----- ingest auto-installs hooks ------------------------------------------


@pytest.mark.integration
def test_ingest_auto_installs_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dummyindex ingest` (which calls `context init` under the hood) should
    install the auto-refresh hooks by default."""
    import shutil

    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "auto_hook_ingest"
    shutil.copytree(fixture, target)
    _init_git_repo(target)

    monkeypatch.chdir(target)
    assert dispatch(["init"]) == 0

    s = status(target)
    assert s.all_installed, "ingest should install all three hooks by default"


@pytest.mark.integration
def test_ingest_skips_hooks_with_no_hooks_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil

    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "no_hooks_ingest"
    shutil.copytree(fixture, target)
    _init_git_repo(target)

    monkeypatch.chdir(target)
    assert dispatch(["init", "--no-hooks"]) == 0

    s = status(target)
    assert not s.git_post_commit
    assert not s.claude_post_tool_use
    assert not s.claude_session_start
