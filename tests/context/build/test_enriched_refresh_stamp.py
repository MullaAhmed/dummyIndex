"""The version stamp can be left alone by a deterministic refresh."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.build import enriched_refresh
from dummyindex.context.build.enriched_refresh import (
    advance_version_stamp,
    refresh_deterministic_artifacts,
)
from dummyindex.context.build.meta import SCHEMA_VERSION
from dummyindex.context.build.runner import build_all


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src/main.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    build_all(root)
    return root


def _seed_meta(root: Path) -> Path:
    meta_path = root / ".context/meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(dummyindex_version="0.36.0", schema_version=1)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return meta_path


@pytest.mark.integration
def test_advance_stamp_false_leaves_version_and_schema(tmp_path):
    root = _repo(tmp_path)
    meta_path = _seed_meta(root)

    result = refresh_deterministic_artifacts(
        root, dummyindex_version="9.9.9", advance_stamp=False
    )

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["dummyindex_version"] == "0.36.0"
    assert meta["schema_version"] == 1
    assert result.failed == ()
    # The rest of the refresh still runs.
    assert "map/files.json" in result.written
    # The extraction cache is still scoped to the running version, not the stamp.
    cache_stamp = root / ".context/cache/extraction-version"
    assert cache_stamp.read_text(encoding="utf-8").strip() == "9.9.9"


@pytest.mark.integration
def test_default_advances_version_and_schema(tmp_path):
    root = _repo(tmp_path)
    meta_path = _seed_meta(root)

    refresh_deterministic_artifacts(root, dummyindex_version="9.9.9")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["dummyindex_version"] == "9.9.9"
    assert meta["schema_version"] == SCHEMA_VERSION


@pytest.mark.unit
def test_private_stamp_name_is_alias_of_public_function():
    assert enriched_refresh._advance_version_stamp is advance_version_stamp
