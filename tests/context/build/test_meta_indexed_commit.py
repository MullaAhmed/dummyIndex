"""``meta.json`` records ``indexed_commit`` — the git HEAD at index time.

Uses a throwaway ``git init`` + commit under ``tmp_path`` so the test
never depends on the host repo's HEAD.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.build.meta import Meta, read_meta, write_meta
from dummyindex.context.build.runner import build_all
from tests.paths import SAMPLE_REPO

_FIXTURE_ROOT = SAMPLE_REPO


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.integration
def test_build_all_records_head_in_a_real_git_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(_FIXTURE_ROOT, repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    head = _git(repo, "rev-parse", "HEAD").strip()

    build_all(repo, cache_root=tmp_path / "cache")

    meta = read_meta(repo / ".context" / "meta.json")
    assert meta.indexed_commit == head


@pytest.mark.integration
def test_build_all_records_none_off_git(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(_FIXTURE_ROOT, repo)  # no `git init`
    build_all(repo, cache_root=tmp_path / "cache")
    meta = read_meta(repo / ".context" / "meta.json")
    assert meta.indexed_commit is None


@pytest.mark.unit
def test_indexed_commit_roundtrips_through_io(tmp_path: Path) -> None:
    meta = Meta(
        schema_version=1,
        dummyindex_version="0.15.2",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        root=str(tmp_path),
        indexed_commit="abc1234",
    )
    path = tmp_path / "meta.json"
    write_meta(path, meta)
    assert read_meta(path).indexed_commit == "abc1234"


@pytest.mark.unit
def test_read_meta_tolerates_missing_field(tmp_path: Path) -> None:
    # An index written by a pre-0.15.2 dummyindex has no indexed_commit.
    path = tmp_path / "meta.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dummyindex_version": "0.15.1",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "root": str(tmp_path),
            }
        ),
        encoding="utf-8",
    )
    assert read_meta(path).indexed_commit is None
