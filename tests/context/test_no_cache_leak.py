"""Verify dummyindex v0 keeps all generated artifacts inside .context/."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from dummyindex.context.build.runner import build_all

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


@pytest.mark.integration
def test_cache_lives_inside_context_dir(sample_repo: Path) -> None:
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    cache = sample_repo / ".context" / "cache"
    assert cache.exists() and cache.is_dir()
    # At least one cache entry per extracted file
    entries = list(cache.glob("*.json"))
    assert entries, "expected cache entries inside .context/cache/"


@pytest.mark.integration
def test_context_gitignore_excludes_cache(sample_repo: Path) -> None:
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    gi = sample_repo / ".context" / ".gitignore"
    assert gi.exists()
    assert "cache/" in gi.read_text(encoding="utf-8")


@pytest.mark.integration
def test_cache_env_var_is_restored(sample_repo: Path) -> None:
    prior = os.environ.get("DUMMYINDEX_CACHE_DIR")
    try:
        os.environ["DUMMYINDEX_CACHE_DIR"] = "/tmp/some_prior_value"
        build_all(sample_repo, dummyindex_version="0.0.0-test")
        assert os.environ["DUMMYINDEX_CACHE_DIR"] == "/tmp/some_prior_value"
    finally:
        if prior is None:
            os.environ.pop("DUMMYINDEX_CACHE_DIR", None)
        else:
            os.environ["DUMMYINDEX_CACHE_DIR"] = prior


@pytest.mark.integration
def test_cache_env_var_unset_after_run_with_no_prior(sample_repo: Path) -> None:
    os.environ.pop("DUMMYINDEX_CACHE_DIR", None)
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    assert "DUMMYINDEX_CACHE_DIR" not in os.environ


@pytest.mark.integration
def test_user_added_gitignore_lines_preserved(sample_repo: Path) -> None:
    ctx = sample_repo / ".context"
    ctx.mkdir(parents=True)
    (ctx / ".gitignore").write_text("# user-added\nlocal-notes.md\n", encoding="utf-8")
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    gi_text = (ctx / ".gitignore").read_text(encoding="utf-8")
    assert "local-notes.md" in gi_text
    assert "cache/" in gi_text