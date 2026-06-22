"""Tests for dummyindex's default-plugin wiring (context.default_plugins)."""

from __future__ import annotations

import pytest

from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    DefaultPlugin,
    PluginWireResult,
    WiredClass,
    WiredEntry,
    WiredKind,
    classify_wired_entry,
    default_wired,
    describe_wire_result,
    resolve_enabled,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "target", "present", "expected"),
    [
        # skill entries are always needs-user (no enable primitive)
        (WiredKind.SKILL, "some-skill", False, WiredClass.NEEDS_USER),
        (WiredKind.SKILL, "some-skill", True, WiredClass.NEEDS_USER),
        # a malformed plugin target is needs-user (can't be mis-wired)
        (WiredKind.PLUGIN, "no-marketplace", False, WiredClass.NEEDS_USER),
        # a valid plugin already decided in settings is satisfied
        (WiredKind.PLUGIN, "p@m", True, WiredClass.SATISFIED),
        # a valid plugin declared but absent is acted
        (WiredKind.PLUGIN, "p@m", False, WiredClass.ACTED),
    ],
)
def test_classify_wired_entry_branches(
    kind: WiredKind, target: str, present: bool, expected: WiredClass
) -> None:
    """The one shared classify rule — pure over (entry, is_present), no I/O."""
    entry = WiredEntry(kind=kind, target=target, version=None)
    result = classify_wired_entry(entry, is_present=lambda _t: present)
    assert result is expected


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
        needs_user=(("sk", "skill entries are declared, not auto-wired"),),
        skipped=("c@d",),
        errors=(("e@f", "boom"),),
    )
    info, warn = describe_wire_result(result)
    assert any("enabled superpowers@claude-plugins-official" in line for line in info)
    assert any("a@b already enabled" in line for line in info)
    assert any("skipped c@d" in line for line in info)
    assert any("needs you: sk" in line for line in warn)
    assert any("e@f" in line and "boom" in line for line in warn)


import json
from pathlib import Path

from dummyindex.context.default_plugins import wire_default_plugins

_SUPERPOWERS = "superpowers@claude-plugins-official"


def _enabled_plugins(settings_path: Path) -> dict:
    if not settings_path.exists():
        return {}
    return json.loads(settings_path.read_text(encoding="utf-8")).get("enabledPlugins", {})


# ---------------------------------------------------------------------------
# The reconciler runs install_default_plugins on the acted path. To keep the
# wire tests off the real CLI/network we inject a fake runner that reports the
# `claude` binary as absent — install defers, never shells out. Tests that
# specifically assert the acted/needs-user install behaviour script their own.
# ---------------------------------------------------------------------------


def _claude_absent_runner(argv: list[str], cwd: Path) -> "RunResult":
    return RunResult(127, "", "claude: not found")


@pytest.mark.unit
def test_wire_enables_superpowers_into_fresh_settings(tmp_path: Path) -> None:
    result = wire_default_plugins(
        default_wired(), tmp_path, enabled=True, runner=_claude_absent_runner
    )

    settings = tmp_path / ".claude" / "settings.json"
    enabled = _enabled_plugins(settings)
    assert enabled.get(_SUPERPOWERS) is True
    # Official marketplace is natively known → no extraKnownMarketplaces entry.
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "extraKnownMarketplaces" not in data
    assert result.enabled == (_SUPERPOWERS,)  # acted
    assert result.already == ()
    assert result.needs_user == ()


@pytest.mark.unit
def test_wire_disabled_writes_nothing(tmp_path: Path) -> None:
    result = wire_default_plugins(default_wired(), tmp_path, enabled=False)

    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert result.skipped == (_SUPERPOWERS,)
    assert result.enabled == ()


@pytest.mark.unit
def test_wire_empty_wired_is_opt_out(tmp_path: Path) -> None:
    """Empty ``wired`` == opted out: wires nothing even when enabled=True."""
    result = wire_default_plugins((), tmp_path, enabled=True)

    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert result.enabled == ()
    assert result.already == ()
    assert result.needs_user == ()
    assert result.skipped == ()


@pytest.mark.unit
def test_wire_skips_when_already_true_in_project_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: True}}), encoding="utf-8"
    )
    before = settings.read_text(encoding="utf-8")

    result = wire_default_plugins(default_wired(), tmp_path, enabled=True)

    assert result.already == (_SUPERPOWERS,)  # satisfied
    assert result.enabled == ()
    assert settings.read_text(encoding="utf-8") == before  # untouched


@pytest.mark.unit
def test_wire_respects_explicit_false_in_project_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: False}}), encoding="utf-8"
    )

    result = wire_default_plugins(default_wired(), tmp_path, enabled=True)

    assert result.already == (_SUPERPOWERS,)
    assert _enabled_plugins(settings).get(_SUPERPOWERS) is False  # NOT force-enabled


@pytest.mark.unit
def test_wire_skips_when_present_in_settings_local(tmp_path: Path) -> None:
    local = tmp_path / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: True}}), encoding="utf-8"
    )

    result = wire_default_plugins(default_wired(), tmp_path, enabled=True)

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

    result = wire_default_plugins(
        default_wired(), repo, enabled=True, runner=_claude_absent_runner
    )

    assert result.enabled == (_SUPERPOWERS,)
    assert _enabled_plugins(repo / ".claude" / "settings.json").get(_SUPERPOWERS) is True


@pytest.mark.unit
def test_wire_malformed_settings_reports_error_no_raise(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json", encoding="utf-8")

    result = wire_default_plugins(default_wired(), tmp_path, enabled=True)

    assert result.enabled == ()
    assert result.errors and result.errors[0][0] == _SUPERPOWERS
    assert settings.read_text(encoding="utf-8") == "{not json"  # untouched


@pytest.mark.unit
def test_wire_is_idempotent(tmp_path: Path) -> None:
    first = wire_default_plugins(
        default_wired(), tmp_path, enabled=True, runner=_claude_absent_runner
    )
    second = wire_default_plugins(
        default_wired(), tmp_path, enabled=True, runner=_claude_absent_runner
    )

    assert first.enabled == (_SUPERPOWERS,)  # acted
    assert second.enabled == ()
    assert second.already == (_SUPERPOWERS,)  # satisfied


@pytest.mark.unit
def test_wire_skill_entry_is_needs_user(tmp_path: Path) -> None:
    """A ``kind=skill`` entry has no enable primitive → classified needs-user,
    never written into settings.json, never auto-wired."""
    wired = (WiredEntry(kind=WiredKind.SKILL, target="some-skill", version="1.2.0"),)

    result = wire_default_plugins(wired, tmp_path, enabled=True)

    assert result.needs_user and result.needs_user[0][0] == "some-skill"
    assert result.enabled == ()
    assert result.already == ()
    # Nothing materialised into settings for a skill.
    assert not (tmp_path / ".claude" / "settings.json").exists()


@pytest.mark.unit
def test_wire_install_failure_lands_in_needs_user(tmp_path: Path) -> None:
    """An absent plugin is enabled (acted) but a failed best-effort install is
    escalated to needs-user — the declaration is written, the user must finish."""

    def fn(argv: list[str], cwd: Path) -> "RunResult":
        if argv[:2] == ["claude", "--version"]:
            return RunResult(0, "1.0.0", "")
        return RunResult(1, "", "untrusted source: pass --yes")

    result = wire_default_plugins(default_wired(), tmp_path, enabled=True, runner=fn)

    # Declaration still written (acted)...
    assert result.enabled == (_SUPERPOWERS,)
    assert _enabled_plugins(tmp_path / ".claude" / "settings.json").get(
        _SUPERPOWERS
    ) is True
    # ...but the failed install escalates to needs-user, never silently dropped.
    assert result.needs_user and result.needs_user[0][0] == _SUPERPOWERS
    assert "--yes" in result.needs_user[0][1]


@pytest.mark.unit
def test_wire_never_reads_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The reconciler is non-interactive: any attempt to read stdin is a bug.
    Structured so a blocking prompt would raise rather than hang the suite."""

    def _boom() -> str:
        raise AssertionError("wire_default_plugins must never call input()")

    monkeypatch.setattr("builtins.input", _boom)

    # Mix of acted (plugin) + needs-user (skill) so every classification path runs.
    wired = (
        *default_wired(),
        WiredEntry(kind=WiredKind.SKILL, target="some-skill"),
    )
    result = wire_default_plugins(
        wired, tmp_path, enabled=True, runner=_claude_absent_runner
    )

    assert result.enabled == (_SUPERPOWERS,)
    assert any(t == "some-skill" for t, _ in result.needs_user)


# ---------------------------------------------------------------------------
# install_default_plugins: best-effort materialisation via the `claude` CLI
#
# `wire_default_plugins` only *declares* a default in settings.json; on a fresh
# laptop that declaration doesn't put the plugin's bits on disk (the marketplace
# clone + installed_plugins.json registration live under ~/.claude, per-machine
# and never shared via git). `install_default_plugins` closes that gap by
# shelling out to `claude plugin install`. It is best-effort: a missing `claude`
# binary degrades to "deferred" (Claude Code installs it on next session) and a
# failed install is reported, never raised. Runner is injected so tests never
# touch the real CLI/network.
# ---------------------------------------------------------------------------

import os  # noqa: E402
from collections.abc import Callable  # noqa: E402

from dummyindex.context.default_plugins import (  # noqa: E402
    PluginInstallResult,
    RunResult,
    _install_one,
    describe_install_result,
    install_default_plugins,
)


class _FakeRunner:
    """Records (argv, cwd) calls and returns scripted results via ``fn(argv)``."""

    def __init__(self, fn: Callable[[list[str]], RunResult]) -> None:
        self.fn = fn
        self.calls: list[tuple[tuple[str, ...], Path]] = []

    def __call__(self, argv: list[str], cwd: Path) -> RunResult:
        self.calls.append((tuple(argv), cwd))
        return self.fn(list(argv))


def _ok(_argv: list[str]) -> RunResult:
    return RunResult(0, "", "")


def _claude_absent(argv: list[str]) -> RunResult:
    # `claude --version` -> 127 (not found); nothing else should be invoked.
    return RunResult(127, "", "claude: not found")


@pytest.mark.unit
def test_install_materialises_default_via_claude(tmp_path: Path) -> None:
    runner = _FakeRunner(_ok)

    result = install_default_plugins(tmp_path, enabled=True, runner=runner)

    assert result.installed == (_SUPERPOWERS,)
    assert result.deferred == ()
    assert result.errors == ()
    # Probed availability, then installed with project scope in the repo dir.
    assert (("claude", "--version"), tmp_path) in runner.calls
    assert (
        ("claude", "plugin", "install", _SUPERPOWERS, "--scope", "project"),
        tmp_path,
    ) in runner.calls


@pytest.mark.unit
def test_install_defers_when_claude_absent(tmp_path: Path) -> None:
    runner = _FakeRunner(_claude_absent)

    result = install_default_plugins(tmp_path, enabled=True, runner=runner)

    assert result.deferred == (_SUPERPOWERS,)
    assert result.installed == ()
    assert result.errors == ()
    # Only the availability probe ran — no install attempted.
    assert all(argv[:2] != ("claude", "plugin") for argv, _ in runner.calls)


@pytest.mark.unit
def test_install_reports_error_when_install_fails_no_raise(tmp_path: Path) -> None:
    def fn(argv: list[str]) -> RunResult:
        if argv[:2] == ["claude", "--version"]:
            return RunResult(0, "1.0.0", "")
        return RunResult(1, "", "network unreachable")

    result = install_default_plugins(tmp_path, enabled=True, runner=_FakeRunner(fn))

    assert result.installed == ()
    assert result.errors and result.errors[0][0] == _SUPERPOWERS
    assert "network unreachable" in result.errors[0][1]


@pytest.mark.unit
def test_install_disabled_skips_everything(tmp_path: Path) -> None:
    runner = _FakeRunner(_ok)

    result = install_default_plugins(tmp_path, enabled=False, runner=runner)

    assert result.skipped == (_SUPERPOWERS,)
    assert result.installed == ()
    assert runner.calls == []  # never even probed for claude


@pytest.mark.unit
def test_install_one_registers_third_party_marketplace_first(tmp_path: Path) -> None:
    """A non-official default registers its marketplace before installing."""
    plugin = DefaultPlugin(
        plugin="impeccable", marketplace="impeccable", repo="pbakaus/impeccable"
    )
    runner = _FakeRunner(_ok)

    ok, err = _install_one(plugin, tmp_path, runner)

    assert ok is True and err is None
    argvs = [argv for argv, _ in runner.calls]
    assert ("claude", "plugin", "marketplace", "add", "pbakaus/impeccable",
            "--scope", "project") in argvs
    # marketplace add precedes the install
    add_i = argvs.index(
        ("claude", "plugin", "marketplace", "add", "pbakaus/impeccable",
         "--scope", "project")
    )
    inst_i = argvs.index(
        ("claude", "plugin", "install", "impeccable@impeccable", "--scope", "project")
    )
    assert add_i < inst_i


@pytest.mark.unit
def test_install_one_marketplace_add_fails_reports_error(tmp_path: Path) -> None:
    """If registering a third-party marketplace fails, install is not attempted."""
    plugin = DefaultPlugin(
        plugin="impeccable", marketplace="impeccable", repo="pbakaus/impeccable"
    )

    def fn(argv: list[str]) -> RunResult:
        if argv[:4] == ["claude", "plugin", "marketplace", "add"]:
            return RunResult(1, "", "could not resolve ref")
        return RunResult(0, "", "")

    runner = _FakeRunner(fn)
    ok, err = _install_one(plugin, tmp_path, runner)

    assert ok is False
    assert err is not None and "marketplace add failed" in err
    # install must NOT run once the marketplace add failed.
    assert all(argv[:3] != ("claude", "plugin", "install") for argv, _ in runner.calls)


@pytest.mark.unit
def test_install_one_pins_ref_in_marketplace_source(tmp_path: Path) -> None:
    """A pinned ``ref`` is composed as ``repo@ref`` in the marketplace source."""
    plugin = DefaultPlugin(
        plugin="impeccable",
        marketplace="impeccable",
        repo="pbakaus/impeccable",
        ref="skill-v3.5.0",
    )
    runner = _FakeRunner(_ok)

    ok, err = _install_one(plugin, tmp_path, runner)

    assert ok is True and err is None
    argvs = [argv for argv, _ in runner.calls]
    assert ("claude", "plugin", "marketplace", "add",
            "pbakaus/impeccable@skill-v3.5.0", "--scope", "project") in argvs


@pytest.mark.unit
def test_install_env_guard_defers_on_default_path(tmp_path: Path) -> None:
    """With the skip env set (as the suite does) and no injected runner, the
    production path defers instead of shelling out to the real CLI."""
    from dummyindex.context.default_plugins import SKIP_INSTALL_ENV

    assert os.environ.get(SKIP_INSTALL_ENV)  # set by the autouse conftest guard
    result = install_default_plugins(tmp_path, enabled=True)  # no runner injected

    assert result.deferred == (_SUPERPOWERS,)
    assert result.installed == ()


@pytest.mark.unit
def test_describe_install_result_splits_info_and_warn() -> None:
    result = PluginInstallResult(
        installed=("superpowers@claude-plugins-official",),
        deferred=("g@h",),
        errors=(("e@f", "boom"),),
    )
    info, warn = describe_install_result(result)
    assert any("installed superpowers@claude-plugins-official" in line for line in info)
    assert any("g@h" in line and "deferred" in line for line in info)
    assert any("e@f" in line and "boom" in line for line in warn)
