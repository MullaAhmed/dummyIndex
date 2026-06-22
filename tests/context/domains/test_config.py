"""Tests for v0.14 onboarding config (`.context/config.json`).

Covers the domain round-trip (read/write/from_dict validation) and the two
CLI handlers (`onboard` + `config show`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.config import run as run_config
from dummyindex.cli.onboard import run as run_onboard
from dummyindex.context.default_plugins import (
    WiredEntry,
    WiredKind,
    default_wired,
)
from dummyindex.context.domains.config import (
    CONFIG_SCHEMA_VERSION,
    Config,
    ConfigError,
    CouncilMode,
    DepthCommand,
    ModelChoice,
    ScopeKind,
    current_dummyindex_version,
    default_config,
    read_config,
    resolve_depth,
    write_config,
)


def default_config_with(**overrides: object):
    from dataclasses import replace

    from dummyindex.context.domains.config import default_config

    return replace(default_config(), **overrides)


def _context_dir(tmp_path: Path) -> Path:
    """Create and return a `.context/` dir under tmp_path."""
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True, exist_ok=True)
    return ctx


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_config_roundtrips(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    written = write_config(ctx, default_config())
    assert written == (ctx / "config.json").resolve()

    loaded = read_config(ctx)
    assert loaded == default_config()
    assert loaded.model == "sonnet-4.6"
    assert loaded.mode == "standard"
    assert loaded.scope == "repo"
    assert loaded.schema_version == CONFIG_SCHEMA_VERSION


@pytest.mark.unit
def test_write_config_is_pretty_with_trailing_newline(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config())
    text = (ctx / "config.json").read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "\n  " in text  # indented (pretty)


@pytest.mark.unit
def test_external_docs_roundtrips_as_tuple(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    cfg = Config(
        schema_version=CONFIG_SCHEMA_VERSION,
        scope=ScopeKind.REPO,
        scope_path=None,
        mode=CouncilMode.DEEP,
        model=ModelChoice.OPUS_4_7,
        auto_refresh_hook=False,
        external_docs=("docs/", "wiki/api.md"),
    )
    write_config(ctx, cfg)
    loaded = read_config(ctx)
    assert isinstance(loaded.external_docs, tuple)
    assert loaded.external_docs == ("docs/", "wiki/api.md")
    # to_dict emits a list (JSON-shaped)
    assert loaded.to_dict()["external_docs"] == ["docs/", "wiki/api.md"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "field, value",
    [
        ("model", "gpt-4"),
        ("mode", "turbo"),
        ("scope", "global"),
    ],
)
def test_from_dict_rejects_unknown_enum(field: str, value: str) -> None:
    payload = default_config().to_dict()
    payload[field] = value
    with pytest.raises(ConfigError):
        Config.from_dict(payload)


@pytest.mark.unit
def test_read_config_returns_none_when_absent(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    assert read_config(ctx) is None


@pytest.mark.unit
def test_read_config_raises_on_malformed_json(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    (ctx / "config.json").write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ConfigError):
        read_config(ctx)


@pytest.mark.unit
@pytest.mark.parametrize("bad_version", [True, 99])
def test_from_dict_rejects_bool_and_unknown_schema_version(bad_version) -> None:
    """`schema_version: true` (isinstance(True, int) is True) and any version
    other than the supported one are both rejected."""
    payload = default_config().to_dict()
    payload["schema_version"] = bad_version
    with pytest.raises(ConfigError):
        Config.from_dict(payload)


@pytest.mark.unit
def test_config_post_init_rejects_subdir_without_path() -> None:
    """Cross-field invariant: scope==subdir requires a non-empty scope_path."""
    with pytest.raises(ConfigError):
        Config(
            schema_version=CONFIG_SCHEMA_VERSION,
            scope=ScopeKind.SUBDIR,
            scope_path=None,
            mode=CouncilMode.STANDARD,
            model=ModelChoice.SONNET_4_6,
            auto_refresh_hook=True,
        )


@pytest.mark.unit
def test_from_dict_rejects_subdir_without_scope_path() -> None:
    payload = default_config().to_dict()
    payload["scope"] = "subdir"  # scope_path stays null
    with pytest.raises(ConfigError):
        Config.from_dict(payload)


@pytest.mark.unit
def test_reconcile_exclude_roundtrips_as_tuple(tmp_path: Path) -> None:
    """The user's repo-specific reconcile-noise globs round-trip as a tuple."""
    ctx = _context_dir(tmp_path)
    cfg = Config(
        schema_version=CONFIG_SCHEMA_VERSION,
        scope=ScopeKind.REPO,
        scope_path=None,
        mode=CouncilMode.STANDARD,
        model=ModelChoice.SONNET_4_6,
        auto_refresh_hook=True,
        reconcile_exclude=("docs/spikes/**", "*.png"),
    )
    write_config(ctx, cfg)
    loaded = read_config(ctx)
    assert isinstance(loaded.reconcile_exclude, tuple)
    assert loaded.reconcile_exclude == ("docs/spikes/**", "*.png")
    assert loaded.to_dict()["reconcile_exclude"] == ["docs/spikes/**", "*.png"]


@pytest.mark.unit
def test_reconcile_exclude_defaults_empty_and_back_compat(tmp_path: Path) -> None:
    """A config written before the field existed reads back with an empty
    tuple (absent-field back-compat), and the default config has none."""
    assert default_config().reconcile_exclude == ()
    # A payload with no reconcile_exclude key still loads.
    payload = default_config().to_dict()
    payload.pop("reconcile_exclude", None)
    cfg = Config.from_dict(payload)
    assert cfg.reconcile_exclude == ()


@pytest.mark.unit
def test_reconcile_exclude_rejects_non_iterable() -> None:
    payload = default_config().to_dict()
    payload["reconcile_exclude"] = "docs/**"  # a bare string, not a list
    with pytest.raises(ConfigError):
        Config.from_dict(payload)


@pytest.mark.unit
def test_to_dict_serialises_enums_as_plain_strings() -> None:
    """Wire output is plain strings (`.value`), never `CouncilMode.STANDARD`
    reprs — the JSON artefact must stay enum-repr-free."""
    cfg = default_config()
    assert isinstance(cfg.scope, ScopeKind)  # field is the enum member
    wire = json.dumps(cfg.to_dict())
    assert '"mode": "standard"' in wire
    assert '"model": "sonnet-4.6"' in wire
    assert '"scope": "repo"' in wire
    assert "CouncilMode" not in wire
    assert "ScopeKind" not in wire


# ---------------------------------------------------------------------------
# CLI: onboard
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_onboard_defaults_writes_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _context_dir(tmp_path)
    rc = run_onboard(["--defaults", str(tmp_path)])
    assert rc == 0
    cfg = read_config(ctx)
    assert cfg == default_config()
    out = capsys.readouterr().out
    assert "context onboard: wrote" in out
    assert "sonnet-4.6" in out


@pytest.mark.integration
def test_onboard_requires_model_without_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _context_dir(tmp_path)
    rc = run_onboard(["--mode", "deep", str(tmp_path)])
    assert rc == 2
    assert "--model is required" in capsys.readouterr().err
    # Nothing written when validation fails.
    assert not (ctx / "config.json").exists()


@pytest.mark.integration
def test_onboard_full_flags_persist_choices(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    rc = run_onboard(
        [
            "--scope",
            "subdir",
            "--scope-path",
            "packages/api",
            "--mode",
            "deep",
            "--model",
            "opus-4.8",
            "--no-hook",
            "--doc",
            "docs/",
            "--doc",
            "wiki/",
            str(tmp_path),
        ]
    )
    assert rc == 0
    cfg = read_config(ctx)
    assert cfg.scope == "subdir"
    assert cfg.scope_path == "packages/api"
    assert cfg.mode == "deep"
    assert cfg.model == "opus-4.8"
    assert cfg.auto_refresh_hook is False
    assert cfg.external_docs == ("docs/", "wiki/")


@pytest.mark.integration
def test_onboard_errors_when_context_dir_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No .context/ created.
    rc = run_onboard(["--defaults", str(tmp_path)])
    assert rc == 2
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.integration
def test_onboard_rejects_bad_enum_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _context_dir(tmp_path)
    rc = run_onboard(["--model", "gpt-4", str(tmp_path)])
    assert rc == 2
    assert "not one of" in capsys.readouterr().err


@pytest.mark.integration
def test_onboard_subdir_without_scope_path_returns_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--scope subdir` without `--scope-path` is the cross-field invariant
    violation — rejected with rc=2 and a clear error, nothing written."""
    ctx = _context_dir(tmp_path)
    rc = run_onboard(
        ["--scope", "subdir", "--model", "sonnet-4.6", str(tmp_path)]
    )
    assert rc == 2
    assert "scope_path" in capsys.readouterr().err
    assert not (ctx / "config.json").exists()


# ---------------------------------------------------------------------------
# CLI: config show
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_config_show_prints_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config())
    rc = run_config(["show", str(tmp_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["model"] == "sonnet-4.6"


@pytest.mark.integration
def test_config_show_returns_1_when_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _context_dir(tmp_path)
    rc = run_config(["show", str(tmp_path)])
    assert rc == 1
    assert "no config.json" in capsys.readouterr().err


@pytest.mark.integration
def test_config_unknown_action_returns_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = run_config(["bogus", str(tmp_path)])
    assert rc == 2
    assert "unknown config sub-action" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# v2: wired
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_config_seeds_wired_from_default_plugins() -> None:
    """A fresh config declares the default plugin set as `wired` entries."""
    assert default_config().wired == default_wired()
    # Today: one superpowers plugin entry.
    assert all(e.kind == WiredKind.PLUGIN for e in default_config().wired)
    assert any(
        e.target == "superpowers@claude-plugins-official"
        for e in default_config().wired
    )


@pytest.mark.unit
def test_wired_round_trips_to_dict_from_dict() -> None:
    cfg = default_config_with(
        wired=(
            WiredEntry(kind=WiredKind.PLUGIN, target="foo@mkt", version=None),
            WiredEntry(kind=WiredKind.SKILL, target="some-skill", version="1.2.0"),
        )
    )
    wire = cfg.to_dict()["wired"]
    assert wire == [
        {"kind": "plugin", "target": "foo@mkt", "version": None},
        {"kind": "skill", "target": "some-skill", "version": "1.2.0"},
    ]
    assert Config.from_dict(cfg.to_dict()).wired == cfg.wired


@pytest.mark.unit
def test_wired_serializes_enum_repr_free() -> None:
    cfg = default_config_with(
        wired=(WiredEntry(kind=WiredKind.SKILL, target="s", version=None),)
    )
    blob = json.dumps(cfg.to_dict())
    assert "WiredKind" not in blob
    assert '"kind": "skill"' in blob


@pytest.mark.unit
def test_wired_entry_rejects_bad_kind() -> None:
    with pytest.raises(ValueError):
        WiredEntry.from_dict({"kind": "bogus", "target": "x"})


@pytest.mark.unit
def test_wired_rejects_bad_kind_via_from_dict() -> None:
    payload = default_config().to_dict()
    payload["wired"] = [{"kind": "bogus", "target": "x", "version": None}]
    with pytest.raises(ConfigError):
        Config.from_dict(payload)


@pytest.mark.unit
def test_wired_defaults_empty_when_absent() -> None:
    payload = default_config().to_dict()
    payload.pop("wired", None)
    assert Config.from_dict(payload).wired == ()


# ---------------------------------------------------------------------------
# v2: command_depths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_command_depths_round_trips_as_object() -> None:
    cfg = default_config_with(
        command_depths=(
            (DepthCommand.RECONCILE, CouncilMode.LIGHT),
            (DepthCommand.AUDIT, CouncilMode.DEEP),
        )
    )
    obj = cfg.to_dict()["command_depths"]
    assert obj == {"reconcile": "light", "audit": "deep"}
    assert Config.from_dict(cfg.to_dict()).command_depths == cfg.command_depths


@pytest.mark.unit
def test_command_depths_serializes_enum_repr_free() -> None:
    cfg = default_config_with(
        command_depths=((DepthCommand.RECONCILE, CouncilMode.LIGHT),)
    )
    blob = json.dumps(cfg.to_dict())
    assert "DepthCommand" not in blob
    assert "CouncilMode" not in blob
    assert '"reconcile": "light"' in blob


@pytest.mark.unit
def test_command_depths_defaults_empty_when_absent() -> None:
    payload = default_config().to_dict()
    payload.pop("command_depths", None)
    assert Config.from_dict(payload).command_depths == ()
    assert default_config().command_depths == ()


@pytest.mark.unit
def test_command_depths_unknown_command_key_rejected() -> None:
    payload = default_config().to_dict()
    payload["command_depths"] = {"rebuild": "light"}  # rebuild is NOT depth-bearing
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(payload)
    msg = str(exc.value)
    # Names the valid commands.
    assert "ingest" in msg and "reconcile" in msg and "build" in msg


@pytest.mark.unit
def test_command_depths_invalid_depth_value_rejected() -> None:
    payload = default_config().to_dict()
    payload["command_depths"] = {"reconcile": "turbo"}
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(payload)
    assert "light" in str(exc.value) and "deep" in str(exc.value)


# ---------------------------------------------------------------------------
# v2: schema migration + dummyindex_version
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_config_schema_version_is_2() -> None:
    assert CONFIG_SCHEMA_VERSION == 2
    assert default_config().schema_version == 2


@pytest.mark.unit
def test_v1_wire_superpowers_true_migrates_to_default_wired() -> None:
    payload = {
        "schema_version": 1,
        "scope": "repo",
        "scope_path": None,
        "mode": "standard",
        "model": "sonnet-4.6",
        "auto_refresh_hook": True,
        "wire_superpowers": True,
        "external_docs": [],
        "reconcile_exclude": [],
    }
    cfg = Config.from_dict(payload)
    assert cfg.wired == default_wired()
    assert cfg.schema_version == 2
    # Migration populates the version stamp.
    assert cfg.dummyindex_version == current_dummyindex_version()


@pytest.mark.unit
def test_v1_wire_superpowers_false_migrates_to_empty_wired() -> None:
    payload = {
        "schema_version": 1,
        "scope": "repo",
        "scope_path": None,
        "mode": "standard",
        "model": "sonnet-4.6",
        "auto_refresh_hook": True,
        "wire_superpowers": False,
        "external_docs": [],
        "reconcile_exclude": [],
    }
    cfg = Config.from_dict(payload)
    assert cfg.wired == ()
    assert cfg.schema_version == 2


@pytest.mark.unit
def test_schema_version_2_accepted() -> None:
    payload = default_config().to_dict()
    assert payload["schema_version"] == 2
    assert Config.from_dict(payload).schema_version == 2


@pytest.mark.unit
@pytest.mark.parametrize("bad_version", [True, 3, 99])
def test_schema_version_3_and_bool_rejected(bad_version) -> None:
    payload = default_config().to_dict()
    payload["schema_version"] = bad_version
    with pytest.raises(ConfigError):
        Config.from_dict(payload)


@pytest.mark.unit
def test_dummyindex_version_read_tolerates_any_value(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    payload = default_config().to_dict()
    payload["dummyindex_version"] = "0.0.1-some-ancient"
    (ctx / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    cfg = read_config(ctx)
    assert cfg.dummyindex_version == "0.0.1-some-ancient"


@pytest.mark.unit
def test_write_config_stamps_current_version(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    stale = default_config_with(dummyindex_version="0.0.1-stale")
    write_config(ctx, stale)
    loaded = read_config(ctx)
    assert loaded.dummyindex_version == current_dummyindex_version()


@pytest.mark.unit
def test_v2_config_round_trips_byte_stable(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    cfg = default_config_with(
        command_depths=((DepthCommand.RECONCILE, CouncilMode.LIGHT),),
        wired=(WiredEntry(kind=WiredKind.PLUGIN, target="a@b", version=None),),
    )
    write_config(ctx, cfg)
    first = (ctx / "config.json").read_text(encoding="utf-8")
    reloaded = read_config(ctx)
    write_config(ctx, reloaded)
    second = (ctx / "config.json").read_text(encoding="utf-8")
    assert first == second


# ---------------------------------------------------------------------------
# v2: resolve_depth precedence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_depth_flag_wins(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    write_config(
        ctx,
        default_config_with(
            mode=CouncilMode.DEEP,
            command_depths=((DepthCommand.RECONCILE, CouncilMode.STANDARD),),
        ),
    )
    assert (
        resolve_depth(ctx, DepthCommand.RECONCILE, "light") == CouncilMode.LIGHT
    )


@pytest.mark.unit
def test_resolve_depth_command_depths_beats_mode(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    write_config(
        ctx,
        default_config_with(
            mode=CouncilMode.DEEP,
            command_depths=((DepthCommand.RECONCILE, CouncilMode.LIGHT),),
        ),
    )
    assert resolve_depth(ctx, DepthCommand.RECONCILE, None) == CouncilMode.LIGHT
    # An unset command falls through to mode.
    assert resolve_depth(ctx, DepthCommand.INGEST, None) == CouncilMode.DEEP


@pytest.mark.unit
def test_resolve_depth_falls_through_to_mode(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config_with(mode=CouncilMode.LIGHT))
    assert resolve_depth(ctx, DepthCommand.AUDIT, None) == CouncilMode.LIGHT


@pytest.mark.unit
def test_resolve_depth_defaults_standard_without_config(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)  # no config.json written
    assert resolve_depth(ctx, DepthCommand.AUDIT, None) == CouncilMode.STANDARD


@pytest.mark.unit
def test_resolve_depth_invalid_flag_raises(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config())
    with pytest.raises(ConfigError) as exc:
        resolve_depth(ctx, DepthCommand.AUDIT, "turbo")
    assert "light" in str(exc.value) and "deep" in str(exc.value)


# ---------------------------------------------------------------------------
# v2: audit's resolve_mode is a thin wrapper that delegates to resolve_depth
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("flag", [None, "", "deep"])
def test_audit_resolve_mode_delegates_to_resolve_depth(
    tmp_path: Path, flag: str | None
) -> None:
    """``audit.resolve_mode`` must return exactly what the shared resolver does
    for ``DepthCommand.AUDIT`` — it carries no precedence logic of its own."""
    from dummyindex.context.domains.audit import resolve_mode

    ctx = _context_dir(tmp_path)
    write_config(
        ctx,
        default_config_with(
            mode=CouncilMode.DEEP,
            command_depths=((DepthCommand.AUDIT, CouncilMode.LIGHT),),
        ),
    )
    # `resolve_mode` treats a falsy flag (None/"") as "no flag"; mirror that.
    expected = resolve_depth(ctx, DepthCommand.AUDIT, flag or None)
    assert resolve_mode(ctx, flag) == expected
