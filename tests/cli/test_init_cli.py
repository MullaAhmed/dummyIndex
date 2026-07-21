"""Tests for `dummyindex context init` (== `ingest`) enriched-index guard.

`init`/`ingest` means "first build". An enriched index proves it is NOT the
first build, so init must refuse to overwrite it unless `--force` is passed.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

import dummyindex.context.default_plugins as default_plugins_module
from dummyindex.cli import init
from dummyindex.context.build.runner import build_all
from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    SKIP_INSTALL_ENV,
    RunResult,
    WiredEntry,
    WiredKind,
    default_wired,
)
from dummyindex.context.domains.config import (
    default_config,
    read_config,
    write_config,
)
from dummyindex.context.domains.features import rename_feature
from dummyindex.context.output.bootstrap import ALWAYS_ON_OUTPUT_POLICY
from tests.paths import SAMPLE_REPO

_FIXTURE_ROOT = SAMPLE_REPO


class _RecordingRunner:
    def __init__(self, capture_output: Callable[[], str] | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.output_before_first_call: str | None = None
        self._capture_output = capture_output

    def __call__(self, argv: list[str], _cwd: Path) -> RunResult:
        if not self.calls and self._capture_output is not None:
            self.output_before_first_call = self._capture_output()
        self.calls.append(tuple(argv))
        return RunResult(0, "ok", "")


_DEFAULT_TARGETS = tuple(plugin.target for plugin in DEFAULT_PLUGINS)


@pytest.fixture
def primed_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    build_all(dest, cache_root=tmp_path / "cache")
    return dest


def _curate(repo: Path) -> str:
    features_dir = repo / ".context" / "features"
    index = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    first_id = index["features"][0]["feature_id"]
    new_id = "auth-core"
    rename_feature(
        features_dir,
        from_id=first_id,
        to_id=new_id,
        new_name="Auth Core",
        new_summary="Curated.",
    )
    return new_id


@pytest.mark.integration
def test_init_refuses_on_enriched_index_without_force(
    primed_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    new_id = _curate(primed_repo)
    index_before = (primed_repo / ".context" / "features" / "INDEX.json").read_text(
        encoding="utf-8"
    )

    rc = init.run([str(primed_repo)])

    assert rc == 2
    err = capsys.readouterr().err
    assert "curated index detected" in err
    assert "--force" in err
    index_after = (primed_repo / ".context" / "features" / "INDEX.json").read_text(
        encoding="utf-8"
    )
    assert index_after == index_before
    assert (primed_repo / ".context" / "features" / new_id).is_dir()


@pytest.mark.integration
def test_init_force_proceeds_on_enriched_index(
    primed_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _curate(primed_repo)
    rc = init.run([str(primed_repo), "--force", "--no-hooks"])
    assert rc == 0
    assert "context init: wrote" in capsys.readouterr().out


@pytest.mark.integration
def test_init_proceeds_on_deterministic_index(
    primed_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No curation → init may proceed (re-builds the deterministic index).
    rc = init.run([str(primed_repo), "--no-hooks"])
    assert rc == 0
    assert "context init: wrote" in capsys.readouterr().out


@pytest.mark.integration
def test_init_proceeds_on_fresh_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fresh = tmp_path / "fresh"
    shutil.copytree(_FIXTURE_ROOT, fresh)
    rc = init.run([str(fresh), "--no-hooks"])
    assert rc == 0
    assert (fresh / ".context").is_dir()


# ----- reviewed default-plugin orchestration -------------------------------


def _make_min_repo(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / ".git").mkdir()
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (target / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8"
    )


def _plugin_settings(repo: Path) -> dict:
    settings = repo / ".claude" / "settings.json"
    if not settings.exists():
        return {}
    return json.loads(settings.read_text(encoding="utf-8"))


def _plugin_install_targets(calls: list[tuple[str, ...]]) -> list[str]:
    return [argv[3] for argv in calls if argv[:3] == ("claude", "plugin", "install")]


@pytest.mark.integration
@pytest.mark.parametrize("platform", ["claude", "both"])
def test_init_declares_and_materializes_all_defaults_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    platform: str,
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)
    runner = _RecordingRunner(lambda: capsys.readouterr().out)
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    rc = init.run([".", "--no-hooks", "--platform", platform])

    assert rc == 0
    settings = _plugin_settings(repo)
    assert settings["enabledPlugins"] == dict.fromkeys(_DEFAULT_TARGETS, True)
    for plugin in DEFAULT_PLUGINS:
        if plugin.repo is None:
            continue
        assert settings["extraKnownMarketplaces"][plugin.marketplace]["source"] == {
            "source": "github",
            "repo": plugin.repo,
            "ref": plugin.ref,
        }
        add_call = (
            "claude",
            "plugin",
            "marketplace",
            "add",
            f"{plugin.repo}@{plugin.ref}",
            "--scope",
            "project",
        )
        install_call = (
            "claude",
            "plugin",
            "install",
            plugin.target,
            "--scope",
            "project",
        )
        assert runner.calls.index(add_call) < runner.calls.index(install_call)
    assert runner.calls.count(("claude", "--version")) == 1
    assert _plugin_install_targets(runner.calls) == list(_DEFAULT_TARGETS)
    before_runner = runner.output_before_first_call or ""
    for plugin in DEFAULT_PLUGINS:
        if plugin.repo is not None:
            assert f"{plugin.repo}@{plugin.ref}" in before_runner
    assert "runs code: yes" in before_runner
    assert "runs code: no" in before_runner
    assert "--no-default-plugins" in before_runner
    if platform == "both":
        assert (repo / "AGENTS.md").read_text(encoding="utf-8").count(
            ALWAYS_ON_OUTPUT_POLICY
        ) == 1


@pytest.mark.integration
def test_init_codex_only_then_both_transitions_defaults_same_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    rc = init.run([".", "--no-hooks", "--platform", "codex"])

    assert rc == 0
    assert runner.calls == []
    assert not (repo / ".claude").exists()
    assert (repo / "AGENTS.md").read_text(encoding="utf-8").count(
        ALWAYS_ON_OUTPUT_POLICY
    ) == 1
    write_config(repo / ".context", default_config(platform="codex"))

    rc = init.run([".", "--no-hooks", "--platform", "both"])

    assert rc == 0
    cfg = read_config(repo / ".context")
    assert cfg is not None
    assert cfg.default_plugins_enabled is True
    assert tuple(entry.target for entry in cfg.wired) == _DEFAULT_TARGETS
    assert _plugin_settings(repo)["enabledPlugins"] == dict.fromkeys(
        _DEFAULT_TARGETS, True
    )
    assert runner.calls.count(("claude", "--version")) == 1
    assert _plugin_install_targets(runner.calls) == list(_DEFAULT_TARGETS)


@pytest.mark.integration
def test_init_backfills_opted_in_config_before_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    custom = WiredEntry(WiredKind.PLUGIN, "custom@team")
    write_config(
        repo / ".context",
        replace(
            default_config(),
            wired=(default_wired()[0], custom),
            default_plugins_enabled=True,
        ),
    )
    monkeypatch.chdir(repo)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    assert init.run([".", "--no-hooks"]) == 0

    cfg = read_config(repo / ".context")
    assert cfg is not None
    assert tuple(entry.target for entry in cfg.wired) == (
        _DEFAULT_TARGETS[0],
        custom.target,
        *_DEFAULT_TARGETS[1:],
    )
    assert runner.calls.count(("claude", "--version")) == 1
    assert _plugin_install_targets(runner.calls) == list(_DEFAULT_TARGETS)


@pytest.mark.integration
@pytest.mark.parametrize("flag", ["--no-default-plugins", "--no-superpowers"])
def test_init_one_run_opt_out_is_byte_exact_and_side_effect_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    custom = WiredEntry(WiredKind.PLUGIN, "custom@team")
    write_config(
        repo / ".context",
        replace(default_config(), wired=(default_wired()[0], custom)),
    )
    config_path = repo / ".context" / "config.json"
    config_before = config_path.read_bytes()
    settings_path = repo / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"userSetting": true}\n', encoding="utf-8")
    settings_before = settings_path.read_bytes()
    monkeypatch.chdir(repo)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    assert init.run([".", "--no-hooks", flag]) == 0

    assert config_path.read_bytes() == config_before
    assert settings_path.read_bytes() == settings_before
    assert runner.calls == []


@pytest.mark.integration
def test_init_malformed_config_warns_and_mutates_no_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    config_path = repo / ".context" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{malformed\n", encoding="utf-8")
    before = config_path.read_bytes()
    monkeypatch.chdir(repo)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    rc = init.run([".", "--no-hooks", "--depth", "standard"])

    assert rc == 0
    assert config_path.read_bytes() == before
    assert not (repo / ".claude" / "settings.json").exists()
    assert runner.calls == []
    assert "skipped defaults" in capsys.readouterr().err


@pytest.mark.integration
def test_init_explicit_default_opt_out_remains_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    write_config(
        repo / ".context",
        replace(default_config(), default_plugins_enabled=False),
    )
    config_path = repo / ".context" / "config.json"
    before = config_path.read_bytes()
    monkeypatch.chdir(repo)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    assert init.run([".", "--no-hooks"]) == 0

    cfg = read_config(repo / ".context")
    assert cfg is not None and cfg.default_plugins_enabled is False
    assert config_path.read_bytes() == before
    assert not (repo / ".claude" / "settings.json").exists()
    assert runner.calls == []


# ----- --depth threading (Task 4) -------------------------------------------


@pytest.mark.integration
def test_init_depth_flag_surfaces_and_writes_no_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--depth deep` is a one-run council override: it surfaces in the summary
    and ingest never materializes a `config.json` as a side effect."""
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    rc = init.run(["--no-hooks", "--no-superpowers", "--depth", "deep", "."])

    assert rc == 0
    assert "council depth: deep" in capsys.readouterr().out
    # The one-run override is never persisted.
    assert not (repo / ".context" / "config.json").exists()


@pytest.mark.integration
def test_init_no_depth_defaults_standard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no config and no `--depth`, ingest resolves the standard default."""
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    rc = init.run(["--no-hooks", "--no-superpowers", "."])

    assert rc == 0
    assert "council depth: standard" in capsys.readouterr().out


@pytest.mark.unit
def test_init_invalid_depth_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    rc = init.run(["--no-hooks", "--no-superpowers", "--depth", "turbo", "."])

    assert rc == 2
    assert "light|standard|deep" in capsys.readouterr().err


@pytest.mark.unit
def test_init_malformed_config_surfaces_real_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed config.json must surface its real ConfigError, not be
    misreported as a `--depth` flag problem (regression: a bad `model` value
    once printed `--depth must be light|standard|deep, got None`).

    The legacy `opus-4.7` value is *migrated*, not rejected (see
    `config.migrate_config_in_place`); this test uses a genuinely unknown model
    so it still exercises the real-ConfigError path."""
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    context_dir = repo / ".context"
    context_dir.mkdir()
    (context_dir / "config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope": "repo",
                "scope_path": None,
                "mode": "deep",
                "model": "gpt-4",  # not a ModelChoice and not a legacy alias
                "auto_refresh_hook": True,
            }
        ),
        encoding="utf-8",
    )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    rc = init.run(["--no-hooks", "--no-superpowers", "."])

    err = capsys.readouterr().err
    assert rc == 2
    assert "model" in err
    assert "light|standard|deep" not in err


@pytest.mark.integration
def test_codex_init_reports_malformed_guidance_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dummyindex.context.output.agents_md import (
        AGENTS_BEGIN_MARKER,
        AGENTS_END_MARKER,
    )

    repo = tmp_path / "repo"
    _make_min_repo(repo)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    guidance = repo / "AGENTS.md"
    original = f"{AGENTS_END_MARKER}\nKeep me.\n{AGENTS_BEGIN_MARKER}\n"
    guidance.write_text(original, encoding="utf-8")

    rc = init.run([str(repo), "--platform", "codex", "--no-hooks", "--no-superpowers"])

    assert rc == 0
    assert (repo / ".context" / "INDEX.md").exists()
    assert guidance.read_text(encoding="utf-8") == original
    err = capsys.readouterr().err
    assert "Codex guidance -> skipped" in err
    assert "end marker before" in err


@pytest.mark.integration
def test_codex_init_reports_unwritable_guidance_target_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    (repo / "AGENTS.md").mkdir()

    rc = init.run([str(repo), "--platform", "codex", "--no-hooks", "--no-superpowers"])

    assert rc == 0
    assert (repo / ".context" / "INDEX.md").exists()
    err = capsys.readouterr().err
    assert "Codex guidance -> skipped" in err
    assert "AGENTS.md" in err


@pytest.mark.integration
def test_claude_init_reversed_markers_builds_index_without_guidance_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from dummyindex.context.output.bootstrap import BEGIN_MARKER, END_MARKER

    repo = tmp_path / "repo"
    _make_min_repo(repo)
    root_guidance = repo / "CLAUDE.md"
    original = f"# User rules\n\n{END_MARKER}\nbody\n{BEGIN_MARKER}\n"
    root_guidance.write_text(original, encoding="utf-8")

    with pytest.warns(UserWarning, match="CLAUDE.md reconcile"):
        rc = init.run(
            [str(repo), "--platform", "claude", "--no-hooks", "--no-superpowers"]
        )

    assert rc == 0
    assert (repo / ".context" / "INDEX.md").exists()
    assert root_guidance.read_text(encoding="utf-8") == original
    assert not (repo / ".claude" / "CLAUDE.md").exists()
    assert "CLAUDE.md  ->  managed block written" not in capsys.readouterr().out


@pytest.mark.integration
def test_claude_init_invalid_utf8_builds_index_without_traceback(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    root_guidance = repo / "CLAUDE.md"
    original = b"\xff\xfeinvalid guidance"
    root_guidance.write_bytes(original)

    with pytest.warns(UserWarning, match="CLAUDE.md reconcile"):
        rc = init.run(
            [str(repo), "--platform", "claude", "--no-hooks", "--no-superpowers"]
        )

    assert rc == 0
    assert (repo / ".context" / "INDEX.md").exists()
    assert root_guidance.read_bytes() == original
    assert not (repo / ".claude" / "CLAUDE.md").exists()


@pytest.mark.integration
def test_claude_init_refuses_symlinked_guidance_directory_outside_project(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    _make_min_repo(repo)
    outside.mkdir()
    outside_guidance = outside / "CLAUDE.md"
    outside_guidance.write_text("# Outside rules\n", encoding="utf-8")
    (repo / ".claude").symlink_to(outside, target_is_directory=True)

    with pytest.warns(UserWarning, match="outside project root"):
        rc = init.run(
            [str(repo), "--platform", "claude", "--no-hooks", "--no-superpowers"]
        )

    assert rc == 0
    assert (repo / ".context" / "INDEX.md").exists()
    assert outside_guidance.read_text(encoding="utf-8") == "# Outside rules\n"
