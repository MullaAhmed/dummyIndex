"""Tests for dummyindex's default-plugin wiring (context.default_plugins)."""

from __future__ import annotations

import pytest

from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    DefaultPlugin,
    PluginWireResult,
    describe_wire_result,
    resolve_enabled,
)


@pytest.mark.unit
def test_default_plugins_contains_superpowers_official() -> None:
    assert DefaultPlugin("superpowers", "claude-plugins-official") in DEFAULT_PLUGINS
    target = DefaultPlugin("superpowers", "claude-plugins-official").target
    assert target == "superpowers@claude-plugins-official"


@pytest.mark.unit
def test_resolve_enabled_flag_wins() -> None:
    assert resolve_enabled(cli_opt_out=True, config_value=True) is False
    assert resolve_enabled(cli_opt_out=True, config_value=None) is False


@pytest.mark.unit
def test_resolve_enabled_honors_config() -> None:
    assert resolve_enabled(cli_opt_out=False, config_value=False) is False
    assert resolve_enabled(cli_opt_out=False, config_value=True) is True


@pytest.mark.unit
def test_resolve_enabled_defaults_on_when_no_config() -> None:
    assert resolve_enabled(cli_opt_out=False, config_value=None) is True


@pytest.mark.unit
def test_describe_wire_result_splits_info_and_warn() -> None:
    result = PluginWireResult(
        enabled=("superpowers@claude-plugins-official",),
        already=("a@b",),
        skipped=("c@d",),
        errors=(("e@f", "boom"),),
    )
    info, warn = describe_wire_result(result)
    assert any("enabled superpowers@claude-plugins-official" in line for line in info)
    assert any("a@b already enabled" in line for line in info)
    assert any("skipped c@d" in line for line in info)
    assert any("e@f" in line and "boom" in line for line in warn)


import json
from pathlib import Path

from dummyindex.context.default_plugins import wire_default_plugins

_SUPERPOWERS = "superpowers@claude-plugins-official"


def _enabled_plugins(settings_path: Path) -> dict:
    if not settings_path.exists():
        return {}
    return json.loads(settings_path.read_text(encoding="utf-8")).get("enabledPlugins", {})


@pytest.mark.unit
def test_wire_enables_superpowers_into_fresh_settings(tmp_path: Path) -> None:
    result = wire_default_plugins(tmp_path, enabled=True)

    settings = tmp_path / ".claude" / "settings.json"
    enabled = _enabled_plugins(settings)
    assert enabled.get(_SUPERPOWERS) is True
    # Official marketplace is natively known → no extraKnownMarketplaces entry.
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "extraKnownMarketplaces" not in data
    assert result.enabled == (_SUPERPOWERS,)
    assert result.already == ()


@pytest.mark.unit
def test_wire_disabled_writes_nothing(tmp_path: Path) -> None:
    result = wire_default_plugins(tmp_path, enabled=False)

    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert result.skipped == (_SUPERPOWERS,)
    assert result.enabled == ()


@pytest.mark.unit
def test_wire_skips_when_already_true_in_project_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: True}}), encoding="utf-8"
    )
    before = settings.read_text(encoding="utf-8")

    result = wire_default_plugins(tmp_path, enabled=True)

    assert result.already == (_SUPERPOWERS,)
    assert result.enabled == ()
    assert settings.read_text(encoding="utf-8") == before  # untouched


@pytest.mark.unit
def test_wire_respects_explicit_false_in_project_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: False}}), encoding="utf-8"
    )

    result = wire_default_plugins(tmp_path, enabled=True)

    assert result.already == (_SUPERPOWERS,)
    assert _enabled_plugins(settings).get(_SUPERPOWERS) is False  # NOT force-enabled


@pytest.mark.unit
def test_wire_skips_when_present_in_settings_local(tmp_path: Path) -> None:
    local = tmp_path / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: True}}), encoding="utf-8"
    )

    result = wire_default_plugins(tmp_path, enabled=True)

    assert result.already == (_SUPERPOWERS,)
    assert not (tmp_path / ".claude" / "settings.json").exists()


@pytest.mark.unit
def test_wire_ignores_user_settings_writes_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A global (~/.claude) enable must NOT suppress the committed project entry."""
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    (fake_home / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: True}}), encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(fake_home))
    repo = tmp_path / "repo"
    repo.mkdir()

    result = wire_default_plugins(repo, enabled=True)

    assert result.enabled == (_SUPERPOWERS,)
    assert _enabled_plugins(repo / ".claude" / "settings.json").get(_SUPERPOWERS) is True


@pytest.mark.unit
def test_wire_malformed_settings_reports_error_no_raise(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json", encoding="utf-8")

    result = wire_default_plugins(tmp_path, enabled=True)

    assert result.enabled == ()
    assert result.errors and result.errors[0][0] == _SUPERPOWERS
    assert settings.read_text(encoding="utf-8") == "{not json"  # untouched


@pytest.mark.unit
def test_wire_is_idempotent(tmp_path: Path) -> None:
    first = wire_default_plugins(tmp_path, enabled=True)
    second = wire_default_plugins(tmp_path, enabled=True)

    assert first.enabled == (_SUPERPOWERS,)
    assert second.enabled == ()
    assert second.already == (_SUPERPOWERS,)
