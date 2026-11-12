"""Tests for dummyindex.context.meta."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from dummyindex.context.build.enriched_refresh import refresh_deterministic_artifacts
from dummyindex.context.build.meta import (
    SCHEMA_VERSION,
    Meta,
    new_meta,
    read_meta,
    write_meta,
)
from dummyindex.context.build.runner import build_all


@pytest.mark.unit
def test_new_meta_has_current_schema_version(tmp_repo: Path) -> None:
    m = new_meta(tmp_repo, dummyindex_version="0.0.0-test")
    assert m.schema_version == SCHEMA_VERSION
    assert m.root == str(tmp_repo.resolve())
    assert m.created_at == m.updated_at
    assert m.file_count == 0
    assert m.symbol_count == 0
    assert m.languages == ()
    assert m.config == {}


@pytest.mark.unit
def test_meta_roundtrip(tmp_repo: Path) -> None:
    original = new_meta(tmp_repo, dummyindex_version="0.0.0-test")
    path = tmp_repo / ".context" / "meta.json"
    write_meta(path, original)
    loaded = read_meta(path)
    assert loaded == original


@pytest.mark.unit
def test_meta_with_languages_and_counts_roundtrip(tmp_repo: Path) -> None:
    original = Meta(
        schema_version=SCHEMA_VERSION,
        dummyindex_version="0.0.0-test",
        created_at="2026-05-24T00:00:00+00:00",
        updated_at="2026-05-24T00:00:00+00:00",
        root=str(tmp_repo.resolve()),
        languages=("python", "typescript"),
        file_count=42,
        symbol_count=128,
        config={"depth": "class"},
    )
    path = tmp_repo / ".context" / "meta.json"
    write_meta(path, original)
    loaded = read_meta(path)
    assert loaded == original


@pytest.mark.unit
def test_with_updates_returns_new_frozen_instance(tmp_repo: Path) -> None:
    original = new_meta(tmp_repo, dummyindex_version="0.0.0-test")
    updated = original.with_updates(file_count=42, symbol_count=128)
    assert updated is not original
    assert updated.file_count == 42
    assert updated.symbol_count == 128
    assert original.file_count == 0
    assert updated.created_at == original.created_at


@pytest.mark.unit
def test_meta_is_immutable() -> None:
    m = Meta(
        schema_version=SCHEMA_VERSION,
        dummyindex_version="0.0.0-test",
        created_at="x",
        updated_at="x",
        root="/tmp",
    )
    with pytest.raises(FrozenInstanceError):
        m.file_count = 99  # type: ignore[misc]


@pytest.mark.unit
def test_read_meta_missing_file_raises(tmp_repo: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_meta(tmp_repo / ".context" / "meta.json")


@pytest.mark.unit
def test_new_meta_writes_schema_2(tmp_repo: Path) -> None:
    assert SCHEMA_VERSION == 2
    assert new_meta(tmp_repo, dummyindex_version="0.0.0-test").schema_version == 2


@pytest.mark.unit
def test_read_meta_still_loads_schema_v1(tmp_repo: Path) -> None:
    path = tmp_repo / ".context" / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema_version": 1, "dummyindex_version": "0.37.0", '
        '"created_at": "2026-01-01T00:00:00+00:00", '
        '"updated_at": "2026-01-01T00:00:00+00:00", '
        '"root": "."}',
        encoding="utf-8",
    )
    loaded = read_meta(path)
    assert loaded.schema_version == 1
    assert loaded.dummyindex_version == "0.37.0"


@pytest.mark.unit
@pytest.mark.parametrize("version", [SCHEMA_VERSION + 1, 9999])
def test_read_meta_future_schema_version_raises(tmp_repo: Path, version: int) -> None:
    path = tmp_repo / ".context" / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        f'{{"schema_version": {version}, "dummyindex_version": "x", '
        '"created_at": "2026-01-01T00:00:00+00:00", '
        '"updated_at": "2026-01-01T00:00:00+00:00", '
        '"root": "/tmp"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="newer than this dummyindex build") as err:
        read_meta(path)
    assert "upgrade dummyindex" in str(err.value)


@pytest.mark.unit
def test_read_meta_non_object_raises(tmp_repo: Path) -> None:
    path = tmp_repo / ".context" / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        read_meta(path)


@pytest.mark.unit
def test_read_meta_missing_required_field_raises(tmp_repo: Path) -> None:
    path = tmp_repo / ".context" / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema_version": 1, "dummyindex_version": "x", '
        '"created_at": "2026-01-01T00:00:00+00:00"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required"):
        read_meta(path)


@pytest.mark.unit
def test_read_meta_missing_schema_version_raises(tmp_repo: Path) -> None:
    path = tmp_repo / ".context" / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"dummyindex_version": "x", "created_at": "x", "updated_at": "x", "root": "/"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema_version"):
        read_meta(path)


@pytest.mark.unit
def test_write_meta_is_atomic_no_tmp_remains(tmp_repo: Path) -> None:
    path = tmp_repo / ".context" / "meta.json"
    m = new_meta(tmp_repo, dummyindex_version="0.0.0-test")
    write_meta(path, m)
    assert path.exists()
    assert not list(path.parent.glob("meta.json.tmp"))


@pytest.mark.unit
def test_write_meta_creates_parent_dirs(tmp_repo: Path) -> None:
    path = tmp_repo / "deeply" / "nested" / ".context" / "meta.json"
    m = new_meta(tmp_repo, dummyindex_version="0.0.0-test")
    write_meta(path, m)
    assert path.exists()


@pytest.mark.unit
def test_restyled_ruleset_roundtrip(tmp_repo: Path) -> None:
    original = replace(new_meta(tmp_repo, dummyindex_version="0.0.0-test"), restyled_ruleset=1)
    path = tmp_repo / ".context" / "meta.json"
    write_meta(path, original)
    assert read_meta(path).restyled_ruleset == 1


@pytest.mark.unit
def test_restyled_ruleset_missing_key_reads_none(tmp_repo: Path) -> None:
    path = tmp_repo / ".context" / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema_version": 2, "dummyindex_version": "x", '
        '"created_at": "2026-01-01T00:00:00+00:00", '
        '"updated_at": "2026-01-01T00:00:00+00:00", "root": "."}',
        encoding="utf-8",
    )
    assert read_meta(path).restyled_ruleset is None


@pytest.mark.unit
@pytest.mark.parametrize("raw", ['"1"', "true", "null"])
def test_restyled_ruleset_non_int_reads_none(tmp_repo: Path, raw: str) -> None:
    path = tmp_repo / ".context" / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema_version": 2, "dummyindex_version": "x", '
        '"created_at": "x", "updated_at": "x", "root": ".", '
        f'"restyled_ruleset": {raw}}}',
        encoding="utf-8",
    )
    assert read_meta(path).restyled_ruleset is None


@pytest.mark.integration
def test_restyled_ruleset_survives_version_restamp(tmp_repo: Path) -> None:
    """Real enriched_refresh restamp path (:337) must keep restyled_ruleset."""
    root = tmp_repo
    (root / "src").mkdir()
    (root / "src/main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    build_all(root)
    meta_path = root / ".context" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["restyled_ruleset"] = 1
    meta["dummyindex_version"] = "0.0.1"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    refresh_deterministic_artifacts(root, dummyindex_version="9.9.9")

    assert read_meta(meta_path).restyled_ruleset == 1
    assert read_meta(meta_path).dummyindex_version == "9.9.9"
