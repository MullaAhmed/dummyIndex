"""Tests for `dummyindex context init` (== `ingest`) enriched-index guard.

`init`/`ingest` means "first build". An enriched index proves it is NOT the
first build, so init must refuse to overwrite it unless `--force` is passed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import init
from dummyindex.context.build.runner import build_all
from dummyindex.context.domains.features import rename_feature
from tests.paths import SAMPLE_REPO

_FIXTURE_ROOT = SAMPLE_REPO


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


# ----- default superpowers plugin wiring (Task 6) ---------------------------

_SUPERPOWERS = "superpowers@claude-plugins-official"


def _make_min_repo(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / ".git").mkdir()
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (target / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8"
    )


def _enabled(repo: Path) -> dict:
    settings = repo / ".claude" / "settings.json"
    if not settings.exists():
        return {}
    return json.loads(settings.read_text(encoding="utf-8")).get("enabledPlugins", {})


@pytest.mark.integration
def test_init_enables_superpowers_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    rc = init.run(["."])

    assert rc == 0
    assert _enabled(repo).get(_SUPERPOWERS) is True


@pytest.mark.integration
def test_init_no_superpowers_flag_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    rc = init.run(["--no-superpowers", "."])

    assert rc == 0
    assert _SUPERPOWERS not in _enabled(repo)


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
