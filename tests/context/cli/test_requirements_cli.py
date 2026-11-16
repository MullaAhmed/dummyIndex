"""`dummyindex context requirements check|sync|gate|bypass` — the wired CLI verbs.

Drives ``dispatch(["requirements", ...])`` on a ``tmp_path`` project. The Claude
config dir comes from ``CLAUDE_CONFIG_DIR`` pointed at a fixture; the family stamp
and CLI version are patched, so nothing reads the real ``~/.claude`` or shells out to
``claude``/``dummyindex``. The sync runner is always a fake.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from dummyindex.context.cli import dispatch
from dummyindex.context.cli import requirements as cli_requirements
from dummyindex.context.default_plugins import RunResult, WiredEntry, WiredKind
from dummyindex.context.domains.requirements import (
    PluginRequirement,
    Requirements,
    SyncReport,
    write_requirements,
)
from dummyindex.context.domains.requirements.constants import (
    BYPASS_REL,
    CONFIG_TOML_REL,
)

pytestmark = pytest.mark.unit

PLUGIN = "superpowers@claude-plugins-official"
VERSION = "0.39.0"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".context").mkdir(parents=True)
    return root


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "claude-config"
    path.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(path))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    return path


@pytest.fixture(autouse=True)
def _isolated_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the version and stamp; never scan the real home for skill copies."""
    monkeypatch.setattr(
        "dummyindex.context.domains.config.current_dummyindex_version",
        lambda: VERSION,
    )
    monkeypatch.setattr(
        "dummyindex.context.cli.check._read_skill_stamps",
        lambda _root: (("User Claude skill", VERSION),),
    )


def _write_config(project: Path, req: Requirements) -> None:
    write_requirements(project / CONFIG_TOML_REL, req)


def _enable_plugin(config_dir: Path) -> None:
    (config_dir / "settings.json").write_text(
        json.dumps({"enabledPlugins": {PLUGIN: True}}), encoding="utf-8"
    )
    registry = config_dir / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    record = [{"scope": "user", "installPath": "/x", "version": "7.1.0"}]
    registry.write_text(
        json.dumps({"version": 2, "plugins": {PLUGIN: record}}), encoding="utf-8"
    )


# --- check


def test_check_satisfied_exits_zero(project: Path, config_dir: Path, capsys) -> None:
    _write_config(project, Requirements(min_version=VERSION))

    rc = dispatch(["requirements", "check", "--root", str(project)])

    assert rc == 0
    assert "satisfied" in capsys.readouterr().out


def test_check_missing_plugin_exits_three(project: Path, config_dir: Path) -> None:
    _write_config(project, Requirements(plugins=(PluginRequirement(id=PLUGIN),)))

    rc = dispatch(["requirements", "check", "--root", str(project)])

    assert rc == 3


def test_check_uses_claude_config_dir_from_env(project: Path, config_dir: Path) -> None:
    # The plugin is only enabled under CLAUDE_CONFIG_DIR, so a pass proves the env
    # var is the config dir the check reads.
    _enable_plugin(config_dir)
    _write_config(project, Requirements(plugins=(PluginRequirement(id=PLUGIN),)))

    rc = dispatch(["requirements", "check", "--root", str(project)])

    assert rc == 0


def test_check_without_config_exits_zero_with_message(
    project: Path, config_dir: Path, capsys
) -> None:
    rc = dispatch(["requirements", "check", "--root", str(project)])

    assert rc == 0
    assert "nothing to check" in capsys.readouterr().out


def test_check_json_lists_rows(project: Path, config_dir: Path, capsys) -> None:
    _write_config(project, Requirements(min_version=VERSION))

    rc = dispatch(["requirements", "check", "--root", str(project), "--json"])

    rows = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert rows[0]["kind"] == "dummyindex"
    assert rows[0]["status"] == "satisfied"


# --- sync


class _Recorder:
    def __init__(self, report: SyncReport | None = None) -> None:
        self.calls: list[dict] = []
        self.report = report or _empty_report()

    def __call__(self, project_root, requirements, **kwargs) -> SyncReport:
        self.calls.append({"project_root": project_root, **kwargs})
        return self.report


def _empty_report(**overrides) -> SyncReport:
    fields = {
        "adapters_written": (),
        "adapters_unchanged": (),
        "adapters_kept": (),
        "skill_family_ran": False,
        "installed": (),
        "skipped": (),
        "errors": (),
    }
    fields.update(overrides)
    return SyncReport(**fields)


def test_sync_local_only_never_calls_runner(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_runner(argv, cwd) -> RunResult:
        calls.append(argv)
        return RunResult(0, "", "")

    monkeypatch.setattr(
        "dummyindex.context.default_plugins.default_runner", fake_runner
    )
    _write_config(project, Requirements(plugins=(PluginRequirement(id=PLUGIN),)))

    rc = dispatch(["requirements", "sync", "--root", str(project), "--local-only"])

    assert rc == 0
    assert calls == []


def test_sync_yes_passes_approve(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(
        "dummyindex.context.domains.requirements.sync_requirements", recorder
    )
    _write_config(project, Requirements(plugins=(PluginRequirement(id=PLUGIN),)))

    rc = dispatch(["requirements", "sync", "--root", str(project), "--yes"])

    assert rc == 0
    [call] = recorder.calls
    assert call["approve"] is True
    assert call["local_only"] is False
    assert call["confirm"] is None  # pytest stdin is not a TTY
    assert call["claude_config_dir"] == config_dir


def test_sync_passes_family_stamp_read_by_check(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(
        "dummyindex.context.domains.requirements.sync_requirements", recorder
    )
    _write_config(project, Requirements(min_version=VERSION))

    rc = dispatch(["requirements", "sync", "--root", str(project)])

    assert rc == 0
    [call] = recorder.calls
    assert call["family_stamp"] == VERSION


def test_sync_prints_restart_hint_when_adapters_written(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    report = _empty_report(
        adapters_written=(".claude/agents/x.md",), installed=(PLUGIN,)
    )
    monkeypatch.setattr(
        "dummyindex.context.domains.requirements.sync_requirements",
        _Recorder(report),
    )
    _write_config(project, Requirements(min_version=VERSION))

    rc = dispatch(["requirements", "sync", "--root", str(project)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "restart Claude Code to load new agents" in out
    assert f"installed: {PLUGIN}" in out


def test_sync_errors_exit_one(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    report = _empty_report(errors=(("claude plugin install", "exit 1: boom"),))
    monkeypatch.setattr(
        "dummyindex.context.domains.requirements.sync_requirements",
        _Recorder(report),
    )
    _write_config(project, Requirements(min_version=VERSION))

    rc = dispatch(["requirements", "sync", "--root", str(project)])

    assert rc == 1
    assert "boom" in capsys.readouterr().err


# --- gate


def test_gate_without_config_prints_nothing(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "hi"}'))

    rc = dispatch(["requirements", "gate", "--root", str(project)])

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_gate_internal_error_fails_open(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("dummyindex.context.domains.requirements.run_gate", boom)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "hi"}'))
    _write_config(project, Requirements(min_version=VERSION))

    rc = dispatch(["requirements", "gate", "--root", str(project)])

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_gate_prints_domain_output(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(
        "dummyindex.context.domains.requirements.run_gate",
        lambda *_a, **_k: '{"decision": "block", "reason": "x"}',
    )
    monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "hi"}'))
    _write_config(project, Requirements(min_version=VERSION))

    rc = dispatch(["requirements", "gate", "--root", str(project)])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"


def test_root_defaults_to_claude_project_dir(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))

    rc = dispatch(["requirements", "bypass", "--hours", "2"])

    assert rc == 0
    assert (project / BYPASS_REL).is_file()


def test_explicit_root_beats_claude_project_dir(
    project: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(other))

    rc = dispatch(["requirements", "bypass", "--hours", "2", "--root", str(project)])

    assert rc == 0
    assert (project / BYPASS_REL).is_file()
    assert not (other / BYPASS_REL).exists()


# --- bypass


@pytest.mark.parametrize("hours", [1, 24])
def test_bypass_accepts_bounds(project: Path, config_dir: Path, hours: int) -> None:
    rc = dispatch(
        ["requirements", "bypass", "--hours", str(hours), "--root", str(project)]
    )

    assert rc == 0
    assert (project / BYPASS_REL).is_file()


@pytest.mark.parametrize("hours", ["0", "25", "-1", "abc"])
def test_bypass_rejects_out_of_range(
    project: Path, config_dir: Path, hours: str
) -> None:
    rc = dispatch(["requirements", "bypass", "--hours", hours, "--root", str(project)])

    assert rc == 2
    assert not (project / BYPASS_REL).exists()


def test_bypass_requires_hours(project: Path, config_dir: Path) -> None:
    rc = dispatch(["requirements", "bypass", "--root", str(project)])

    assert rc == 2


# --- unknown verb


def test_unknown_verb_exits_two(project: Path, config_dir: Path) -> None:
    rc = dispatch(["requirements", "frobnicate", "--root", str(project)])

    assert rc == 2


# --- wired skill presence


def test_wired_skill_satisfied_by_skill_md(project: Path) -> None:
    from dummyindex.context.default_plugins import WiredClass

    skill_dir = project / ".claude" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    entry = WiredEntry(kind=WiredKind.SKILL, target="demo")

    assert cli_requirements.classify_wired(entry, root=project) is WiredClass.SATISFIED


def test_wired_skill_needs_user_without_skill_md(project: Path) -> None:
    from dummyindex.context.default_plugins import WiredClass

    (project / ".agents" / "skills" / "demo").mkdir(parents=True)  # no SKILL.md
    entry = WiredEntry(kind=WiredKind.SKILL, target="demo")

    assert cli_requirements.classify_wired(entry, root=project) is WiredClass.NEEDS_USER


def test_wired_skill_found_under_agents_dir(project: Path) -> None:
    from dummyindex.context.default_plugins import WiredClass

    skill_dir = project / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    entry = WiredEntry(kind=WiredKind.SKILL, target="demo")

    assert cli_requirements.classify_wired(entry, root=project) is WiredClass.SATISFIED


def test_wired_plugin_satisfied_by_project_settings(project: Path) -> None:
    from dummyindex.context.default_plugins import WiredClass

    settings = project / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {PLUGIN: True}}), encoding="utf-8"
    )
    entry = WiredEntry(kind=WiredKind.PLUGIN, target=PLUGIN)

    assert cli_requirements.classify_wired(entry, root=project) is WiredClass.SATISFIED


# --- polish: invalid config row, confirm prompt, kept adapters


def test_check_invalid_config_prints_invalid_row_and_exits_zero(
    project: Path, config_dir: Path, capsys
) -> None:
    (project / CONFIG_TOML_REL).write_text("[[[ not toml\n", encoding="utf-8")

    rc = dispatch(["requirements", "check", "--root", str(project)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "invalid" in out
    assert "config.toml" in out


def test_check_invalid_config_json_has_invalid_status(
    project: Path, config_dir: Path, capsys
) -> None:
    (project / CONFIG_TOML_REL).write_text("[[[ not toml\n", encoding="utf-8")

    rc = dispatch(["requirements", "check", "--root", str(project), "--json"])

    [row] = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert row["status"] == "invalid"


def test_confirm_passes_question_through_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or "y")

    assert cli_requirements._confirm("Install untrusted plugin x [y/N]") is True
    assert asked == ["Install untrusted plugin x [y/N]"]


@pytest.mark.parametrize("failure", [EOFError, KeyboardInterrupt])
def test_confirm_reads_interrupt_as_no(
    monkeypatch: pytest.MonkeyPatch, failure: type[BaseException]
) -> None:
    def interrupted(prompt: str = "") -> str:
        raise failure

    monkeypatch.setattr("builtins.input", interrupted)

    assert cli_requirements._confirm("Install untrusted plugin x [y/N]") is False


def test_sync_prints_kept_adapters(
    project: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    report = _empty_report(adapters_kept=(".claude/agents/mine.md",))
    monkeypatch.setattr(
        "dummyindex.context.domains.requirements.sync_requirements",
        _Recorder(report),
    )
    _write_config(project, Requirements(min_version=VERSION))

    rc = dispatch(["requirements", "sync", "--root", str(project)])

    assert rc == 0
    assert "kept: .claude/agents/mine.md" in capsys.readouterr().out
