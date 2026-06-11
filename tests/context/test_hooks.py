"""Tests for the SessionStart drift hook (v0.13.5+) and the `hooks` CLI verb.

Pre-0.13.5 also installed a ``git post-commit`` hook and a Claude
``PostToolUse`` hook. Those were retired because they re-ran the
deterministic backbone on every edit and clobbered council-enriched
feature folders. Several tests below exercise the upgrade path —
``install`` must scrub the legacy entries it finds.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.hooks import (
    HookStatus,
    install,
    status,
    uninstall,
)


_LEGACY_SENTINEL_HOOK = {
    "matcher": "Edit|Write|MultiEdit",
    "hooks": [
        {
            "type": "command",
            "command": (
                "# DUMMYINDEX_AUTO_REFRESH\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                "dummyindex context rebuild --changed --root \"$CLAUDE_PROJECT_DIR\" "
                ">/dev/null 2>&1 &\n"
                "exit 0\n"
            ),
        }
    ],
}

_LEGACY_GIT_HOOK_BODY = (
    "#!/usr/bin/env bash\n"
    "# DUMMYINDEX_AUTO_REFRESH\n"
    "exit 0\n"
)


def _init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q"], cwd=str(path), check=True, capture_output=True
    )


def _write_settings(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ----- install --------------------------------------------------------------


@pytest.mark.integration
def test_install_writes_session_start_hook(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = install(tmp_path)
    assert "claude/SessionStart" in result.installed
    assert result.errors == ()

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "SessionStart" in settings["hooks"]
    cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "DUMMYINDEX_AUTO_REFRESH" in cmd
    assert "plan-update" in cmd


@pytest.mark.integration
def test_install_does_not_create_git_post_commit(tmp_path: Path) -> None:
    """The post-commit shell hook was retired in 0.13.5."""
    _init_git_repo(tmp_path)
    install(tmp_path)
    assert not (tmp_path / ".git" / "hooks" / "post-commit").exists()


@pytest.mark.integration
def test_install_is_idempotent(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    second = install(tmp_path)
    assert second.installed == ()
    assert "claude/SessionStart" in second.skipped


@pytest.mark.integration
def test_install_works_without_git(tmp_path: Path) -> None:
    """No .git/ → SessionStart still installs; nothing depends on git anymore."""
    result = install(tmp_path)
    assert "claude/SessionStart" in result.installed


@pytest.mark.integration
def test_install_preserves_user_authored_hooks(tmp_path: Path) -> None:
    """User entries (no sentinel) survive a fresh install."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "echo user"}],
                    }
                ]
            }
        },
    )

    install(tmp_path)
    after = json.loads(settings_path.read_text())
    # User's entry + our entry → 2 entries total.
    assert len(after["hooks"]["SessionStart"]) == 2


@pytest.mark.integration
def test_install_preserves_malformed_settings(tmp_path: Path) -> None:
    """A malformed settings.json must never be clobbered to just our hook.

    Regression: ``_install_claude_hook`` used to reset ``settings = {}`` on a
    ``JSONDecodeError`` and then overwrite the file — silently destroying the
    user's permissions / env / other hooks. The fix is preserve-or-refuse:
    leave the file byte-for-byte intact and surface the failure.
    """
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    broken = '{"permissions": {"allow": ["Bash"]}, OOPS not valid json'
    settings_path.write_text(broken, encoding="utf-8")

    result = install(tmp_path)

    # File left exactly as it was — no clobber.
    assert settings_path.read_text(encoding="utf-8") == broken
    # The failure is surfaced, not swallowed, and we did not claim success.
    assert any(name == "claude/SessionStart" for name, _ in result.errors)
    assert "claude/SessionStart" not in result.installed


@pytest.mark.integration
def test_install_refuses_non_object_settings(tmp_path: Path) -> None:
    """Valid JSON that isn't an object (e.g. a list) must not crash or clobber.

    Regression: ``settings.setdefault("hooks", {})`` raised an uncaught
    ``AttributeError`` when the top-level JSON was a list/number/string.
    """
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = '["not", "an", "object"]'
    settings_path.write_text(payload, encoding="utf-8")

    result = install(tmp_path)

    assert settings_path.read_text(encoding="utf-8") == payload
    assert any(name == "claude/SessionStart" for name, _ in result.errors)
    assert "claude/SessionStart" not in result.installed


# ----- legacy scrub (upgrade path) ----------------------------------------


@pytest.mark.integration
def test_install_scrubs_legacy_post_tool_use(tmp_path: Path) -> None:
    """Upgrading from <=0.13.4 must remove our PostToolUse entry."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {"hooks": {"PostToolUse": [_LEGACY_SENTINEL_HOOK]}},
    )

    result = install(tmp_path)
    assert "claude/PostToolUse (legacy)" in result.removed

    after = json.loads(settings_path.read_text())
    # The whole PostToolUse key is gone because the only entry was ours.
    assert "PostToolUse" not in after.get("hooks", {})


@pytest.mark.integration
def test_install_scrubs_legacy_git_post_commit(tmp_path: Path) -> None:
    """Upgrade path: our legacy post-commit script is deleted on install."""
    _init_git_repo(tmp_path)
    target = tmp_path / ".git" / "hooks" / "post-commit"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_LEGACY_GIT_HOOK_BODY, encoding="utf-8")

    result = install(tmp_path)
    assert "git/post-commit (legacy)" in result.removed
    assert not target.exists()


@pytest.mark.integration
def test_install_leaves_foreign_git_post_commit_alone(tmp_path: Path) -> None:
    """A user-authored post-commit hook (no sentinel) must survive."""
    _init_git_repo(tmp_path)
    target = tmp_path / ".git" / "hooks" / "post-commit"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("#!/bin/bash\necho user\n", encoding="utf-8")

    result = install(tmp_path)
    assert "git/post-commit (legacy)" not in result.removed
    assert target.exists()


@pytest.mark.integration
def test_install_scrubs_legacy_post_commit_in_submodule(tmp_path: Path) -> None:
    """For a submodule, the real hooks dir lives under the superproject's
    ``.git/modules/<name>`` — the legacy scrub must follow the `.git` pointer
    file there, not look in ``<submodule>/.git/hooks`` (which doesn't exist)."""
    module_dir = tmp_path / ".git" / "modules" / "backend"
    (module_dir / "hooks").mkdir(parents=True)
    submodule = tmp_path / "backend"
    submodule.mkdir()
    (submodule / ".git").write_text(
        "gitdir: ../.git/modules/backend\n", encoding="utf-8"
    )
    target = module_dir / "hooks" / "post-commit"
    target.write_text(_LEGACY_GIT_HOOK_BODY, encoding="utf-8")

    result = install(submodule)
    assert "git/post-commit (legacy)" in result.removed
    assert not target.exists()


@pytest.mark.integration
def test_install_scrubs_legacy_post_tool_use_keeps_user_entries(
    tmp_path: Path,
) -> None:
    """Legacy scrub must remove only our PostToolUse entries, not the user's."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    user_entry = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "echo user-hook"}],
    }
    _write_settings(
        settings_path,
        {"hooks": {"PostToolUse": [_LEGACY_SENTINEL_HOOK, user_entry]}},
    )

    install(tmp_path)
    after = json.loads(settings_path.read_text())
    assert after["hooks"]["PostToolUse"] == [user_entry]


# ----- uninstall ------------------------------------------------------------


@pytest.mark.integration
def test_uninstall_removes_session_start(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    result = uninstall(tmp_path)
    assert "claude/SessionStart" in result.removed


@pytest.mark.integration
def test_uninstall_also_scrubs_legacy_entries(tmp_path: Path) -> None:
    """Even if the install already happened, uninstall removes legacy stragglers."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {"hooks": {"PostToolUse": [_LEGACY_SENTINEL_HOOK]}},
    )
    target = tmp_path / ".git" / "hooks" / "post-commit"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_LEGACY_GIT_HOOK_BODY, encoding="utf-8")

    result = uninstall(tmp_path)
    assert "claude/PostToolUse" in result.removed
    assert "git/post-commit" in result.removed


@pytest.mark.integration
def test_uninstall_leaves_user_session_start_hooks(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "echo user"}],
                    }
                ]
            }
        },
    )
    install(tmp_path)
    uninstall(tmp_path)
    after = json.loads(settings_path.read_text())
    remaining = after.get("hooks", {}).get("SessionStart", [])
    assert len(remaining) == 1
    assert remaining[0]["hooks"][0]["command"] == "echo user"


@pytest.mark.integration
def test_uninstall_idempotent_when_nothing_present(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = uninstall(tmp_path)
    assert result.removed == ()
    assert len(result.skipped) > 0


@pytest.mark.integration
def test_uninstall_preserves_malformed_settings(tmp_path: Path) -> None:
    """Uninstall must not clobber a malformed settings.json either."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    broken = '{"permissions": {"allow": ["Bash"]}, OOPS not valid json'
    settings_path.write_text(broken, encoding="utf-8")

    result = uninstall(tmp_path)

    assert settings_path.read_text(encoding="utf-8") == broken
    assert any(name == "claude/settings.json" for name, _ in result.errors)


# ----- status ---------------------------------------------------------------


@pytest.mark.integration
def test_status_false_when_absent(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    s = status(tmp_path)
    assert s == HookStatus(claude_session_start=False, claude_stop=False, claude_pre_compact=False)
    assert not s.all_installed


@pytest.mark.integration
def test_status_true_after_install(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    s = status(tmp_path)
    assert s.all_installed
    assert s.claude_session_start


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
    assert "claude/SessionStart" in out

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
    """`dummyindex ingest` should install the SessionStart hook by default."""
    import shutil

    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "auto_hook_ingest"
    shutil.copytree(fixture, target)
    _init_git_repo(target)

    monkeypatch.chdir(target)
    assert dispatch(["init"]) == 0

    s = status(target)
    assert s.all_installed, "ingest should install the SessionStart drift hook"


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
    assert not s.claude_session_start


def test_install_writes_memory_session_start_command(tmp_path):
    import json

    from dummyindex.context.hooks import install

    install(tmp_path)
    settings = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    commands = [
        h["command"]
        for entry in settings["hooks"]["SessionStart"]
        for h in entry["hooks"]
    ]
    assert any("plan-update" in c for c in commands)
    assert any("memory session-start" in c for c in commands)


@pytest.mark.integration
def test_install_writes_stop_and_precompact_hooks(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = install(tmp_path)
    assert set(result.installed) == {
        "claude/SessionStart",
        "claude/Stop",
        "claude/PreCompact",
    }
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    stop_cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    pre_cmd = settings["hooks"]["PreCompact"][0]["hooks"][0]["command"]
    assert "memory nudge" in stop_cmd
    assert "DUMMYINDEX_AUTO_REFRESH" in stop_cmd
    assert "memory breadcrumb" in pre_cmd


@pytest.mark.integration
def test_status_true_after_install_all_three(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    s = status(tmp_path)
    assert s.claude_session_start and s.claude_stop and s.claude_pre_compact
    assert s.all_installed


@pytest.mark.integration
def test_uninstall_removes_stop_and_precompact(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    result = uninstall(tmp_path)
    assert "claude/Stop" in result.removed
    assert "claude/PreCompact" in result.removed


@pytest.mark.integration
def test_cli_hooks_status_lists_all_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    dispatch(["hooks", "install"])
    capsys.readouterr()
    assert dispatch(["hooks", "status"]) == 0
    out = capsys.readouterr().out
    assert "claude/SessionStart" in out
    assert "claude/Stop" in out
    assert "claude/PreCompact" in out


# ----- Stop gate + global scope (v0.23.0) -----------------------------------

from dummyindex.context import hooks as _H


def test_stop_entry_has_nudge_and_gate(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _H.install(tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    stop = settings["hooks"]["Stop"]
    assert len(stop) == 1  # single entry...
    cmds = [h["command"] for h in stop[0]["hooks"]]
    assert any("memory nudge" in c for c in cmds)
    assert any("reconcile-gate" in c for c in cmds)  # ...two commands


def test_install_idempotent_with_gate(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _H.install(tmp_path)
    _H.install(tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["Stop"]) == 1
    assert len(settings["hooks"]["Stop"][0]["hooks"]) == 2


def test_global_install_targets_home_and_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _H.install(tmp_path, scope="global")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    cmds = [
        h["command"]
        for e in settings["hooks"]["SessionStart"]
        for h in e["hooks"]
    ]
    assert any("hooks defer-check" in c for c in cmds)


def test_global_bodies_guarded_local_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _init_git_repo(tmp_path)
    _H.install(tmp_path, scope="local")
    local = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    lcmds = [h["command"] for e in local["hooks"]["Stop"] for h in e["hooks"]]
    assert not any("defer-check" in c for c in lcmds)


def test_local_install_present_detects_sentinel(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    assert _H.local_install_present(tmp_path) is False
    _H.install(tmp_path, scope="local")
    assert _H.local_install_present(tmp_path) is True


def test_global_uninstall_scrubs_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _H.install(tmp_path, scope="global")
    _H.uninstall(tmp_path, scope="global")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert "hooks" not in settings or not settings["hooks"]


def test_global_status_independent_of_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _init_git_repo(tmp_path)
    _H.install(tmp_path, scope="local")
    assert _H.status(tmp_path, scope="local").all_installed is True
    assert _H.status(tmp_path, scope="global").all_installed is False
