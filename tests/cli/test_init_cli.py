"""Tests for `dummyindex context init` (== `ingest`) enriched-index guard.

`init`/`ingest` means "first build". An enriched index proves it is NOT the
first build, so init must refuse to overwrite it unless `--force` is passed.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.paths import SAMPLE_REPO

from dummyindex.cli import init
from dummyindex.context.build.runner import build_all
from dummyindex.context.domains.features import rename_feature

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
    index_before = (
        primed_repo / ".context" / "features" / "INDEX.json"
    ).read_text(encoding="utf-8")

    rc = init.run([str(primed_repo)])

    assert rc == 2
    err = capsys.readouterr().err
    assert "curated index detected" in err
    assert "--force" in err
    index_after = (
        primed_repo / ".context" / "features" / "INDEX.json"
    ).read_text(encoding="utf-8")
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
def test_init_proceeds_on_fresh_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fresh = tmp_path / "fresh"
    shutil.copytree(_FIXTURE_ROOT, fresh)
    rc = init.run([str(fresh), "--no-hooks"])
    assert rc == 0
    assert (fresh / ".context").is_dir()
