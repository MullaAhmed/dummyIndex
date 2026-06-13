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
from dummyindex.context.domains.config import (
    CONFIG_SCHEMA_VERSION,
    Config,
    ConfigError,
    CouncilMode,
    ModelChoice,
    ScopeKind,
    default_config,
    read_config,
    write_config,
)


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
            "opus-4.7",
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
    assert cfg.model == "opus-4.7"
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
