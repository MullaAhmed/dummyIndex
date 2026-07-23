"""Tests for the reviewed default-plugin declaration/materialization seams."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    DefaultPlugin,
    PluginInstallResult,
    PluginWireResult,
    RunResult,
    WiredClass,
    WiredEntry,
    WiredKind,
    _validate_default_plugins,
    classify_wired_entry,
    default_wired,
    describe_default_plugin_trust,
    describe_install_result,
    describe_wire_result,
    install_default_plugins,
    resolve_enabled,
    wire_default_plugins,
)

_SUPERPOWERS = "superpowers@claude-plugins-official"
_CAVEMAN = "caveman@caveman"
_ADHD = "i-have-adhd@i-have-adhd"
_TARGETS = (_SUPERPOWERS, _CAVEMAN, _ADHD)
# A SHA pin written by dummyindex <= 0.33.x — Claude Code clones marketplaces
# with `git clone --branch <ref>`, which never accepts a commit SHA, so these
# legacy declarations must be healed to unpinned, never re-written.
_LEGACY_CAVEMAN_SHA = "0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0"


def _entry(target: str) -> WiredEntry:
    return WiredEntry(kind=WiredKind.PLUGIN, target=target, version=None)


def _settings_path(root: Path, *, local: bool = False) -> Path:
    name = "settings.local.json" if local else "settings.json"
    return root / ".claude" / name


def _read_settings(root: Path, *, local: bool = False) -> dict:
    path = _settings_path(root, local=local)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_settings(root: Path, payload: dict, *, local: bool = False) -> Path:
    path = _settings_path(root, local=local)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


class _FakeRunner:
    """Record fixed argv/cwd calls and return a scripted result."""

    def __init__(self, fn: Callable[[list[str]], RunResult]) -> None:
        self.fn = fn
        self.calls: list[tuple[tuple[str, ...], Path]] = []

    def __call__(self, argv: list[str], cwd: Path) -> RunResult:
        self.calls.append((tuple(argv), cwd))
        return self.fn(list(argv))


def _ok(_argv: list[str]) -> RunResult:
    return RunResult(0, "", "")


def _declare(root: Path, wired: tuple[WiredEntry, ...] = default_wired()) -> None:
    result = wire_default_plugins(wired, root, enabled=True)
    assert result.errors == ()
    assert result.needs_user == ()


@pytest.mark.unit
def test_default_plugins_are_exact_reviewed_ordered_records() -> None:
    assert DEFAULT_PLUGINS == (
        DefaultPlugin(
            plugin="superpowers",
            marketplace="claude-plugins-official",
            surfaces=("skills",),
            runs_code=False,
        ),
        DefaultPlugin(
            plugin="caveman",
            marketplace="caveman",
            repo="JuliusBrussee/caveman",
            surfaces=(
                "skills",
                "commands",
                "SessionStart Node command hook",
                "UserPromptSubmit Node command hook",
            ),
            runs_code=True,
        ),
        DefaultPlugin(
            plugin="i-have-adhd",
            marketplace="i-have-adhd",
            repo="ayghri/i-have-adhd",
            surfaces=("skill",),
            runs_code=False,
        ),
    )
    assert tuple(plugin.target for plugin in DEFAULT_PLUGINS) == _TARGETS
    assert tuple(entry.target for entry in default_wired()) == _TARGETS
    assert len(set(_TARGETS)) == len(_TARGETS)


@pytest.mark.unit
def test_default_plugin_validation_rejects_duplicate_target() -> None:
    plugin = DefaultPlugin(
        plugin="p",
        marketplace="m",
        surfaces=("skill",),
    )
    with pytest.raises(ValueError, match="duplicate default plugin target: p@m"):
        _validate_default_plugins((plugin, plugin))


@pytest.mark.unit
def test_default_plugins_carry_no_pin() -> None:
    """Claude Code clones marketplaces with ``git clone --branch <ref>`` — a
    commit SHA is never clonable, so defaults track the latest upstream."""
    for plugin in DEFAULT_PLUGINS:
        assert not hasattr(plugin, "ref")


@pytest.mark.unit
def test_default_plugin_validation_requires_reviewed_surfaces() -> None:
    plugin = DefaultPlugin(plugin="p", marketplace="m")
    with pytest.raises(ValueError, match="has no reviewed surfaces"):
        _validate_default_plugins((plugin,))


@pytest.mark.unit
def test_trust_disclosure_is_pure_exact_and_names_reviewed_blast_radius() -> None:
    assert describe_default_plugin_trust() == (
        "default plugin trust -> caveman@caveman from "
        "JuliusBrussee/caveman (tracks latest); reviewed surfaces: skills, "
        "commands, SessionStart Node command hook, UserPromptSubmit Node command "
        "hook; runs code: yes; opt out this run with --no-default-plugins",
        "default plugin trust -> i-have-adhd@i-have-adhd from "
        "ayghri/i-have-adhd (tracks latest); reviewed surfaces: skill; runs code: "
        "no; opt out this run with --no-default-plugins",
    )
    assert describe_default_plugin_trust() == describe_default_plugin_trust()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "target", "present", "expected"),
    [
        (WiredKind.SKILL, "some-skill", False, WiredClass.NEEDS_USER),
        (WiredKind.SKILL, "some-skill", True, WiredClass.NEEDS_USER),
        (WiredKind.PLUGIN, "no-marketplace", False, WiredClass.NEEDS_USER),
        (WiredKind.PLUGIN, "p@m", True, WiredClass.SATISFIED),
        (WiredKind.PLUGIN, "p@m", False, WiredClass.ACTED),
    ],
)
def test_classify_wired_entry_branches(
    kind: WiredKind, target: str, present: bool, expected: WiredClass
) -> None:
    entry = WiredEntry(kind=kind, target=target, version=None)
    assert classify_wired_entry(entry, is_present=lambda _t: present) is expected


@pytest.mark.unit
def test_resolve_enabled_precedence() -> None:
    assert resolve_enabled(cli_opt_out=True, config_value=True) is False
    assert resolve_enabled(cli_opt_out=True, config_value=None) is False
    assert resolve_enabled(cli_opt_out=False, config_value=False) is False
    assert resolve_enabled(cli_opt_out=False, config_value=True) is True
    assert resolve_enabled(cli_opt_out=False, config_value=None) is True


@pytest.mark.unit
def test_describe_wire_result_splits_info_and_warn() -> None:
    result = PluginWireResult(
        enabled=(_SUPERPOWERS,),
        already=("a@b",),
        needs_user=(("sk", "skill entries are declared, not auto-wired"),),
        skipped=("c@d",),
        errors=(("e@f", "boom"),),
    )
    info, warn = describe_wire_result(result)
    assert any(f"enabled {_SUPERPOWERS}" in line for line in info)
    assert any("a@b already enabled" in line for line in info)
    assert any("skipped c@d" in line for line in info)
    assert any("needs you: sk" in line for line in warn)
    assert any("e@f" in line and "boom" in line for line in warn)


@pytest.mark.unit
def test_wire_declares_all_defaults_without_invoking_runner(tmp_path: Path) -> None:
    def _must_not_run(_argv: list[str], _cwd: Path) -> RunResult:
        raise AssertionError("declaration must not probe or invoke Claude")

    result = wire_default_plugins(
        default_wired(), tmp_path, enabled=True, runner=_must_not_run
    )

    assert result == PluginWireResult(enabled=_TARGETS)
    assert _read_settings(tmp_path) == {
        "extraKnownMarketplaces": {
            "caveman": {
                "source": {
                    "source": "github",
                    "repo": "JuliusBrussee/caveman",
                }
            },
            "i-have-adhd": {
                "source": {
                    "source": "github",
                    "repo": "ayghri/i-have-adhd",
                }
            },
        },
        "enabledPlugins": dict.fromkeys(_TARGETS, True),
    }


@pytest.mark.unit
def test_wire_identical_marketplace_is_not_redeclared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = {
        "extraKnownMarketplaces": {
            "caveman": {
                "source": {
                    "source": "github",
                    "repo": "JuliusBrussee/caveman",
                }
            }
        }
    }
    _write_settings(tmp_path, settings)

    def _must_not_add(*_args: object, **_kwargs: object) -> bool:
        raise AssertionError("an identical declaration must be a no-op")

    monkeypatch.setattr(
        "dummyindex.context.default_plugins.add_marketplace", _must_not_add
    )
    result = wire_default_plugins((_entry(_CAVEMAN),), tmp_path)

    assert result.enabled == (_CAVEMAN,)
    assert (
        _read_settings(tmp_path)["extraKnownMarketplaces"]
        == settings["extraKnownMarketplaces"]
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        # A branch/tag ref IS clonable by Claude Code — a deliberate user
        # choice, never healed.
        {"source": "github", "repo": "JuliusBrussee/caveman", "ref": "v2.4.0"},
        # An extra key means the declaration is not the known legacy shape.
        {
            "source": "github",
            "repo": "JuliusBrussee/caveman",
            "ref": _LEGACY_CAVEMAN_SHA,
            "sparse": [".claude-plugin"],
        },
    ],
    ids=("tag-ref", "extra-key"),
)
def test_wire_same_repo_custom_declaration_is_conflict_and_untouched(
    tmp_path: Path, source: dict
) -> None:
    """Only the exact <= 0.33.x SHA-pin shape is healed; any other difference
    for the same repo keeps the preserve-or-refuse contract."""
    path = _write_settings(
        tmp_path, {"extraKnownMarketplaces": {"caveman": {"source": source}}}
    )
    before = path.read_bytes()

    result = wire_default_plugins((_entry(_CAVEMAN),), tmp_path)
    installed = install_default_plugins(
        tmp_path, wired=(_entry(_CAVEMAN),), enabled=True, runner=_FakeRunner(_ok)
    )

    assert result.needs_user == (
        (
            _CAVEMAN,
            "marketplace 'caveman' already declares a different source; left unchanged",
        ),
    )
    assert installed.skipped == (_CAVEMAN,)
    assert path.read_bytes() == before


@pytest.mark.unit
@pytest.mark.parametrize("already_enabled", [False, True])
def test_wire_heals_legacy_sha_pinned_default_marketplace(
    tmp_path: Path, already_enabled: bool
) -> None:
    """A ``<= 0.33.x`` SHA-pinned declaration for a reviewed default is
    rewritten unpinned — Claude Code cannot clone a commit SHA, so the stale
    pin would otherwise fail materialisation at every session start."""
    payload: dict = {
        "extraKnownMarketplaces": {
            "caveman": {
                "source": {
                    "source": "github",
                    "repo": "JuliusBrussee/caveman",
                    "ref": _LEGACY_CAVEMAN_SHA,
                }
            }
        }
    }
    if already_enabled:
        payload["enabledPlugins"] = {_CAVEMAN: True}
    _write_settings(tmp_path, payload)

    result = wire_default_plugins((_entry(_CAVEMAN),), tmp_path)

    if already_enabled:
        assert result.already == (_CAVEMAN,)
    else:
        assert result.enabled == (_CAVEMAN,)
    assert result.needs_user == ()
    assert result.errors == ()
    assert _read_settings(tmp_path)["extraKnownMarketplaces"]["caveman"] == {
        "source": {
            "source": "github",
            "repo": "JuliusBrussee/caveman",
        }
    }


@pytest.mark.unit
def test_wire_marketplace_conflict_is_needs_user_and_untouched(
    tmp_path: Path,
) -> None:
    path = _write_settings(
        tmp_path,
        {
            "extraKnownMarketplaces": {
                "caveman": {
                    "source": {
                        "source": "github",
                        "repo": "attacker/different",
                        "ref": "f" * 40,
                    }
                }
            }
        },
    )
    before = path.read_bytes()

    result = wire_default_plugins((_entry(_CAVEMAN),), tmp_path)

    assert result.enabled == ()
    assert result.needs_user == (
        (
            _CAVEMAN,
            "marketplace 'caveman' already declares a different source; left unchanged",
        ),
    )
    assert path.read_bytes() == before


@pytest.mark.unit
def test_wire_disabled_and_empty_selections_make_no_settings(tmp_path: Path) -> None:
    disabled = wire_default_plugins(default_wired(), tmp_path, enabled=False)
    empty = wire_default_plugins((), tmp_path, enabled=True)

    assert disabled.skipped == _TARGETS
    assert empty == PluginWireResult()
    assert not _settings_path(tmp_path).exists()


@pytest.mark.unit
@pytest.mark.parametrize("local", [False, True])
def test_false_tombstone_is_preserved_and_not_materialized(
    tmp_path: Path, local: bool
) -> None:
    _write_settings(
        tmp_path,
        {"enabledPlugins": {_CAVEMAN: False}},
        local=local,
    )
    runner = _FakeRunner(_ok)
    selected = (_entry(_CAVEMAN),)

    wired = wire_default_plugins(selected, tmp_path)
    installed = install_default_plugins(
        tmp_path, wired=selected, enabled=True, runner=runner
    )

    assert wired.already == (_CAVEMAN,)
    assert _read_settings(tmp_path, local=local)["enabledPlugins"][_CAVEMAN] is False
    assert installed.skipped == (_CAVEMAN,)
    assert runner.calls == []
    if local:
        assert not _settings_path(tmp_path).exists()


@pytest.mark.unit
def test_local_false_overrides_project_true(tmp_path: Path) -> None:
    _write_settings(tmp_path, {"enabledPlugins": {_SUPERPOWERS: True}})
    _write_settings(
        tmp_path,
        {"enabledPlugins": {_SUPERPOWERS: False}},
        local=True,
    )
    runner = _FakeRunner(_ok)
    selected = (_entry(_SUPERPOWERS),)

    result = install_default_plugins(tmp_path, wired=selected, runner=runner)

    assert result.skipped == (_SUPERPOWERS,)
    assert runner.calls == []
    assert _read_settings(tmp_path)["enabledPlugins"][_SUPERPOWERS] is True
    assert _read_settings(tmp_path, local=True)["enabledPlugins"][_SUPERPOWERS] is False


@pytest.mark.unit
def test_wire_is_byte_and_result_idempotent(tmp_path: Path) -> None:
    first = wire_default_plugins(default_wired(), tmp_path)
    settings = _settings_path(tmp_path)
    before = settings.read_bytes()
    second = wire_default_plugins(default_wired(), tmp_path)

    assert first.enabled == _TARGETS
    assert second.already == _TARGETS
    assert second.enabled == ()
    assert settings.read_bytes() == before


@pytest.mark.unit
def test_wire_malformed_settings_reports_every_target_without_overwrite(
    tmp_path: Path,
) -> None:
    settings = _settings_path(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json", encoding="utf-8")

    result = wire_default_plugins(default_wired(), tmp_path)

    assert tuple(target for target, _ in result.errors) == _TARGETS
    assert result.enabled == ()
    assert settings.read_text(encoding="utf-8") == "{not json"


@pytest.mark.unit
def test_wire_custom_skill_and_bad_plugin_are_needs_user(tmp_path: Path) -> None:
    wired = (
        WiredEntry(kind=WiredKind.SKILL, target="some-skill", version="1.2.0"),
        WiredEntry(kind=WiredKind.PLUGIN, target="not-a-target", version=None),
    )

    result = wire_default_plugins(wired, tmp_path)

    assert tuple(target for target, _ in result.needs_user) == (
        "some-skill",
        "not-a-target",
    )
    assert not _settings_path(tmp_path).exists()


@pytest.mark.unit
def test_wire_never_reads_stdin_or_runs_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "builtins.input",
        lambda: (_ for _ in ()).throw(
            AssertionError("wire_default_plugins must never call input")
        ),
    )

    def _must_not_run(_argv: list[str], _cwd: Path) -> RunResult:
        raise AssertionError("wire_default_plugins must not materialize")

    wired = (
        _entry(_SUPERPOWERS),
        WiredEntry(kind=WiredKind.SKILL, target="some-skill"),
    )
    result = wire_default_plugins(wired, tmp_path, runner=_must_not_run)

    assert result.enabled == (_SUPERPOWERS,)
    assert result.needs_user[0][0] == "some-skill"


@pytest.mark.unit
def test_install_filtered_selection_materializes_only_selected_default(
    tmp_path: Path,
) -> None:
    selected = (_entry(_CAVEMAN),)
    _declare(tmp_path, selected)
    runner = _FakeRunner(_ok)

    result = install_default_plugins(tmp_path, wired=selected, runner=runner)

    assert result == PluginInstallResult(installed=(_CAVEMAN,))
    assert runner.calls == [
        (("claude", "--version"), tmp_path),
        (
            (
                "claude",
                "plugin",
                "marketplace",
                "add",
                "JuliusBrussee/caveman",
                "--scope",
                "project",
            ),
            tmp_path,
        ),
        (
            ("claude", "plugin", "install", _CAVEMAN, "--scope", "project"),
            tmp_path,
        ),
    ]


@pytest.mark.unit
def test_install_failure_isolated_and_later_default_still_runs(tmp_path: Path) -> None:
    _declare(tmp_path)

    def _fail_caveman_add(argv: list[str]) -> RunResult:
        if argv[:4] == ["claude", "plugin", "marketplace", "add"] and (
            "JuliusBrussee/caveman" in argv[4]
        ):
            return RunResult(1, "", "caveman marketplace unavailable")
        return RunResult(0, "", "")

    runner = _FakeRunner(_fail_caveman_add)
    result = install_default_plugins(
        tmp_path, wired=default_wired(), enabled=True, runner=runner
    )
    argvs = [argv for argv, _ in runner.calls]

    assert result.installed == (_SUPERPOWERS, _ADHD)
    assert result.deferred == ()
    assert result.skipped == ()
    assert result.errors == (
        (
            _CAVEMAN,
            "marketplace add failed (exit 1): caveman marketplace unavailable",
        ),
    )
    assert (
        "claude",
        "plugin",
        "install",
        _CAVEMAN,
        "--scope",
        "project",
    ) not in argvs
    assert argvs[-1] == (
        "claude",
        "plugin",
        "install",
        _ADHD,
        "--scope",
        "project",
    )
    assert argvs.count(("claude", "--version")) == 1


@pytest.mark.unit
def test_install_defers_all_selected_when_claude_absent(tmp_path: Path) -> None:
    _declare(tmp_path)
    runner = _FakeRunner(lambda _argv: RunResult(127, "", "claude: not found"))

    result = install_default_plugins(
        tmp_path, wired=default_wired(), enabled=True, runner=runner
    )

    assert result == PluginInstallResult(deferred=_TARGETS)
    assert runner.calls == [(("claude", "--version"), tmp_path)]
    data = _read_settings(tmp_path)
    assert data["enabledPlugins"] == dict.fromkeys(_TARGETS, True)
    assert set(data["extraKnownMarketplaces"]) == {"caveman", "i-have-adhd"}


@pytest.mark.unit
def test_install_empty_custom_and_disabled_selections_make_zero_runner_calls(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(_ok)
    custom = (_entry("custom@private"),)
    _declare(tmp_path, custom)

    empty = install_default_plugins(tmp_path, wired=(), runner=runner)
    custom_result = install_default_plugins(tmp_path, wired=custom, runner=runner)
    disabled = install_default_plugins(
        tmp_path, wired=default_wired(), enabled=False, runner=runner
    )

    assert empty == PluginInstallResult()
    assert custom_result == PluginInstallResult()
    assert disabled.skipped == _TARGETS
    assert runner.calls == []


@pytest.mark.unit
def test_install_env_guard_defers_all_declared_defaults(tmp_path: Path) -> None:
    from dummyindex.context.default_plugins import SKIP_INSTALL_ENV

    assert os.environ.get(SKIP_INSTALL_ENV)
    _declare(tmp_path)

    result = install_default_plugins(tmp_path, wired=default_wired())

    assert result == PluginInstallResult(deferred=_TARGETS)


@pytest.mark.unit
def test_describe_install_result_splits_info_and_warn() -> None:
    result = PluginInstallResult(
        installed=(_SUPERPOWERS,),
        deferred=("g@h",),
        errors=(("e@f", "boom"),),
    )
    info, warn = describe_install_result(result)
    assert any(f"installed {_SUPERPOWERS}" in line for line in info)
    assert any("g@h" in line and "deferred" in line for line in info)
    assert any("e@f" in line and "boom" in line for line in warn)
