"""Tests for dummyindex.context.docs — INDEX.md and PROJECT.md generators."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.output.docs import (
    generate_index_md,
    generate_project_md,
    write_index_md,
    write_project_md,
)
from dummyindex.context.build.meta import Meta, SCHEMA_VERSION


def _meta(root: Path, **overrides) -> Meta:
    base = dict(
        schema_version=SCHEMA_VERSION,
        dummyindex_version="0.0.0-test",
        created_at="2026-05-24T00:00:00+00:00",
        updated_at="2026-05-24T00:00:00+00:00",
        root=str(root.resolve()),
        languages=("python",),
        file_count=10,
        symbol_count=42,
    )
    base.update(overrides)
    return Meta(**base)


# --- generate_index_md -------------------------------------------------------


@pytest.mark.unit
def test_index_md_lists_provided_files() -> None:
    text = generate_index_md(["PROJECT.md", "tree.json", "map/files.json"])
    assert "# .context/" in text
    assert "`PROJECT.md`" in text
    assert "`tree.json`" in text
    assert "`map/files.json`" in text


@pytest.mark.unit
def test_index_md_includes_descriptions_for_known_files() -> None:
    text = generate_index_md(["conventions/naming.md"])
    assert "Derived naming rules" in text


@pytest.mark.unit
def test_index_md_handles_unknown_file() -> None:
    text = generate_index_md(["custom/extra.json"])
    assert "`custom/extra.json`" in text


# --- generate_project_md -----------------------------------------------------


@pytest.mark.unit
def test_project_md_with_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "myproj"
description = "A tiny project for testing."
version = "1.2.3"
""".strip(),
        encoding="utf-8",
    )
    meta = _meta(tmp_path)
    text = generate_project_md(tmp_path, meta)
    assert "# myproj" in text
    assert "_Version 1.2.3_" in text
    assert "A tiny project for testing." in text
    assert "**Languages:** python" in text
    assert "**Files:** 10" in text
    assert "**Symbols:** 42" in text


@pytest.mark.unit
def test_project_md_with_pyproject_scripts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "myproj"
description = "x"
version = "0.1.0"

[project.scripts]
mycli = "myproj.cli:main"
""".strip(),
        encoding="utf-8",
    )
    meta = _meta(tmp_path)
    text = generate_project_md(tmp_path, meta)
    assert "## Entry points" in text
    assert "`mycli` → `myproj.cli:main`" in text


@pytest.mark.unit
def test_project_md_with_package_json_only(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({
            "name": "my-pkg",
            "description": "A node package.",
            "version": "2.0.0",
        }),
        encoding="utf-8",
    )
    meta = _meta(tmp_path, languages=("typescript",))
    text = generate_project_md(tmp_path, meta)
    assert "# my-pkg" in text
    assert "_Version 2.0.0_" in text
    assert "A node package." in text
    assert "**Languages:** typescript" in text


@pytest.mark.unit
def test_project_md_with_no_manifest_uses_dir_name(tmp_path: Path) -> None:
    # Pure-directory fallback. Use a subdirectory so dir name is predictable.
    repo = tmp_path / "lonely_project"
    repo.mkdir()
    meta = _meta(repo)
    text = generate_project_md(repo, meta)
    assert "# lonely_project" in text
    assert "**Languages:** python" in text


@pytest.mark.unit
def test_project_md_falls_back_to_readme_description(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Project Title\n\nThis is the description paragraph from README.\n\nMore content.\n",
        encoding="utf-8",
    )
    meta = _meta(tmp_path)
    text = generate_project_md(tmp_path, meta)
    assert "This is the description paragraph from README." in text


@pytest.mark.unit
def test_project_md_ends_with_newline(tmp_path: Path) -> None:
    meta = _meta(tmp_path)
    text = generate_project_md(tmp_path, meta)
    assert text.endswith("\n")
    # No double-trailing newline
    assert not text.endswith("\n\n\n")


# --- Writers -----------------------------------------------------------------


@pytest.mark.unit
def test_write_index_md_atomic(tmp_path: Path) -> None:
    out = tmp_path / ".context" / "INDEX.md"
    write_index_md(out, generate_index_md(["PROJECT.md"]))
    assert out.exists()
    assert not list(out.parent.glob("INDEX.md.tmp"))


@pytest.mark.unit
def test_write_project_md_atomic(tmp_path: Path) -> None:
    out = tmp_path / ".context" / "PROJECT.md"
    meta = _meta(tmp_path)
    write_project_md(out, generate_project_md(tmp_path, meta))
    assert out.exists()
    assert not list(out.parent.glob("PROJECT.md.tmp"))
