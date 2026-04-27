"""Tests for the run_log aggregator (replaces token-only cost.json)."""
import json
from pathlib import Path

import pytest

from dummyindex.runtime.run_log import (
    LEGACY_FILENAME,
    RUN_LOG_FILENAME,
    aggregate_run_stats,
    append_run,
    format_run_summary,
)


def _write_artifacts(tmp_path: Path) -> None:
    """Write a realistic set of pipeline intermediates the run_log reads."""
    (tmp_path / ".dummyindex_detect.json").write_text(json.dumps({
        "total_files": 31, "total_words": 605500,
        "files": {"code": [None]*6, "document": [None]*4, "paper": [None]*3, "image": [None]*16},
    }))
    (tmp_path / ".dummyindex_extract.json").write_text(json.dumps({
        "nodes": [{"id": f"n{i}", "file_type": "code"} for i in range(18)] +
                 [{"id": f"d{i}", "file_type": "document"} for i in range(50)],
        "edges": [{"source": "a", "target": "b"}] * 80,
        "input_tokens": 12345, "output_tokens": 6789,
    }))
    (tmp_path / ".dummyindex_analysis.json").write_text(json.dumps({
        "communities": {str(i): [f"n{i}"] for i in range(5)},
        "cohesion": {str(i): 0.5 for i in range(5)},
        "gods": [{"id": f"god_{i}", "label": f"god_{i}"} for i in range(3)],
    }))
    (tmp_path / "structure_graph.json").write_text(json.dumps({
        "nodes": [{"id": f"s{i}"} for i in range(60)],
        "hierarchy_edges": [{}] * 59, "cross_edges": [{}] * 71,
    }))
    (tmp_path / "flow_graph.json").write_text(json.dumps({
        "flows": [
            {"id": "flow:a", "label": "Login Flow", "nodes": ["x", "y"]},
            {"id": "flow:b", "label": "flow:b", "nodes": ["y"]},  # provisional
        ],
        "overlap_index": {"y": ["flow:a", "flow:b"]},
    }))
    (tmp_path / "feature_graph.json").write_text(json.dumps({
        "features": [
            {"id": "feature:auth", "label": "Auth"},
            {"id": "feature:pay", "label": "Payments"},
            {"id": "feature:infra", "label": "feature:infra"},  # provisional
        ],
        "feature_dependencies": [
            {"source_feature_id": "feature:pay", "target_feature_id": "feature:auth", "is_mutual": True},
            {"source_feature_id": "feature:auth", "target_feature_id": "feature:pay", "is_mutual": True},
        ],
        "orphans": ["o1", "o2", "o3"],
        "overlap_matrix": {"shared_node": ["feature:auth", "feature:pay"]},
    }))
    (tmp_path / "graph.json").write_text(json.dumps({
        "nodes": [], "links": [],
        "hyperedges": [
            {"id": "flow:a", "kind": "flow"},
            {"id": "flow:b", "kind": "flow"},
            {"id": "feature:auth", "kind": "feature"},
            {"id": "feature:pay", "kind": "feature"},
            {"id": "feature:infra", "kind": "feature"},
        ],
    }))


def test_aggregate_pulls_counts_from_every_artifact(tmp_path):
    _write_artifacts(tmp_path)
    stats = aggregate_run_stats(tmp_path, started_at="2026-04-26T00:00:00+00:00",
                                 duration_seconds=42.5)

    assert stats["schema_version"] == "1.0"
    assert stats["files"]["total"] == 31
    assert stats["files"]["total_words"] == 605500
    assert stats["files"]["code"] == 6
    assert stats["files"]["document"] == 4
    assert stats["files"]["paper"] == 3
    assert stats["files"]["image"] == 16

    assert stats["extraction"]["input_tokens"] == 12345
    assert stats["extraction"]["output_tokens"] == 6789
    assert stats["extraction"]["ast_nodes"] == 18
    assert stats["extraction"]["semantic_nodes"] == 50
    assert stats["extraction"]["edges"] == 80

    assert stats["graph"]["nodes"] == 68
    assert stats["graph"]["communities"] == 5
    assert stats["graph"]["god_nodes"] == 3
    assert stats["graph"]["hyperedges_flow"] == 2
    assert stats["graph"]["hyperedges_feature"] == 3

    assert stats["structure_graph"]["nodes"] == 60
    assert stats["structure_graph"]["hierarchy_edges"] == 59
    assert stats["structure_graph"]["cross_edges"] == 71

    assert stats["flow_graph"]["flows"] == 2
    assert stats["flow_graph"]["named"] == 1  # only flow:a is named
    assert stats["flow_graph"]["shared_nodes"] == 1

    assert stats["feature_graph"]["features"] == 3
    assert stats["feature_graph"]["named"] == 2  # feature:infra is provisional
    assert stats["feature_graph"]["dependencies"] == 2
    assert stats["feature_graph"]["mutual_dependencies"] == 2
    assert stats["feature_graph"]["orphans"] == 3
    assert stats["feature_graph"]["shared_nodes"] == 1

    assert stats["duration_seconds"] == 42.5
    assert stats["started_at"] == "2026-04-26T00:00:00+00:00"


def test_aggregate_handles_missing_artifacts(tmp_path):
    """Should not crash on a fresh out_dir."""
    stats = aggregate_run_stats(tmp_path)
    assert stats["files"]["total"] == 0
    assert stats["graph"]["nodes"] == 0
    assert stats["flow_graph"]["flows"] == 0


def test_append_run_persists_and_accumulates(tmp_path):
    _write_artifacts(tmp_path)
    s1 = append_run(tmp_path, duration_seconds=10.0)
    s2 = append_run(tmp_path, duration_seconds=15.0)

    log = json.loads((tmp_path / RUN_LOG_FILENAME).read_text())
    assert log["schema_version"] == "1.0"
    assert log["totals"]["runs"] == 2
    assert log["totals"]["duration_seconds"] == 25.0
    assert log["totals"]["input_tokens"] == 12345 * 2
    assert len(log["runs"]) == 2

    # back-compat pointer
    legacy = json.loads((tmp_path / LEGACY_FILENAME).read_text())
    assert legacy["deprecated"] is True
    assert legacy["see"] == RUN_LOG_FILENAME


def test_format_run_summary_is_concise(tmp_path):
    _write_artifacts(tmp_path)
    stats = aggregate_run_stats(tmp_path, duration_seconds=12.3)
    s = format_run_summary(stats)
    assert "files: 31" in s
    assert "took 12.3s" in s
    assert "flows: 2" in s
    assert "features: 3" in s


def test_aggregate_uses_uncached_for_cache_hit_ratio(tmp_path):
    _write_artifacts(tmp_path)
    # Pretend Step B0 left an uncached file with 5 entries
    (tmp_path / ".dummyindex_uncached.txt").write_text("a\nb\nc\nd\ne\n")
    stats = aggregate_run_stats(tmp_path)
    assert stats["extraction"]["cache_total_non_code"] == 23  # 4 doc + 3 paper + 16 img
    assert stats["extraction"]["cache_hits"] == 18  # 23 - 5 uncached
