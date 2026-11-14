"""Seeding a first ``config.toml`` from the wired set."""

from __future__ import annotations

import pytest

from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    WiredEntry,
    WiredKind,
    default_wired,
)
from dummyindex.context.domains.requirements import seed_requirements


def _plugin(target: str, version: str | None = None) -> WiredEntry:
    return WiredEntry(kind=WiredKind.PLUGIN, target=target, version=version)


def _family() -> set[str]:
    req = seed_requirements(
        (), default_plugins_enabled=True, cli_version="0.39.0", claude_wired=False
    )
    return {s.name for s in req.skills}


@pytest.mark.unit
def test_four_wired_plugins_and_skill_family_are_seeded():
    wired = (
        _plugin("a@one", "7.0.0"),
        _plugin("b@two"),
        _plugin("c@three", "not-a-version"),
        _plugin("d@four", "1.2.3"),
    )
    req = seed_requirements(
        wired, default_plugins_enabled=True, cli_version="0.39.0", claude_wired=True
    )
    assert [p.id for p in req.plugins] == ["a@one", "b@two", "c@three", "d@four"]
    assert [p.version for p in req.plugins] == [">=7.0.0", None, None, ">=1.2.3"]
    assert "dummyindex-plan" in _family()
    assert all(s.from_ == "dummyindex" for s in req.skills)
    assert {s.name for s in req.skills} == _family()
    assert req.min_version == "0.39.0"
    assert req.require_native_adapters is True


@pytest.mark.unit
def test_defaults_are_left_out_when_default_plugins_disabled():
    defaults = [p.target for p in DEFAULT_PLUGINS]
    wired = (*default_wired(), _plugin("mine@custom"))
    req = seed_requirements(
        wired, default_plugins_enabled=False, cli_version="0.39.0", claude_wired=False
    )
    assert [p.id for p in req.plugins] == ["mine@custom"]
    assert not set(defaults) & {p.id for p in req.plugins}


@pytest.mark.unit
def test_defaults_are_kept_when_default_plugins_enabled():
    req = seed_requirements(
        default_wired(),
        default_plugins_enabled=True,
        cli_version="0.39.0",
        claude_wired=False,
    )
    assert {p.id for p in req.plugins} == {p.target for p in DEFAULT_PLUGINS}


@pytest.mark.unit
@pytest.mark.parametrize("version", ["0.39.0.dev1", "0.39.0b1", "0.39.0rc1", "unknown"])
def test_non_release_cli_version_omits_min_version(version):
    req = seed_requirements(
        (), default_plugins_enabled=True, cli_version=version, claude_wired=False
    )
    assert req.min_version is None


@pytest.mark.unit
def test_claude_wiring_flag_drives_native_adapters():
    req = seed_requirements(
        (), default_plugins_enabled=True, cli_version="0.39.0", claude_wired=False
    )
    assert req.require_native_adapters is False
