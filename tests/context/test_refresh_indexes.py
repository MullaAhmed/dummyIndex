"""Tests for `dummyindex context refresh-indexes` — the post-enrichment
INDEX.md regenerator. Bug it fixes: after the skill renames feature
folders, the top-level INDEX.md still lists the old `community-N/...`
paths and every link 404s."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.cli import dispatch
from dummyindex.context.docs import refresh_index_md


_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


def _ingested(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(_FIXTURE, target)
    assert dispatch(["init", str(target)]) == 0
    return target


@pytest.mark.integration
def test_refresh_walks_disk_and_lists_renamed_features(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After renaming a feature, refresh-indexes regenerates INDEX.md so it
    references the new folder name, not the stub `community-N` one."""
    target = _ingested(tmp_path, "refresh_basic")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    from_id = idx["features"][0]["feature_id"]

    monkeypatch.chdir(target)
    assert dispatch(
        [
            "features-rename",
            "--from",
            from_id,
            "--to",
            "user-flow",
            "--name",
            "User Flow",
        ]
    ) == 0

    # Sanity check the precondition the bug surfaced: INDEX.md still lists
    # the stub path because it was written at ingest time.
    pre = (target / ".context" / "INDEX.md").read_text(encoding="utf-8")
    assert f"features/{from_id}/" in pre

    rels = refresh_index_md(target / ".context")
    assert "INDEX.md" not in rels  # INDEX.md excludes itself

    post = (target / ".context" / "INDEX.md").read_text(encoding="utf-8")
    assert f"features/{from_id}/" not in post
    assert "features/user-flow/" in post


@pytest.mark.integration
def test_refresh_excludes_cache_and_tmp(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "refresh_excludes")
    # Drop a fake tmp file + ensure cache/ items exist.
    (target / ".context" / "junk.tmp").write_text("x", encoding="utf-8")
    cache_dir = target / ".context" / "cache"
    cache_dir.mkdir(exist_ok=True)
    (cache_dir / "fake.json").write_text("{}", encoding="utf-8")

    rels = refresh_index_md(target / ".context")
    assert all(not r.endswith(".tmp") for r in rels)
    assert all(not r.startswith("cache/") for r in rels)


@pytest.mark.integration
def test_refresh_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "refresh_cli")
    capsys.readouterr()
    monkeypatch.chdir(target)
    rc = dispatch(["refresh-indexes"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "INDEX.md" in out


@pytest.mark.integration
def test_refresh_errors_when_no_context_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = tmp_path / "empty"
    bare.mkdir()
    monkeypatch.chdir(bare)
    rc = dispatch(["refresh-indexes"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err
