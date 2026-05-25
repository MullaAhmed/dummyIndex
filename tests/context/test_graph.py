"""Tests for the knowledge-graph output under .context/features/.

v0.6+: the symbol graph lives at .context/features/symbol-graph.json (it used
to live at .context/graph/graph.json). The pyvis HTML hairball was dropped;
the human-facing visualization is .context/features/graph.html (built by
features.py, not by this module).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.build.runner import build_all

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


@pytest.mark.integration
def test_build_all_writes_symbol_graph_json(sample_repo: Path) -> None:
    result = build_all(sample_repo, dummyindex_version="0.0.0-test")
    json_path = sample_repo / ".context" / "features" / "symbol-graph.json"
    assert json_path.exists()
    assert "features/symbol-graph.json" in result.written

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
def test_legacy_graph_folder_is_not_created(sample_repo: Path) -> None:
    """v0.6: the .context/graph/ folder was retired. Symbol graph is under
    features/. pyvis HTML hairball is gone entirely."""
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    assert not (sample_repo / ".context" / "graph").exists()
    # Must NOT leak to dummyindex-out/ either.
    assert not (sample_repo / "dummyindex-out").exists()


@pytest.mark.integration
def test_index_md_lists_symbol_graph(sample_repo: Path) -> None:
    build_all(sample_repo, dummyindex_version="0.0.0-test")
    index_text = (sample_repo / ".context" / "INDEX.md").read_text(encoding="utf-8")
    assert "features/symbol-graph.json" in index_text


@pytest.mark.integration
def test_how_to_use_mentions_features_graph(sample_repo: Path) -> None:
    """Graph references migrated from CLAUDE.md (now a 3-line pointer) into
    HOW_TO_USE.md where detailed navigation lives."""
    build_all(sample_repo, bootstrap=True, dummyindex_version="0.0.0-test")
    how_to_use = (sample_repo / ".context" / "HOW_TO_USE.md").read_text(encoding="utf-8")
    assert "graph" in how_to_use.lower()
