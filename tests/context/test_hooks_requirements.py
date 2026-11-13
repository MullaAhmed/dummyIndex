"""Requirements gate/upgrade hooks: install round-trip and native-shell execution.

Shell bodies run through the native POSIX shell with a restricted PATH; a fake
``dummyindex`` script on ``./bin`` records calls so the tests can tell whether the
CLI was spawned.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.claude_settings import load_settings
from dummyindex.context.hooks import install, uninstall
from dummyindex.context.hooks_requirements import (
    REQUIREMENTS_SENTINEL,
    install_requirements_hooks,
    uninstall_requirements_hooks,
)

_CLI_VERSION = "0.39.0"
_OLD_STAMP = "0.30.0"
_OLD_MTIME = 1_000_000_000  # well in the past


@pytest.fixture
def native_sh() -> str:
    """A native POSIX shell, including Git Bash."""
    shell = shutil.which("sh")
    if shell:
        return shell
    git = shutil.which("git")
    if git:
        bash = Path(git).parent.parent / "bin" / "bash.exe"
        if bash.is_file():
            return str(bash)
    pytest.skip("native POSIX shell unavailable")


def _commands(settings_path: Path, event: str) -> list[str]:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    return [
        h["command"]
        for entry in settings["hooks"][event]
        for h in entry["hooks"]
        if REQUIREMENTS_SENTINEL in h["command"]
    ]


def _gate_command(settings_path: Path) -> str:
    (command,) = _commands(settings_path, "UserPromptSubmit")
    return command


def _upgrade_command(settings_path: Path) -> str:
    (command,) = _commands(settings_path, "SessionStart")
    return command


def _fake_cli(bin_dir: Path, log: Path) -> None:
    """A `dummyindex` that appends its argv to ``log`` when called."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / "dummyindex"
    exe.write_text(
        f'#!/bin/sh\necho "$@" >> "{log.as_posix()}"\n',
        encoding="utf-8",
        newline="",
    )
    exe.chmod(0o755)


def _run(
    native_sh: str,
    command: str,
    cwd: Path,
    *,
    path: str,
    stdin: str = "{}\n",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": path,
        "HOME": cwd.joinpath("home").as_posix(),
        "CLAUDE_CONFIG_DIR": cwd.joinpath("claude-config").as_posix(),
        "CLAUDE_PROJECT_DIR": cwd.as_posix(),
        **(extra_env or {}),
    }
    return subprocess.run(
        [native_sh, "-c", command],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        cwd=cwd,
        check=False,
        encoding="utf-8",
    )


def _set_mtime(path: Path, seconds: int) -> None:
    os.utime(path, (seconds, seconds))


# --- install / uninstall


@pytest.mark.unit
def test_install_writes_gate_and_upgrade_once_and_is_idempotent(
    tmp_path: Path,
) -> None:
    settings = tmp_path / "settings.json"
    first = install_requirements_hooks(settings, cli_version=_CLI_VERSION)
    assert first == ["claude/UserPromptSubmit", "claude/SessionStart"]

    gate = json.loads(settings.read_text())["hooks"]["UserPromptSubmit"][0]
    assert gate["hooks"][0]["timeout"] == 20
    assert "matcher" not in gate

    before = settings.read_bytes()
    second = install_requirements_hooks(settings, cli_version=_CLI_VERSION)
    assert second == []
    assert settings.read_bytes() == before
    assert len(_commands(settings, "UserPromptSubmit")) == 1
    assert len(_commands(settings, "SessionStart")) == 1


@pytest.mark.unit
def test_install_never_uses_managed_sentinels(tmp_path: Path) -> None:
    """Old scrub/uninstall code matches on the managed sentinels; these must not."""
    settings = tmp_path / "settings.json"
    install_requirements_hooks(settings, cli_version=_CLI_VERSION, global_scope=True)
    text = settings.read_text(encoding="utf-8")
    assert "DUMMYINDEX_AUTO_REFRESH" not in text
    assert "DUMMYINDEX_HOOKS" not in text


@pytest.mark.unit
def test_uninstall_round_trip_keeps_user_hooks(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    user = {"hooks": [{"type": "command", "command": "echo user"}]}
    settings.write_text(
        json.dumps({"hooks": {"SessionStart": [user]}, "env": {"A": "1"}}),
        encoding="utf-8",
    )
    install_requirements_hooks(settings, cli_version=_CLI_VERSION)

    removed = uninstall_requirements_hooks(settings)
    assert sorted(removed) == ["claude/SessionStart", "claude/UserPromptSubmit"]
    data = load_settings(settings)
    assert data == {"hooks": {"SessionStart": [user]}, "env": {"A": "1"}}
    assert uninstall_requirements_hooks(settings) == []


@pytest.mark.unit
def test_uninstall_missing_file_is_noop(tmp_path: Path) -> None:
    assert uninstall_requirements_hooks(tmp_path / "absent.json") == []


# --- gate body (local)


@pytest.mark.integration
def test_gate_without_config_toml_exits_silently(
    tmp_path: Path, native_sh: str
) -> None:
    settings = tmp_path / "settings.json"
    install_requirements_hooks(settings, cli_version=_CLI_VERSION)
    result = _run(native_sh, _gate_command(settings), tmp_path, path="/usr/bin:/bin")
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.integration
def test_gate_without_cli_blocks_with_install_command(
    tmp_path: Path, native_sh: str
) -> None:
    (tmp_path / ".context").mkdir()
    (tmp_path / ".context" / "config.toml").write_text(
        "schema_version = 1\n", encoding="utf-8"
    )
    settings = tmp_path / "settings.json"
    install_requirements_hooks(settings, cli_version=_CLI_VERSION)
    result = _run(native_sh, _gate_command(settings), tmp_path, path="/usr/bin:/bin")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert "pip install --user dummyindex" in payload["reason"]
    assert "uv tool install dummyindex" in payload["reason"]


@pytest.mark.integration
def test_gate_fails_open_when_cli_exits_nonzero(tmp_path: Path, native_sh: str) -> None:
    """A non-zero CLI exit (e.g. missing verb) must not block the prompt."""
    (tmp_path / ".context").mkdir()
    (tmp_path / ".context" / "config.toml").write_text(
        "schema_version = 1\n", encoding="utf-8"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "dummyindex"
    exe.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8", newline="")
    exe.chmod(0o755)
    settings = tmp_path / "settings.json"
    install_requirements_hooks(settings, cli_version=_CLI_VERSION)

    result = _run(
        native_sh,
        _gate_command(settings),
        tmp_path,
        path="./bin:/usr/bin:/bin",
    )
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.integration
def test_install_reports_each_event_once(tmp_path: Path) -> None:
    """Managed and requirements hooks both touch UserPromptSubmit/SessionStart."""
    installed = install(tmp_path).installed
    assert len(installed) == len(set(installed))
    assert installed.count("claude/UserPromptSubmit") == 1
    assert installed.count("claude/SessionStart") == 1
    removed = uninstall(tmp_path).removed
    assert len(removed) == len(set(removed))


@pytest.mark.integration
def test_gate_with_fresh_ok_marker_does_not_spawn_cli(
    tmp_path: Path, native_sh: str
) -> None:
    ctx = tmp_path / ".context"
    (ctx / "cache").mkdir(parents=True)
    config = ctx / "config.toml"
    config.write_text("schema_version = 1\n", encoding="utf-8")
    _set_mtime(config, _OLD_MTIME)
    marker = ctx / "cache" / "requirements.ok"
    marker.write_text("ok\n", encoding="utf-8")
    log = tmp_path / "cli.log"
    _fake_cli(tmp_path / "bin", log)
    settings = tmp_path / "settings.json"
    install_requirements_hooks(settings, cli_version=_CLI_VERSION)
    command = _gate_command(settings)

    fresh = _run(native_sh, command, tmp_path, path="./bin:/usr/bin:/bin")
    assert fresh.returncode == 0
    assert not log.exists()

    # Control: a config.toml newer than the marker makes the gate call the CLI.
    _set_mtime(marker, _OLD_MTIME)
    _set_mtime(config, _OLD_MTIME + 100)
    stale = _run(native_sh, command, tmp_path, path="./bin:/usr/bin:/bin")
    assert stale.returncode == 0
    assert log.read_text(encoding="utf-8").strip() == "context requirements gate"


# --- global variants


@pytest.mark.integration
def test_global_gate_runs_despite_old_local_hooks(
    tmp_path: Path, native_sh: str
) -> None:
    """Local hooks without the requirements sentinel must not mute the global gate."""
    (tmp_path / ".context").mkdir()
    (tmp_path / ".context" / "config.toml").write_text(
        "schema_version = 1\n", encoding="utf-8"
    )
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [{"hooks": [{"type": "command", "command": "echo old"}]}]
                }
            }
        ),
        encoding="utf-8",
    )
    log = tmp_path / "cli.log"
    _fake_cli(tmp_path / "bin", log)
    global_settings = tmp_path / "global" / "settings.json"
    install_requirements_hooks(
        global_settings, cli_version=_CLI_VERSION, global_scope=True
    )

    result = _run(
        native_sh,
        _gate_command(global_settings),
        tmp_path,
        path="./bin:/usr/bin:/bin",
    )
    assert result.returncode == 0
    assert log.exists()


@pytest.mark.integration
def test_global_gate_defers_to_project_requirements_sentinel(
    tmp_path: Path, native_sh: str
) -> None:
    (tmp_path / ".context").mkdir()
    (tmp_path / ".context" / "config.toml").write_text(
        "schema_version = 1\n", encoding="utf-8"
    )
    local = tmp_path / ".claude" / "settings.json"
    install_requirements_hooks(local, cli_version=_CLI_VERSION)
    log = tmp_path / "cli.log"
    _fake_cli(tmp_path / "bin", log)
    global_settings = tmp_path / "global" / "settings.json"
    install_requirements_hooks(
        global_settings, cli_version=_CLI_VERSION, global_scope=True
    )

    result = _run(
        native_sh,
        _gate_command(global_settings),
        tmp_path,
        path="./bin:/usr/bin:/bin",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert not log.exists()


@pytest.mark.integration
def test_global_upgrade_runs_on_stale_stamp_without_config_toml(
    tmp_path: Path, native_sh: str
) -> None:
    (tmp_path / ".context").mkdir()
    (tmp_path / ".context" / "meta.json").write_text(
        json.dumps({"dummyindex_version": _OLD_STAMP}), encoding="utf-8"
    )
    log = tmp_path / "cli.log"
    _fake_cli(tmp_path / "bin", log)
    global_settings = tmp_path / "global" / "settings.json"
    install_requirements_hooks(
        global_settings, cli_version=_CLI_VERSION, global_scope=True
    )

    result = _run(
        native_sh,
        _upgrade_command(global_settings),
        tmp_path,
        path="./bin:/usr/bin:/bin",
    )
    assert result.returncode == 0
    calls = log.read_text(encoding="utf-8").splitlines()
    assert "context upgrade --if-stale --root " + tmp_path.as_posix() in calls
    assert (
        "context requirements sync --local-only --root " + tmp_path.as_posix() in calls
    )


@pytest.mark.integration
def test_upgrade_with_equal_stamp_does_not_spawn(
    tmp_path: Path, native_sh: str
) -> None:
    (tmp_path / ".context").mkdir()
    (tmp_path / ".context" / "meta.json").write_text(
        json.dumps({"dummyindex_version": _CLI_VERSION}), encoding="utf-8"
    )
    log = tmp_path / "cli.log"
    _fake_cli(tmp_path / "bin", log)
    settings = tmp_path / "settings.json"
    install_requirements_hooks(settings, cli_version=_CLI_VERSION)

    result = _run(
        native_sh,
        _upgrade_command(settings),
        tmp_path,
        path="./bin:/usr/bin:/bin",
    )
    assert result.returncode == 0
    assert not log.exists()
