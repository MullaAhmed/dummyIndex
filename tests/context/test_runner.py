"""Tests for dummyindex.context.runner — end-to-end build_all flow."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.runner import BuildResult, build_all

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


@pytest.mark.integration
def test_build_all_returns_build_result(sample_repo: Path, tmp_path: Path) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    assert isinstance(result, BuildResult)
    assert result.root == sample_repo
    assert result.context_dir == sample_repo / ".context"
    assert result.file_count > 0
    assert result.symbol_count > 0


@pytest.mark.integration
def test_build_all_writes_every_expected_file(
    sample_repo: Path, tmp_path: Path
) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    expected = {
        "meta.json",
        "map/files.json",
        "map/symbols.json",
        "tree.json",
        "conventions/naming.json",
        "conventions/naming.md",
        "PROJECT.md",
        "INDEX.md",
    }
    assert expected <= set(result.written)
    for rel in expected:
        assert (result.context_dir / rel).exists(), f"missing {rel}"


@pytest.mark.integration
def test_build_all_writes_meta_with_real_counts(
    sample_repo: Path, tmp_path: Path
) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    meta_payload = json.loads(
        (result.context_dir / "meta.json").read_text(encoding="utf-8")
    )
    assert meta_payload["file_count"] == result.file_count
    assert meta_payload["symbol_count"] == result.symbol_count
    assert sorted(meta_payload["languages"]) == sorted(result.languages)


@pytest.mark.integration
def test_build_all_with_bootstrap_writes_claude_md(
    sample_repo: Path, tmp_path: Path
) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache", bootstrap=True)
    assert result.bootstrapped is True
    claude_md = sample_repo / "CLAUDE.md"
    assert claude_md.exists()
    assert "dummyindex" in claude_md.read_text(encoding="utf-8")


@pytest.mark.integration
def test_build_all_without_bootstrap_skips_claude_md(
    sample_repo: Path, tmp_path: Path
) -> None:
    build_all(sample_repo, cache_root=tmp_path / "cache", bootstrap=False)
    assert not (sample_repo / "CLAUDE.md").exists()


@pytest.mark.integration
def test_build_all_languages_inferred(sample_repo: Path, tmp_path: Path) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    assert "python" in result.languages
    assert "typescript" in result.languages


@pytest.mark.integration
def test_index_md_lists_what_was_written(
    sample_repo: Path, tmp_path: Path
) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    index_text = (result.context_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "tree.json" in index_text
    assert "map/symbols.json" in index_text
    assert "conventions/naming.md" in index_text


@pytest.mark.integration
def test_second_run_is_idempotent_in_content(
    sample_repo: Path, tmp_path: Path
) -> None:
    first = build_all(sample_repo, cache_root=tmp_path / "cache")
    files_first = (first.context_dir / "map" / "files.json").read_text(encoding="utf-8")
    symbols_first = (first.context_dir / "map" / "symbols.json").read_text(encoding="utf-8")
    tree_first = (first.context_dir / "tree.json").read_text(encoding="utf-8")

    build_all(sample_repo, cache_root=tmp_path / "cache")
    files_second = (first.context_dir / "map" / "files.json").read_text(encoding="utf-8")
    symbols_second = (first.context_dir / "map" / "symbols.json").read_text(encoding="utf-8")
    tree_second = (first.context_dir / "tree.json").read_text(encoding="utf-8")

    # Files/symbols/tree are deterministic — should round-trip identically
    assert files_first == files_second
    assert symbols_first == symbols_second
    assert tree_first == tree_second
