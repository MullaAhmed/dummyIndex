"""Tests for the knowledge-graph output under .context/graph/."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.runner import build_all

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


@pytest.mark.integration
def test_build_all_writes_graph_json(sample_repo: Path) -> None:
    result = build_all(sample_repo, dummyindex_version="0.0.0-test")
    json_path = sample_repo / ".context" / "graph" / "graph.json"
    assert json_path.exists()
    assert "graph/graph.json" in result.written

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "nodes" in payload
    assert "links" in payload or "edges" in payload


@pytest.mark.integration
def test_build_all_graph_result_has_counts(sample_repo: Path) -> None:
    result = build_all(sample_repo, dummyindex_version="0.0.0-test")
    assert result.graph is not None
    assert result.graph.node_count > 0
    assert result.graph.community_count >= 1


@pytest.mark.integration
def test_build_all_writes_graph_html_for_small_repos(sample_repo: Path) -> None:
    result = build_all(sample_repo, dummyindex_version="0.0.0-test")
    # Fixture is well under MAX_NODES_FOR_VIZ (5000), so HTML should be written.
    assert result.graph is not None
    assert result.graph.html_path is not None
    assert result.graph.html_path.exists()
    assert "graph/graph.html" in result.written
    text = result.graph.html_path.read_text(encoding="utf-8")
    assert "<html" in text.lower()


@pytest.mark.integration
def test_graph_json_lives_under_context_dir(sample_repo: Path) -> None:
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    # Must NOT leak to dummyindex-out/
    assert not (sample_repo / "dummyindex-out").exists()
    # Must be inside .context/graph/
    assert (sample_repo / ".context" / "graph" / "graph.json").exists()


@pytest.mark.integration
def test_index_md_lists_graph_files(sample_repo: Path) -> None:
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    index_text = (sample_repo / ".context" / "INDEX.md").read_text(encoding="utf-8")
    assert "graph/graph.json" in index_text


@pytest.mark.integration
def test_claude_md_block_mentions_graph(sample_repo: Path) -> None:
    build_all(sample_repo, bootstrap=True, dummyindex_version="0.0.0-test")
    claude_md = (sample_repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "graph/graph.json" in claude_md or "graph.json" in claude_md
