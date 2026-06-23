"""Tests for dummyindex.context.tree."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.build.tree import (
    SCHEMA_VERSION,
    Tree,
    TreeNode,
    build_tree,
    iter_nodes,
    write_tree,
)
from dummyindex.pipeline.enums import ConfidenceLevel
from tests.paths import SAMPLE_REPO

_FIXTURE_ROOT = SAMPLE_REPO


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


def _kinds(tree: Tree) -> set[str]:
    return {n.kind for n in iter_nodes(tree.root)}


def _by_title(tree: Tree) -> dict[str, list[TreeNode]]:
    result: dict[str, list[TreeNode]] = {}
    for n in iter_nodes(tree.root):
        result.setdefault(n.title, []).append(n)
    return result


@pytest.mark.integration
def test_build_tree_returns_tree(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    assert isinstance(tree, Tree)
    assert tree.schema_version == SCHEMA_VERSION


@pytest.mark.integration
def test_root_is_project_node(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    assert tree.root.kind == "project"
    assert tree.root.title == "sample_repo"
    assert tree.root.node_id.startswith("n-prj-")
    assert tree.root.path == "."


@pytest.mark.integration
def test_tree_contains_expected_kinds(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    kinds = _kinds(tree)
    assert "project" in kinds
    assert "dir" in kinds
    assert "file" in kinds
    assert "class" in kinds
    assert "function" in kinds
    assert "method" in kinds


@pytest.mark.integration
def test_dir_node_for_web_directory(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    by_title = _by_title(tree)
    web_nodes = [n for n in by_title.get("web", []) if n.kind == "dir"]
    assert web_nodes, "expected a dir node titled 'web'"
    assert web_nodes[0].path == "web"
    assert web_nodes[0].node_id.startswith("n-dir-")


@pytest.mark.integration
def test_file_nodes_at_top_level(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    top_files = [c for c in tree.root.children if c.kind == "file"]
    titles = {c.title for c in top_files}
    assert "app.py" in titles
    assert "helpers.py" in titles


@pytest.mark.integration
def test_web_app_ts_under_web_dir(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    web_dir = next(
        c for c in tree.root.children if c.kind == "dir" and c.title == "web"
    )
    file_titles = {c.title for c in web_dir.children if c.kind == "file"}
    assert "app.ts" in file_titles


@pytest.mark.integration
def test_class_has_methods_as_children(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    by_title = _by_title(tree)
    app_classes = [n for n in by_title.get("App", []) if n.kind == "class"]
    assert app_classes, "expected class 'App' in tree"
    method_titles = {c.title for c in app_classes[0].children if c.kind == "method"}
    assert "run" in method_titles
    assert "__init__" in method_titles


@pytest.mark.integration
def test_top_level_function_under_file(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    by_title = _by_title(tree)
    files = [n for n in by_title.get("helpers.py", []) if n.kind == "file"]
    assert files, "expected file 'helpers.py' in tree"
    fn_titles = {c.title for c in files[0].children if c.kind == "function"}
    assert "format_currency" in fn_titles
    assert "parse_amount" in fn_titles


@pytest.mark.integration
def test_every_node_has_required_fields(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    for node in iter_nodes(tree.root):
        assert node.node_id, f"empty node_id on {node!r}"
        assert node.kind, f"empty kind on {node!r}"
        assert node.title, f"empty title on {node!r}"
        assert node.abstract, f"empty abstract on {node!r}"
        assert node.confidence == ConfidenceLevel.EXTRACTED


@pytest.mark.integration
def test_node_ids_are_unique(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    ids = [n.node_id for n in iter_nodes(tree.root)]
    assert len(ids) == len(set(ids)), "duplicate node_ids in tree"


@pytest.mark.integration
def test_symbol_nodes_have_line_range(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    leaf_kinds = {"class", "function", "method"}
    leaf_nodes = [n for n in iter_nodes(tree.root) if n.kind in leaf_kinds]
    with_range = [n for n in leaf_nodes if n.range is not None]
    assert with_range, "expected at least one leaf with a line range"
    for n in with_range:
        start, end = n.range  # type: ignore[misc]
        assert start >= 1
        assert end >= start


@pytest.mark.integration
def test_write_tree_roundtrip(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    out = tmp_path / ".context" / "tree.json"
    write_tree(out, tree)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["root"]["kind"] == "project"
    assert payload["root"]["title"] == "sample_repo"
    children_kinds = {c["kind"] for c in payload["root"]["children"]}
    assert {"dir", "file"} <= children_kinds


@pytest.mark.integration
def test_write_tree_atomic_no_tmp_remains(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    out = tmp_path / ".context" / "tree.json"
    write_tree(out, tree)
    assert out.exists()
    assert not list(out.parent.glob("tree.json.tmp"))


@pytest.mark.integration
def test_project_root_id_uses_slug(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    assert tree.root.node_id == "n-prj-sample_repo"


@pytest.mark.integration
def test_dir_ids_use_path_slug(sample_repo: Path, tmp_path: Path) -> None:
    tree = build_tree(sample_repo, cache_root=tmp_path / "cache")
    web = next(c for c in tree.root.children if c.kind == "dir" and c.title == "web")
    assert web.node_id == "n-dir-web"
