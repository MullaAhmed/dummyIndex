"""Tests for dummyindex.context.instructions — HOW_TO_USE / architecture / playbooks."""
from __future__ import annotations

import shutil
from pathlib import Path

from tests.paths import SAMPLE_REPO

import pytest

from dummyindex.context.output.instructions import (
    PLAYBOOK_IDS,
    generate_architecture_overview_md,
    generate_how_to_use_md,
    generate_playbook_md,
    write_how_to_use_md,
    write_playbook_md,
)
from dummyindex.context.build.maps import (
    FileEntry,
    FilesMap,
    SymbolEntry,
    SymbolsMap,
)
from dummyindex.context.build.meta import Meta, SCHEMA_VERSION
from dummyindex.context.build.runner import build_all

_FIXTURE_ROOT = SAMPLE_REPO


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


def _meta(root: Path, **overrides) -> Meta:
    base = dict(
        schema_version=SCHEMA_VERSION,
        dummyindex_version="0.0.0-test",
        created_at="2026-05-24T00:00:00+00:00",
        updated_at="2026-05-24T00:00:00+00:00",
        root=str(root.resolve()),
        languages=("python", "typescript"),
        file_count=3,
        symbol_count=7,
    )
    base.update(overrides)
    return Meta(**base)


# --- HOW_TO_USE.md -----------------------------------------------------------


@pytest.mark.unit
def test_how_to_use_md_contains_navigation_table() -> None:
    text = generate_how_to_use_md()
    assert "# How to use" in text
    assert "PROJECT.md" in text
    assert "map/symbols.json" in text
    assert "conventions/naming.md" in text
    assert "playbooks/" in text


@pytest.mark.unit
def test_how_to_use_md_includes_rebuild_instruction() -> None:
    text = generate_how_to_use_md()
    assert "dummyindex context rebuild --changed" in text


@pytest.mark.unit
def test_write_how_to_use_md_atomic(tmp_path: Path) -> None:
    out = tmp_path / ".context" / "HOW_TO_USE.md"
    write_how_to_use_md(out)
    assert out.exists()
    assert not list(out.parent.glob("HOW_TO_USE.md.tmp"))


# --- architecture/overview.md ------------------------------------------------


@pytest.mark.unit
def test_architecture_overview_basic(tmp_path: Path) -> None:
    repo = tmp_path / "demo"
    repo.mkdir()
    files = FilesMap(
        schema_version=1,
        files=(
            FileEntry(path="src/app.py", language="python", size_bytes=100, sha256="a" * 64),
            FileEntry(path="src/utils.py", language="python", size_bytes=50, sha256="b" * 64),
            FileEntry(path="tests/test_app.py", language="python", size_bytes=80, sha256="c" * 64),
            FileEntry(path="README.md", language=None, size_bytes=200, sha256="d" * 64),
        ),
    )
    symbols = SymbolsMap(
        schema_version=1,
        symbols=(
            SymbolEntry(symbol_id="s1", kind="class", name="App", path="src/app.py"),
            SymbolEntry(symbol_id="s2", kind="function", name="run", path="src/app.py"),
            SymbolEntry(symbol_id="s3", kind="function", name="helper", path="src/utils.py"),
        ),
    )
    meta = _meta(repo)
    text = generate_architecture_overview_md(repo, files, symbols, meta)
    assert "# Architecture overview" in text
    assert "`src/`" in text
    assert "`tests/`" in text
    # Heuristic role hints
    assert "source code" in text
    assert "test suite" in text
    # Repo-root files listed
    assert "`README.md`" in text


@pytest.mark.unit
def test_architecture_overview_no_subdirs(tmp_path: Path) -> None:
    repo = tmp_path / "flat"
    repo.mkdir()
    files = FilesMap(
        schema_version=1,
        files=(
            FileEntry(path="main.py", language="python", size_bytes=80, sha256="a" * 64),
        ),
    )
    symbols = SymbolsMap(schema_version=1, symbols=())
    meta = _meta(repo, file_count=1, symbol_count=0)
    text = generate_architecture_overview_md(repo, files, symbols, meta)
    assert "No subdirectories detected" in text
    assert "`main.py`" in text


@pytest.mark.unit
def test_architecture_overview_unknown_dir_no_role_hint(tmp_path: Path) -> None:
    repo = tmp_path / "x"
    repo.mkdir()
    files = FilesMap(
        schema_version=1,
        files=(
            FileEntry(path="random_dirname/x.py", language="python", size_bytes=10, sha256="a" * 64),
        ),
    )
    text = generate_architecture_overview_md(
        repo, files, SymbolsMap(schema_version=1, symbols=()), _meta(repo)
    )
    assert "`random_dirname/`" in text
    assert "_unknown_" in text


# --- playbooks ---------------------------------------------------------------


@pytest.mark.unit
def test_playbook_ids_complete() -> None:
    expected = {"add-feature", "add-endpoint", "add-migration", "fix-bug", "refactor"}
    assert set(PLAYBOOK_IDS) == expected


@pytest.mark.unit
@pytest.mark.parametrize("pid", ["add-feature", "add-endpoint", "add-migration", "fix-bug", "refactor"])
def test_playbook_returns_content(pid: str) -> None:
    text = generate_playbook_md(pid)
    assert text.startswith("# Playbook")
    assert len(text) > 200


@pytest.mark.unit
def test_playbook_references_index_files() -> None:
    text = generate_playbook_md("add-feature")
    assert "map/symbols.json" in text
    assert "conventions/naming.md" in text


@pytest.mark.unit
def test_unknown_playbook_raises() -> None:
    with pytest.raises(KeyError):
        generate_playbook_md("not-a-real-playbook")


@pytest.mark.unit
def test_write_playbook_atomic(tmp_path: Path) -> None:
    out = tmp_path / "playbooks" / "add-feature.md"
    write_playbook_md(out, "add-feature")
    assert out.exists()
    assert not list(out.parent.glob("*.tmp"))


# --- End-to-end via build_all -------------------------------------------------


@pytest.mark.integration
def test_build_all_writes_instruction_files(sample_repo: Path) -> None:
    result = build_all(sample_repo, dummyindex_version="0.0.0-test")
    assert (sample_repo / ".context" / "HOW_TO_USE.md").exists()
    assert (sample_repo / ".context" / "architecture" / "overview.md").exists()
    for pid in PLAYBOOK_IDS:
        assert (sample_repo / ".context" / "playbooks" / f"{pid}.md").exists()

    # Index listed in build result
    written = set(result.written)
    assert "HOW_TO_USE.md" in written
    assert "architecture/overview.md" in written
    for pid in PLAYBOOK_IDS:
        assert f"playbooks/{pid}.md" in written


@pytest.mark.integration
def test_build_all_index_md_lists_instructions(sample_repo: Path) -> None:
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    index_text = (sample_repo / ".context" / "INDEX.md").read_text(encoding="utf-8")
    assert "HOW_TO_USE.md" in index_text
    assert "architecture/overview.md" in index_text
    assert "playbooks/add-feature.md" in index_text


@pytest.mark.integration
def test_claude_md_block_points_at_how_to_use(
    sample_repo: Path,
) -> None:
    """The managed block is a pointer at HOW_TO_USE.md; detailed navigation
    rules (playbooks, conventions, the graph) live there, not in CLAUDE.md."""
    build_all(sample_repo, bootstrap=True, dummyindex_version="0.0.0-test")
    block = (sample_repo / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "HOW_TO_USE.md" in block
    # The detailed references migrated to HOW_TO_USE.md — verify they're there:
    how_to_use = (sample_repo / ".context" / "HOW_TO_USE.md").read_text(encoding="utf-8")
    assert "playbooks/" in how_to_use
    assert "conventions/naming.md" in how_to_use
