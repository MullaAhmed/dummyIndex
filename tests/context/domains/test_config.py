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
    read_doc_guard_settings,
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
@pytest.mark.parametrize(
    ("platform", "model", "hooks", "wired"),
    [
        ("claude", ModelChoice.SONNET_4_6, True, True),
        ("codex", ModelChoice.CURRENT, False, False),
        ("both", ModelChoice.CURRENT, True, True),
    ],
)
def test_default_config_is_host_aware(
    platform: str, model: ModelChoice, hooks: bool, wired: bool
) -> None:
    cfg = default_config(platform=platform)
    assert cfg.model == model
    assert cfg.auto_refresh_hook is hooks
    assert bool(cfg.wired) is wired


@pytest.mark.unit
def test_default_config_rejects_unknown_platform() -> None:
    with pytest.raises(ConfigError, match="claude, codex, both"):
        default_config(platform="vscode")


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
        model=ModelChoice.OPUS_4_8,
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
def test_legacy_opus_model_value_migrates_in_memory() -> None:
    """A config written before the opus rename (`opus-4.7`) still loads, with
    the value normalised to the current `opus-4.8` — the opus choice is
    preserved, mirroring the v1->v2 schema migration."""
    payload = default_config().to_dict()
    payload["model"] = "opus-4.7"
    cfg = Config.from_dict(payload)
    assert cfg.model == ModelChoice.OPUS_4_8
    assert cfg.to_dict()["model"] == "opus-4.8"


@pytest.mark.unit
def test_legacy_opus_model_value_reads_from_disk(tmp_path: Path) -> None:
    """An on-disk config.json with the legacy `opus-4.7` value reads back
    without raising, normalised to `opus-4.8`."""
    ctx = _context_dir(tmp_path)
    legacy = {
        "schema_version": 1,
        "scope": "repo",
        "scope_path": None,
        "mode": "deep",
        "model": "opus-4.7",
        "auto_refresh_hook": True,
        "external_docs": [],
        "wire_superpowers": True,
    }
    (ctx / "config.json").write_text(json.dumps(legacy), encoding="utf-8")
    loaded = read_config(ctx)
    assert loaded is not None
    assert loaded.model == ModelChoice.OPUS_4_8


@pytest.mark.unit
def test_migrate_config_rewrites_stale_v1_in_place(tmp_path: Path) -> None:
    """A loadable-but-stale config (v1 schema + legacy opus value) is migrated
    on disk: schema bumped, value normalised, all user choices preserved. The
    helper reports that it migrated."""
    from dummyindex.context.domains.config import migrate_config_in_place

    ctx = _context_dir(tmp_path)
    legacy = {
        "schema_version": 1,
        "scope": "repo",
        "scope_path": None,
        "mode": "deep",
        "model": "opus-4.7",
        "auto_refresh_hook": True,
        "external_docs": [],
        "reconcile_exclude": ["*.png"],
        "wire_superpowers": True,
    }
    (ctx / "config.json").write_text(json.dumps(legacy), encoding="utf-8")

    migrated = migrate_config_in_place(ctx)
    assert migrated is True

    raw = json.loads((ctx / "config.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == CONFIG_SCHEMA_VERSION
    assert raw["model"] == "opus-4.8"
    assert raw["mode"] == "deep"  # choice preserved
    assert raw["reconcile_exclude"] == ["*.png"]  # choice preserved
    assert raw["wired"]  # wire_superpowers:true migrated to a non-empty list


@pytest.mark.unit
def test_migrate_config_noop_when_current(tmp_path: Path) -> None:
    """A current-schema config is left byte-for-byte alone (no churn on every
    install) and the helper reports no migration."""
    from dummyindex.context.domains.config import migrate_config_in_place

    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config())
    before = (ctx / "config.json").read_text(encoding="utf-8")

    migrated = migrate_config_in_place(ctx)
    assert migrated is False
    assert (ctx / "config.json").read_text(encoding="utf-8") == before


@pytest.mark.unit
def test_migrate_config_noop_when_absent(tmp_path: Path) -> None:
    """No config.json -> nothing to migrate, no file created."""
    from dummyindex.context.domains.config import migrate_config_in_place

    ctx = _context_dir(tmp_path)
    assert migrate_config_in_place(ctx) is False
    assert not (ctx / "config.json").exists()


@pytest.mark.unit
def test_migrate_config_leaves_unreadable_config_untouched(tmp_path: Path) -> None:
    """A genuinely broken config (unknown enum) is not silently rewritten —
    the helper reports no migration and the file is left for the user."""
    from dummyindex.context.domains.config import migrate_config_in_place

    ctx = _context_dir(tmp_path)
    broken = default_config().to_dict()
    broken["model"] = "gpt-4"
    before = json.dumps(broken)
    (ctx / "config.json").write_text(before, encoding="utf-8")

    assert migrate_config_in_place(ctx) is False
    assert (ctx / "config.json").read_text(encoding="utf-8") == before


def _write_equipment(ctx: Path, *plugin_names: str) -> None:
    """Write an equipment.json recording each name as a native marketplace plugin."""
    from dummyindex.context.domains.equip.enums import (
        EquipmentKind,
        EquipmentSource,
    )
    from dummyindex.context.domains.equip.lifecycle.manifest import write_manifest
    from dummyindex.context.domains.equip.models import (
        EquipmentItem,
        EquipmentManifest,
    )

    items = tuple(
        EquipmentItem(
            kind=EquipmentKind.PLUGIN,
            name=name,
            path=".claude/settings.json",
            source=EquipmentSource.MARKETPLACE,
            version="1.0.0",
        )
        for name in plugin_names
    )
    write_manifest(ctx, EquipmentManifest(schema_version=4, items=items))


@pytest.mark.unit
def test_reconcile_wired_folds_equipped_plugins_into_config(tmp_path: Path) -> None:
    """An equipped plugin recorded only in equipment.json is unioned into
    config.wired — declared intent never silently drops a wired plugin."""
    from dummyindex.context.domains.config import reconcile_wired_with_equipment

    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config())  # wired == default_wired() (superpowers)
    _write_equipment(ctx, "impeccable@impeccable", "canvas-to-code@canvas-to-code")

    changed = reconcile_wired_with_equipment(ctx)
    assert changed is True

    cfg = read_config(ctx)
    targets = [e.target for e in cfg.wired]
    assert "impeccable@impeccable" in targets
    assert "canvas-to-code@canvas-to-code" in targets
    # The pre-existing default is preserved, not clobbered.
    assert "superpowers@claude-plugins-official" in targets
    # Folded entries are plugins with the equipment version recorded.
    folded = next(e for e in cfg.wired if e.target == "impeccable@impeccable")
    assert folded.kind == WiredKind.PLUGIN
    assert folded.version == "1.0.0"


@pytest.mark.unit
def test_reconcile_wired_is_idempotent(tmp_path: Path) -> None:
    """A second reconcile pass adds nothing and reports no change (no churn)."""
    from dummyindex.context.domains.config import reconcile_wired_with_equipment

    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config())
    _write_equipment(ctx, "impeccable@impeccable")

    assert reconcile_wired_with_equipment(ctx) is True
    before = (ctx / "config.json").read_text(encoding="utf-8")
    assert reconcile_wired_with_equipment(ctx) is False
    assert (ctx / "config.json").read_text(encoding="utf-8") == before


@pytest.mark.unit
def test_reconcile_wired_noop_when_no_config(tmp_path: Path) -> None:
    """Never materialise a seeded config as a reconcile side effect."""
    from dummyindex.context.domains.config import reconcile_wired_with_equipment

    ctx = _context_dir(tmp_path)
    _write_equipment(ctx, "impeccable@impeccable")
    assert reconcile_wired_with_equipment(ctx) is False
    assert not (ctx / "config.json").exists()


@pytest.mark.unit
def test_reconcile_wired_noop_when_no_equipment(tmp_path: Path) -> None:
    """No equipment.json -> nothing to fold, config left byte-for-byte alone."""
    from dummyindex.context.domains.config import reconcile_wired_with_equipment

    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config())
    before = (ctx / "config.json").read_text(encoding="utf-8")
    assert reconcile_wired_with_equipment(ctx) is False
    assert (ctx / "config.json").read_text(encoding="utf-8") == before


@pytest.mark.unit
def test_reconcile_wired_ignores_non_plugin_equipment(tmp_path: Path) -> None:
    """Generated agents/skills/hooks are not wired plugins and are skipped."""
    from dummyindex.context.domains.config import reconcile_wired_with_equipment
    from dummyindex.context.domains.equip.enums import (
        EquipmentKind,
        EquipmentSource,
    )
    from dummyindex.context.domains.equip.lifecycle.manifest import write_manifest
    from dummyindex.context.domains.equip.models import (
        EquipmentItem,
        EquipmentManifest,
    )

    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config())
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="my-impl@local",
        path=".claude/agents/my-impl.md",
        source=EquipmentSource.GENERATED,
    )
    write_manifest(ctx, EquipmentManifest(schema_version=4, items=(item,)))

    assert reconcile_wired_with_equipment(ctx) is False


@pytest.mark.unit
def test_reconcile_wired_skips_already_declared_plugin(tmp_path: Path) -> None:
    """A plugin already in config.wired is not duplicated."""
    from dummyindex.context.domains.config import reconcile_wired_with_equipment

    ctx = _context_dir(tmp_path)
    cfg = default_config()
    declared = cfg.wired + (
        WiredEntry(kind=WiredKind.PLUGIN, target="impeccable@impeccable", version=None),
    )
    from dataclasses import replace

    write_config(ctx, replace(cfg, wired=declared))
    _write_equipment(ctx, "impeccable@impeccable")

    assert reconcile_wired_with_equipment(ctx) is False
    cfg2 = read_config(ctx)
    targets = [e.target for e in cfg2.wired]
    assert targets.count("impeccable@impeccable") == 1


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
def test_onboard_defaults_explicit_codex_platform_overrides_guidance(
    tmp_path: Path,
) -> None:
    from dummyindex.context.output.bootstrap import BEGIN_MARKER, END_MARKER

    ctx = _context_dir(tmp_path)
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir()
    claude_md.write_text(f"{BEGIN_MARKER}\nmanaged\n{END_MARKER}\n", encoding="utf-8")

    rc = run_onboard(["--defaults", "--platform", "codex", str(tmp_path)])

    assert rc == 0
    cfg = read_config(ctx)
    assert cfg == default_config(platform="codex")


@pytest.mark.integration
def test_onboard_defaults_infers_codex_only_managed_guidance(tmp_path: Path) -> None:
    from dummyindex.context.output.agents_md import (
        AGENTS_BEGIN_MARKER,
        AGENTS_END_MARKER,
    )

    ctx = _context_dir(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        f"{AGENTS_BEGIN_MARKER}\nmanaged\n{AGENTS_END_MARKER}\n",
        encoding="utf-8",
    )

    rc = run_onboard(["--defaults", str(tmp_path)])

    assert rc == 0
    cfg = read_config(ctx)
    assert cfg == default_config(platform="codex")


@pytest.mark.integration
def test_onboard_defaults_infers_nested_codex_fallback_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dummyindex.context.output.agents_md import (
        AGENTS_BEGIN_MARKER,
        AGENTS_END_MARKER,
    )

    ctx = _context_dir(tmp_path)
    codex_home = tmp_path / "user-codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        f'[projects.{json.dumps(str(tmp_path.resolve()))}]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )
    project_codex = tmp_path / ".codex"
    project_codex.mkdir()
    (project_codex / "config.toml").write_text(
        'project_doc_fallback_filenames = ["docs/TEAM_GUIDE.md"]\n',
        encoding="utf-8",
    )
    nested_guidance = tmp_path / "docs" / "TEAM_GUIDE.md"
    nested_guidance.parent.mkdir()
    nested_guidance.write_text(
        f"{AGENTS_BEGIN_MARKER}\nmanaged\n{AGENTS_END_MARKER}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    rc = run_onboard(["--defaults", str(tmp_path)])

    assert rc == 0
    assert read_config(ctx) == default_config(platform="codex")


@pytest.mark.integration
def test_onboard_defaults_infers_both_managed_guidance(tmp_path: Path) -> None:
    from dummyindex.context.output.agents_md import (
        AGENTS_BEGIN_MARKER,
        AGENTS_END_MARKER,
    )
    from dummyindex.context.output.bootstrap import BEGIN_MARKER, END_MARKER

    ctx = _context_dir(tmp_path)
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir()
    claude_md.write_text(f"{BEGIN_MARKER}\nmanaged\n{END_MARKER}\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        f"{AGENTS_BEGIN_MARKER}\nmanaged\n{AGENTS_END_MARKER}\n",
        encoding="utf-8",
    )

    rc = run_onboard(["--defaults", str(tmp_path)])

    assert rc == 0
    cfg = read_config(ctx)
    assert cfg == default_config(platform="both")


@pytest.mark.integration
def test_onboard_platform_codex_defaults_unspecified_hook_off(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)

    rc = run_onboard(["--platform", "codex", "--model", "current", str(tmp_path)])

    assert rc == 0
    cfg = read_config(ctx)
    assert cfg is not None
    assert cfg.auto_refresh_hook is False


@pytest.mark.integration
def test_onboard_echoes_the_exact_stamped_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dummyindex.context.domains import config as config_mod

    monkeypatch.setattr(config_mod, "current_dummyindex_version", lambda: "9.9.9")
    ctx = _context_dir(tmp_path)

    rc = run_onboard(["--platform", "codex", "--model", "current", str(tmp_path)])

    assert rc == 0
    config_path = ctx / "config.json"
    disk = config_path.read_text(encoding="utf-8")
    assert '"dummyindex_version": "9.9.9"' in disk
    assert capsys.readouterr().out == f"context onboard: wrote {config_path}\n{disk}"


@pytest.mark.integration
def test_onboard_missing_split_value_does_not_swallow_next_option(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _context_dir(tmp_path)

    rc = run_onboard(["--model", "--platform", "codex", str(tmp_path)])

    assert rc == 2
    assert "--model" in capsys.readouterr().err
    assert not (ctx / "config.json").exists()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--platform", "codex", "--model", "sonnet-4.6"], "requires --model current"),
        (
            ["--platform", "codex", "--model", "current", "--hook"],
            "does not install Claude hooks",
        ),
        (["--platform", "both", "--model", "sonnet-4.6"], "requires --model current"),
        (["--platform", "claude", "--model", "current"], "requires a Claude model"),
    ],
)
def test_onboard_rejects_inconsistent_explicit_host_choices(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    ctx = _context_dir(tmp_path)

    rc = run_onboard([*args, str(tmp_path)])

    assert rc == 2
    assert message in capsys.readouterr().err
    assert not (ctx / "config.json").exists()


@pytest.mark.integration
def test_onboard_without_platform_preserves_legacy_hook_default(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)

    rc = run_onboard(["--model", "current", str(tmp_path)])

    assert rc == 0
    cfg = read_config(ctx)
    assert cfg is not None
    assert cfg.auto_refresh_hook is True


@pytest.mark.integration
def test_onboard_rejects_duplicate_platform(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _context_dir(tmp_path)

    rc = run_onboard(
        [
            "--defaults",
            "--platform",
            "codex",
            "--platform=claude",
            str(tmp_path),
        ]
    )

    assert rc == 2
    assert "--platform may be passed only once" in capsys.readouterr().err
    assert not (ctx / "config.json").exists()


@pytest.mark.integration
def test_onboard_rejects_unknown_platform_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = _context_dir(tmp_path)

    rc = run_onboard(["--defaults", "--platform", "vscode", str(tmp_path)])

    assert rc == 2
    assert "claude, codex, both" in capsys.readouterr().err
    assert not (ctx / "config.json").exists()


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
def test_onboard_accepts_current_model_for_codex(tmp_path: Path) -> None:
    (tmp_path / ".context").mkdir()

    assert run_onboard(["--model", "current", "--no-hook", str(tmp_path)]) == 0

    cfg = read_config(tmp_path / ".context")
    assert cfg is not None
    assert cfg.model == ModelChoice.CURRENT
    assert cfg.auto_refresh_hook is False


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
    rc = run_onboard(["--scope", "subdir", "--model", "sonnet-4.6", str(tmp_path)])
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
    err = capsys.readouterr().err
    assert "no config.json" in err
    assert "--platform <claude|codex|both>" in err


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
def test_config_schema_version_is_3() -> None:
    assert CONFIG_SCHEMA_VERSION == 3
    assert default_config().schema_version == 3


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
    assert cfg.schema_version == 3
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
    assert cfg.schema_version == 3


@pytest.mark.unit
def test_schema_version_3_accepted() -> None:
    payload = default_config().to_dict()
    assert payload["schema_version"] == 3
    loaded = Config.from_dict(payload)
    assert loaded.schema_version == 3
    # The v3 doc-guard fields survive a from_dict of a v3 dict.
    assert loaded.doc_guard_enabled is True
    assert loaded.doc_guard_allow == ()


@pytest.mark.unit
@pytest.mark.parametrize("bad_version", [True, 4, 99])
def test_schema_version_4_and_bool_rejected(bad_version) -> None:
    """`schema_version: true` (isinstance(True, int) is True) and any version
    above the current one are rejected; v3 is now the accepted current."""
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
# v3: doc-guard fields + cheap tolerant accessor
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_doc_guard_defaults_on_with_empty_allow() -> None:
    """The guard ships on everywhere with an empty allowlist."""
    cfg = default_config()
    assert cfg.doc_guard_enabled is True
    assert cfg.doc_guard_allow == ()
    # A bare Config (no doc-guard args) takes the same field defaults.
    bare = Config(
        schema_version=CONFIG_SCHEMA_VERSION,
        scope=ScopeKind.REPO,
        scope_path=None,
        mode=CouncilMode.STANDARD,
        model=ModelChoice.SONNET_4_6,
        auto_refresh_hook=True,
    )
    assert bare.doc_guard_enabled is True
    assert bare.doc_guard_allow == ()


@pytest.mark.unit
def test_doc_guard_round_trips_to_dict_from_dict(tmp_path: Path) -> None:
    """Both fields, including a non-empty allowlist and a flipped enabled flag,
    survive a to_dict/from_dict (and on-disk) round-trip; to_dict emits a list."""
    ctx = _context_dir(tmp_path)
    cfg = default_config_with(
        doc_guard_enabled=False,
        doc_guard_allow=("docs/specs/**", "docs/published/*.md"),
    )
    wire = cfg.to_dict()
    assert wire["doc_guard_enabled"] is False
    assert wire["doc_guard_allow"] == ["docs/specs/**", "docs/published/*.md"]

    write_config(ctx, cfg)
    loaded = read_config(ctx)
    assert loaded.doc_guard_enabled is False
    assert isinstance(loaded.doc_guard_allow, tuple)
    assert loaded.doc_guard_allow == ("docs/specs/**", "docs/published/*.md")
    assert Config.from_dict(cfg.to_dict()).doc_guard_allow == cfg.doc_guard_allow


@pytest.mark.unit
def test_doc_guard_defaults_when_keys_absent() -> None:
    """A pre-v3 payload (no doc-guard keys) reads back at the defaults."""
    payload = default_config().to_dict()
    payload.pop("doc_guard_enabled", None)
    payload.pop("doc_guard_allow", None)
    cfg = Config.from_dict(payload)
    assert cfg.doc_guard_enabled is True
    assert cfg.doc_guard_allow == ()


@pytest.mark.unit
def test_doc_guard_enabled_rejects_non_bool() -> None:
    payload = default_config().to_dict()
    payload["doc_guard_enabled"] = "yes"
    with pytest.raises(ConfigError):
        Config.from_dict(payload)


@pytest.mark.unit
def test_doc_guard_allow_rejects_non_iterable() -> None:
    payload = default_config().to_dict()
    payload["doc_guard_allow"] = "docs/specs/**"  # a bare string, not a list
    with pytest.raises(ConfigError):
        Config.from_dict(payload)


@pytest.mark.unit
def test_doc_guard_serialises_enum_and_repr_free(tmp_path: Path) -> None:
    """The JSON artefact carries the two v3 keys with plain JSON values."""
    cfg = default_config_with(
        doc_guard_enabled=False, doc_guard_allow=("docs/specs/**",)
    )
    blob = json.dumps(cfg.to_dict())
    assert '"doc_guard_enabled": false' in blob
    assert '"doc_guard_allow": ["docs/specs/**"]' in blob


@pytest.mark.unit
def test_migrate_config_upgrades_v2_to_v3_preserving_values(tmp_path: Path) -> None:
    """A loadable v2 config (no doc-guard keys) is migrated on disk to v3: the two
    keys are added at their defaults and every pre-existing value is preserved."""
    from dummyindex.context.domains.config import migrate_config_in_place

    ctx = _context_dir(tmp_path)
    v2 = {
        "schema_version": 2,
        "scope": "subdir",
        "scope_path": "packages/api",
        "mode": "deep",
        "model": "opus-4.8",
        "auto_refresh_hook": False,
        "external_docs": ["docs/"],
        "reconcile_exclude": ["*.png"],
        "command_depths": {"reconcile": "light"},
        "wired": [
            {"kind": "plugin", "target": "a@b", "version": "1.0.0"},
        ],
        "dummyindex_version": "0.29.0",
    }
    (ctx / "config.json").write_text(json.dumps(v2, indent=2) + "\n", encoding="utf-8")

    assert migrate_config_in_place(ctx) is True

    raw = json.loads((ctx / "config.json").read_text(encoding="utf-8"))
    # Schema upgraded and the new keys added at their defaults.
    assert raw["schema_version"] == 3
    assert raw["doc_guard_enabled"] is True
    assert raw["doc_guard_allow"] == []
    # Every pre-existing value preserved untouched.
    assert raw["scope"] == "subdir"
    assert raw["scope_path"] == "packages/api"
    assert raw["mode"] == "deep"
    assert raw["model"] == "opus-4.8"
    assert raw["auto_refresh_hook"] is False
    assert raw["external_docs"] == ["docs/"]
    assert raw["reconcile_exclude"] == ["*.png"]
    assert raw["command_depths"] == {"reconcile": "light"}
    assert raw["wired"] == [{"kind": "plugin", "target": "a@b", "version": "1.0.0"}]


@pytest.mark.unit
def test_doc_guard_accessor_defaults_when_config_absent(tmp_path: Path) -> None:
    """Default-on: an absent config (the guard runs before `.context/` exists)
    returns the engaged defaults without raising."""
    ctx = _context_dir(tmp_path)  # no config.json written
    assert read_doc_guard_settings(ctx) == (True, ())
    # Even a context dir that does not exist at all stays fail-open.
    assert read_doc_guard_settings(tmp_path / "nope") == (True, ())


@pytest.mark.unit
def test_doc_guard_accessor_defaults_on_malformed_json(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    (ctx / "config.json").write_text("{ not valid json", encoding="utf-8")
    assert read_doc_guard_settings(ctx) == (True, ())


@pytest.mark.unit
def test_doc_guard_accessor_reads_configured_values(tmp_path: Path) -> None:
    """A well-formed config returns its on-disk doc-guard values."""
    ctx = _context_dir(tmp_path)
    write_config(
        ctx,
        default_config_with(
            doc_guard_enabled=False,
            doc_guard_allow=("docs/specs/**", "docs/published/*.md"),
        ),
    )
    enabled, allow = read_doc_guard_settings(ctx)
    assert enabled is False
    assert allow == ("docs/specs/**", "docs/published/*.md")


@pytest.mark.unit
def test_doc_guard_accessor_defaults_on_missing_or_mistyped_keys(
    tmp_path: Path,
) -> None:
    """A config missing the keys (a pre-v3 file) or carrying mistyped values
    falls back to the defaults per key — never builds a full Config, never raises."""
    ctx = _context_dir(tmp_path)
    # Missing keys entirely (a pre-v3 on-disk config).
    pre_v3 = {
        "schema_version": 2,
        "scope": "repo",
        "scope_path": None,
        "mode": "standard",
        "model": "sonnet-4.6",
        "auto_refresh_hook": True,
    }
    (ctx / "config.json").write_text(json.dumps(pre_v3), encoding="utf-8")
    assert read_doc_guard_settings(ctx) == (True, ())

    # Mistyped values: enabled not a bool, allow a bare string.
    mistyped = dict(pre_v3, doc_guard_enabled="yes", doc_guard_allow="docs/specs/**")
    (ctx / "config.json").write_text(json.dumps(mistyped), encoding="utf-8")
    assert read_doc_guard_settings(ctx) == (True, ())


@pytest.mark.unit
def test_doc_guard_accessor_never_builds_full_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hot-path accessor must not route through `Config.from_dict` (which would
    parse `wired`/`command_depths`); it reads the raw JSON keys directly."""
    import dummyindex.context.domains.config as config_mod

    ctx = _context_dir(tmp_path)
    write_config(ctx, default_config_with(doc_guard_allow=("docs/specs/**",)))

    def _boom(*_a: object, **_k: object):
        raise AssertionError("accessor must not build a full Config")

    monkeypatch.setattr(config_mod.Config, "from_dict", classmethod(_boom))
    assert read_doc_guard_settings(ctx) == (True, ("docs/specs/**",))


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
    assert resolve_depth(ctx, DepthCommand.RECONCILE, "light") == CouncilMode.LIGHT


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
