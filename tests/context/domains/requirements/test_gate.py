"""Hard gate: block/pass decisions, bypass handling and fail-open paths."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dummyindex.context.domains.requirements import (
    PluginRequirement,
    RequirementKind,
    RequirementRow,
    Requirements,
    RequirementStatus,
    gate_decision,
    read_bypass,
    run_gate,
    write_bypass,
    write_ok_marker,
    write_requirements,
)
from dummyindex.context.domains.requirements import gate as gate_mod
from dummyindex.context.domains.requirements.constants import (
    BYPASS_ENV,
    BYPASS_REL,
    CONFIG_TOML_REL,
    OK_MARKER_REL,
)

PLUGIN = "superpowers@claude-plugins-official"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
_S = RequirementStatus


def _row(status: RequirementStatus, name: str = "x", reason: str = "", fix: str = ""):
    return RequirementRow(
        kind=RequirementKind.PLUGIN, name=name, status=status, reason=reason, fix=fix
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".context").mkdir(parents=True)
    return root


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    path = tmp_path / "claude-config"
    path.mkdir()
    return path


def _config(project: Path, plugins: tuple[PluginRequirement, ...] = ()) -> None:
    write_requirements(project / CONFIG_TOML_REL, Requirements(plugins=plugins))


def _run(project: Path, config_dir: Path, stdin: str, env=None) -> str:
    return run_gate(
        project,
        stdin,
        claude_config_dir=config_dir,
        family_stamp="0.39.0",
        cli_version="0.39.0",
        env=env or {},
        now=NOW,
    )


def _prompt(text: str) -> str:
    return json.dumps({"prompt": text})


def _unmet_project(project: Path, config_dir: Path) -> None:
    # Plugin not enabled anywhere: a proven missing row.
    _config(project, (PluginRequirement(id=PLUGIN),))


@pytest.mark.unit
def test_unmet_blocks_with_fix_and_bypass_hint(project, config_dir):
    _unmet_project(project, config_dir)
    out = json.loads(_run(project, config_dir, _prompt("implement the thing")))
    assert out["decision"] == "block"
    reason = out["reason"]
    assert PLUGIN in reason
    assert f"/plugin install {PLUGIN}" in reason
    assert "dummyindex context requirements sync" in reason
    assert "dummyindex context requirements bypass --hours N" in reason
    assert BYPASS_ENV in reason


@pytest.mark.unit
def test_met_prints_nothing_and_writes_ok_marker(project, config_dir):
    _config(project)
    assert _run(project, config_dir, _prompt("hello")) == ""
    assert (project / OK_MARKER_REL).is_file()


@pytest.mark.unit
def test_no_config_prints_nothing(project, config_dir):
    assert _run(project, config_dir, _prompt("hello")) == ""
    assert not (project / OK_MARKER_REL).exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    "prompt",
    [
        "/dummyindex-update",
        f"/plugin install {PLUGIN}",
        "/clear",
        "  /exit",
        "/dummyindex",
    ],
)
def test_exempt_prompts_pass_without_output(project, config_dir, prompt):
    _unmet_project(project, config_dir)
    assert _run(project, config_dir, _prompt(prompt)) == ""


@pytest.mark.unit
def test_malformed_stdin_is_gated_like_a_normal_prompt(project, config_dir):
    _unmet_project(project, config_dir)
    out = json.loads(_run(project, config_dir, "not json at all"))
    assert out["decision"] == "block"


@pytest.mark.unit
def test_internal_error_passes_with_warning(project, config_dir, monkeypatch):
    _unmet_project(project, config_dir)

    def boom(*_args, **_kwargs):
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(gate_mod, "check_requirements", boom)
    out = json.loads(_run(project, config_dir, _prompt("hello")))
    assert "decision" not in out
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "gate error" in text and "registry exploded" in text


@pytest.mark.unit
def test_unknown_row_passes_with_warning(project, config_dir):
    _config(project, (PluginRequirement(id=PLUGIN),))
    _enable = config_dir / "settings.json"
    _enable.write_text(json.dumps({"enabledPlugins": {PLUGIN: True}}), encoding="utf-8")
    registry = config_dir / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True)
    registry.write_text("{broken", encoding="utf-8")
    out = json.loads(_run(project, config_dir, _prompt("hello")))
    assert "decision" not in out
    assert "not verified" in out["hookSpecificOutput"]["additionalContext"]
    assert not (project / OK_MARKER_REL).exists()


@pytest.mark.unit
def test_invalid_config_passes_with_warning(project, config_dir):
    (project / CONFIG_TOML_REL).write_text("schema_version = 2\n", encoding="utf-8")
    out = json.loads(_run(project, config_dir, _prompt("hello")))
    assert "decision" not in out
    assert "config.toml invalid" in out["hookSpecificOutput"]["additionalContext"]


@pytest.mark.unit
def test_valid_bypass_file_passes_with_warning(project, config_dir):
    _unmet_project(project, config_dir)
    write_bypass(project, 2, now=NOW)
    out = json.loads(_run(project, config_dir, _prompt("hello")))
    assert "decision" not in out
    assert "bypass" in out["hookSpecificOutput"]["additionalContext"]


@pytest.mark.unit
def test_bypass_env_var_passes_with_warning(project, config_dir):
    _unmet_project(project, config_dir)
    out = json.loads(_run(project, config_dir, _prompt("hello"), env={BYPASS_ENV: "1"}))
    assert "decision" not in out
    assert "bypass" in out["hookSpecificOutput"]["additionalContext"]


@pytest.mark.unit
def test_expired_bypass_file_is_ignored(project, config_dir):
    _unmet_project(project, config_dir)
    write_bypass(project, 1, now=NOW - timedelta(hours=5))
    out = json.loads(_run(project, config_dir, _prompt("hello")))
    assert out["decision"] == "block"


@pytest.mark.unit
def test_bypass_env_other_than_one_is_ignored(project, config_dir):
    _unmet_project(project, config_dir)
    out = json.loads(_run(project, config_dir, _prompt("hello"), env={BYPASS_ENV: "0"}))
    assert out["decision"] == "block"


@pytest.mark.unit
def test_gate_decision_blocks_only_on_missing_or_mismatch():
    rows = (_row(_S.VERSION_MISMATCH, "a"), _row(_S.SATISFIED, "b"))
    decision = gate_decision(rows, prompt="hi", bypass=False)
    assert decision.block is True
    assert "a" in decision.reason


@pytest.mark.unit
def test_gate_decision_soft_rows_warn_not_block():
    rows = (_row(_S.UNKNOWN, "a"), _row(_S.INVALID, "b"))
    decision = gate_decision(rows, prompt="hi", bypass=False)
    assert decision.block is False
    assert decision.warning


@pytest.mark.unit
def test_gate_decision_exempt_prompt_has_no_warning_even_when_unmet():
    rows = (_row(_S.MISSING, "a"),)
    decision = gate_decision(rows, prompt="  /plugin install x", bypass=True)
    assert decision.block is False
    assert decision.warning is None


@pytest.mark.unit
def test_read_bypass_bad_file_is_false(project):
    path = project / BYPASS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert read_bypass(project, env={}, now=NOW) is False


@pytest.mark.unit
def test_read_bypass_naive_expiry_is_false(project):
    path = project / BYPASS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"expires": "2099-01-01T00:00:00"}), encoding="utf-8")
    assert read_bypass(project, env={}, now=NOW) is False


@pytest.mark.unit
def test_read_bypass_env_one_is_true(project):
    assert read_bypass(project, env={BYPASS_ENV: "1"}, now=NOW) is True


@pytest.mark.unit
@pytest.mark.parametrize("hours", [1, 24])
def test_write_bypass_accepts_bounds(project, hours):
    path = write_bypass(project, hours, now=NOW)
    assert path == project / BYPASS_REL
    assert read_bypass(project, env={}, now=NOW) is True


@pytest.mark.unit
@pytest.mark.parametrize("hours", [0, 25, -1, True])
def test_write_bypass_rejects_out_of_range(project, hours):
    with pytest.raises(ValueError):
        write_bypass(project, hours, now=NOW)


@pytest.mark.unit
def test_write_ok_marker_creates_file(project):
    write_ok_marker(project)
    assert (project / OK_MARKER_REL).is_file()


@pytest.mark.unit
def test_ok_marker_write_failure_is_silent(project, config_dir, monkeypatch):
    _config(project)

    def read_only(_project_root):
        raise PermissionError("cache is read-only")

    monkeypatch.setattr(gate_mod, "write_ok_marker", read_only)
    assert _run(project, config_dir, _prompt("hello")) == ""
