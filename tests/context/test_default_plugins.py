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
