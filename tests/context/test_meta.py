"""Tests for dummyindex.context.meta."""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.meta import (
    SCHEMA_VERSION,
    Meta,
    new_meta,
    read_meta,
    write_meta,
)


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
    with pytest.raises(Exception):  # FrozenInstanceError subclasses AttributeError pre-3.11
        m.file_count = 99  # type: ignore[misc]


@pytest.mark.unit
def test_read_meta_missing_file_raises(tmp_repo: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_meta(tmp_repo / ".context" / "meta.json")


@pytest.mark.unit
def test_read_meta_future_schema_version_raises(tmp_repo: Path) -> None:
    path = tmp_repo / ".context" / "meta.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema_version": 9999, "dummyindex_version": "x", '
        '"created_at": "2026-01-01T00:00:00+00:00", '
        '"updated_at": "2026-01-01T00:00:00+00:00", '
        '"root": "/tmp"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="newer"):
        read_meta(path)


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
