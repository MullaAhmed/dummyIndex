"""Tests for dummyindex.context.maps."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from tests.paths import SAMPLE_REPO

import pytest

from dummyindex.context.build.maps import (
    SCHEMA_VERSION,
    FilesMap,
    SymbolsMap,
    build_maps,
    write_files_map,
    write_symbols_map,
)

_FIXTURE_ROOT = SAMPLE_REPO


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Copy the static fixture into tmp_path so cache writes don't pollute the repo."""
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


@pytest.mark.integration
def test_build_maps_returns_both_maps(sample_repo: Path, tmp_path: Path) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    assert isinstance(files_map, FilesMap)
    assert isinstance(symbols_map, SymbolsMap)
    assert files_map.schema_version == SCHEMA_VERSION
    assert symbols_map.schema_version == SCHEMA_VERSION


@pytest.mark.integration
def test_files_map_lists_every_source_file(sample_repo: Path, tmp_path: Path) -> None:
    files_map, _ = build_maps(sample_repo, cache_root=tmp_path / "cache")
    paths = {f.path for f in files_map.files}
    assert "app.py" in paths
    assert "helpers.py" in paths
    assert "web/app.ts" in paths


@pytest.mark.integration
def test_files_map_languages_inferred_from_extension(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, _ = build_maps(sample_repo, cache_root=tmp_path / "cache")
    by_path = {f.path: f for f in files_map.files}
    assert by_path["app.py"].language == "python"
    assert by_path["helpers.py"].language == "python"
    assert by_path["web/app.ts"].language == "typescript"


@pytest.mark.integration
def test_files_map_entries_have_size_and_sha256(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, _ = build_maps(sample_repo, cache_root=tmp_path / "cache")
    for entry in files_map.files:
        assert entry.size_bytes > 0
        assert len(entry.sha256) == 64  # sha256 hex digest length
        assert entry.loc > 0


@pytest.mark.integration
def test_files_map_paths_are_posix_and_relative(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, _ = build_maps(sample_repo, cache_root=tmp_path / "cache")
    for entry in files_map.files:
        assert "\\" not in entry.path
        assert not entry.path.startswith("/")
        assert not entry.path.startswith(str(sample_repo))


@pytest.mark.integration
def test_symbols_map_contains_python_class_and_methods(
    sample_repo: Path, tmp_path: Path
) -> None:
    _, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    names_by_kind: dict[str, set[str]] = {}
    for s in symbols_map.symbols:
        names_by_kind.setdefault(s.kind, set()).add(s.name)
    assert "App" in names_by_kind.get("class", set())
    assert "run" in names_by_kind.get("method", set())


@pytest.mark.integration
def test_symbols_map_contains_top_level_function(
    sample_repo: Path, tmp_path: Path
) -> None:
    _, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    functions = {s.name for s in symbols_map.symbols if s.kind == "function"}
    assert "make_app" in functions
    assert "format_currency" in functions


@pytest.mark.integration
def test_symbols_map_method_has_class_parent(
    sample_repo: Path, tmp_path: Path
) -> None:
    _, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    methods = [s for s in symbols_map.symbols if s.kind == "method" and s.name == "run"]
    assert methods, "expected method 'run' in symbols map"
    parent_id = methods[0].parent
    assert parent_id is not None
    parent_class = next(
        (s for s in symbols_map.symbols if s.symbol_id == parent_id),
        None,
    )
    assert parent_class is not None
    assert parent_class.kind == "class"
    assert parent_class.name == "App"


@pytest.mark.integration
def test_symbols_map_exported_flag(sample_repo: Path, tmp_path: Path) -> None:
    _, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    by_name = {s.name: s for s in symbols_map.symbols}
    assert by_name.get("make_app") is not None
    assert by_name["make_app"].exported is True
    if "_private_helper" in by_name:
        assert by_name["_private_helper"].exported is False


@pytest.mark.integration
def test_symbols_map_paths_are_posix(sample_repo: Path, tmp_path: Path) -> None:
    _, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    for s in symbols_map.symbols:
        assert "\\" not in s.path


@pytest.mark.integration
def test_symbols_map_range_is_start_line(sample_repo: Path, tmp_path: Path) -> None:
    _, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    ranged = [s for s in symbols_map.symbols if s.range is not None]
    assert ranged, "expected at least one symbol with a known range"
    for s in ranged:
        start, end = s.range  # type: ignore[misc]
        assert start >= 1
        assert end >= start  # v0: end == start (PR 3 computes real ranges)


@pytest.mark.integration
def test_writers_round_trip_files_map(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, _ = build_maps(sample_repo, cache_root=tmp_path / "cache")
    out = tmp_path / ".context" / "map" / "files.json"
    write_files_map(out, files_map)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert {entry["path"] for entry in payload["files"]} == {
        f.path for f in files_map.files
    }


@pytest.mark.integration
def test_writers_round_trip_symbols_map(
    sample_repo: Path, tmp_path: Path
) -> None:
    _, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    out = tmp_path / ".context" / "map" / "symbols.json"
    write_symbols_map(out, symbols_map)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    written_ids = {s["symbol_id"] for s in payload["symbols"]}
    assert written_ids == {s.symbol_id for s in symbols_map.symbols}


@pytest.mark.integration
def test_writer_is_atomic_no_tmp_remains(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, _ = build_maps(sample_repo, cache_root=tmp_path / "cache")
    out = tmp_path / ".context" / "map" / "files.json"
    write_files_map(out, files_map)
    assert out.exists()
    assert not list(out.parent.glob("files.json.tmp"))


@pytest.mark.integration
def test_build_maps_is_fast_enough_for_fixture(
    sample_repo: Path, tmp_path: Path
) -> None:
    start = time.perf_counter()
    build_maps(sample_repo, cache_root=tmp_path / "cache")
    elapsed = time.perf_counter() - start
    # Generous: detecting + extracting 3 small files should be well under 5 s.
    assert elapsed < 5.0, f"build_maps took {elapsed:.2f}s on fixture (expected <5s)"
