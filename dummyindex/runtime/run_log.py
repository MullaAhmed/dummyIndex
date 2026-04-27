"""Run-log aggregation — replaces the token-only ``cost.json``.

The previous ``cost.json`` recorded only ``input_tokens`` and ``output_tokens``,
both of which are *always zero* because subagent JSON outputs hardcode those
fields and the orchestrator never threads its actual ``<usage>`` block back
into the pipeline.

This module aggregates everything *useful* that's already on disk after a run:

- File counts by type (from ``.dummyindex_detect.json``)
- Cache hit ratio (from ``.dummyindex_uncached.txt`` if present)
- Graph stats (from ``.dummyindex_extract.json`` + ``.dummyindex_analysis.json``)
- Structure-graph stats (from ``structure_graph.json``)
- Flow-graph stats (from ``flow_graph.json``)
- Feature-graph stats (from ``feature_graph.json``)
- Token totals (best-effort — usually zero but kept for forward compat)
- Wall-clock duration (caller passes ``started_at``)

The output file is now ``dummyindex-out/run_log.json``. ``cost.json`` is kept
as a *deprecated alias* with a one-line pointer for callers who haven't
migrated.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
RUN_LOG_FILENAME = "run_log.json"
LEGACY_FILENAME = "cost.json"   # kept for back-compat; written as a tiny pointer

logger = logging.getLogger("dummyindex.run_log")


def _safe_load(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read %s for run_log aggregation: %s", path, exc)
        return None


def aggregate_run_stats(
    out_dir: str | Path,
    *,
    started_at: str | None = None,
    duration_seconds: float | None = None,
    errors: list[str] | None = None,
) -> dict:
    """Collect everything useful from the artifacts that exist in ``out_dir``.

    Designed to run at Step 9 — by then every intermediate file has either
    been written or never will be. Missing files contribute zero stats; they
    don't fail the aggregation.
    """
    od = Path(out_dir)

    detect = _safe_load(od / ".dummyindex_detect.json") or {}
    extract = _safe_load(od / ".dummyindex_extract.json") or {}
    analysis = _safe_load(od / ".dummyindex_analysis.json") or {}
    structure = _safe_load(od / "structure_graph.json") or {}
    flow_graph = _safe_load(od / "flow_graph.json") or {}
    feature_graph = _safe_load(od / "feature_graph.json") or {}
    graph_data = _safe_load(od / "graph.json") or {}

    file_counts: dict[str, int] = {}
    for ftype, files in (detect.get("files") or {}).items():
        if isinstance(files, list):
            file_counts[ftype] = len(files)
    file_counts["total"] = detect.get("total_files", sum(file_counts.values()))
    total_words = detect.get("total_words", 0)

    # cache hit ratio — best-effort from the temp file written in Step B0
    cache_total = file_counts.get("document", 0) + file_counts.get("paper", 0) + file_counts.get("image", 0)
    uncached_path = od / ".dummyindex_uncached.txt"
    if uncached_path.exists():
        try:
            uncached_count = sum(1 for line in uncached_path.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            uncached_count = cache_total
    else:
        uncached_count = 0  # post-cleanup; assume everything was processed (or all cached)
    cache_hits = max(0, cache_total - uncached_count)

    # split graph counts: AST vs semantic via file_type on each node
    extraction_nodes = extract.get("nodes") or []
    extraction_edges = extract.get("edges") or []
    code_nodes = sum(1 for n in extraction_nodes if n.get("file_type") == "code")
    non_code_nodes = len(extraction_nodes) - code_nodes

    communities = analysis.get("communities") or {}
    cohesion = analysis.get("cohesion") or {}
    god_nodes = analysis.get("gods") or analysis.get("god_nodes") or []

    hyperedges = graph_data.get("hyperedges") or []
    flow_count = sum(1 for h in hyperedges if h.get("kind") == "flow")
    feature_count = sum(1 for h in hyperedges if h.get("kind") == "feature")
    other_hyper = len(hyperedges) - flow_count - feature_count

    flows = flow_graph.get("flows") or []
    flows_named = sum(1 for f in flows if f.get("label") and f.get("label") != f.get("id"))
    flow_overlap_index = flow_graph.get("overlap_index") or {}
    flow_shared_nodes = sum(1 for fids in flow_overlap_index.values() if len(fids) > 1)

    features = feature_graph.get("features") or []
    features_named = sum(1 for f in features if f.get("label") and f.get("label") != f.get("id"))
    feature_deps = feature_graph.get("feature_dependencies") or []
    feature_orphans = feature_graph.get("orphans") or []
    feature_overlap = feature_graph.get("overlap_matrix") or {}
    feature_shared_nodes = sum(1 for fids in feature_overlap.values() if len(fids) > 1)

    structure_nodes = len(structure.get("nodes") or [])
    structure_hier = len(structure.get("hierarchy_edges") or [])
    structure_cross = len(structure.get("cross_edges") or [])

    # AST cache utilization (per-code-file cache directory)
    cache_dir = od / "cache"
    ast_cache_files = len(list(cache_dir.glob("*.json"))) if cache_dir.exists() else 0

    artifact_sizes: dict[str, int] = {}
    for name in ("graph.json", "graph.html", "structure_graph.json", "structure_graph.html",
                 "flow_graph.json", "flow_graph.html", "feature_graph.json", "feature_graph.html",
                 "GRAPH_REPORT.md"):
        p = od / name
        if p.exists():
            try:
                artifact_sizes[name] = p.stat().st_size
            except OSError:
                pass

    return {
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration_seconds, 3) if duration_seconds is not None else None,
        "files": {**file_counts, "total_words": total_words},
        "extraction": {
            "input_tokens": extract.get("input_tokens", 0),
            "output_tokens": extract.get("output_tokens", 0),
            "ast_nodes": code_nodes,
            "semantic_nodes": non_code_nodes,
            "edges": len(extraction_edges),
            "cache_hits": cache_hits,
            "cache_total_non_code": cache_total,
            "ast_cache_entries": ast_cache_files,
        },
        "graph": {
            "nodes": len(extraction_nodes),
            "edges": len(extraction_edges),
            "communities": len(communities),
            "god_nodes": len(god_nodes),
            "hyperedges_total": len(hyperedges),
            "hyperedges_flow": flow_count,
            "hyperedges_feature": feature_count,
            "hyperedges_other": other_hyper,
        },
        "structure_graph": {
            "nodes": structure_nodes,
            "hierarchy_edges": structure_hier,
            "cross_edges": structure_cross,
        },
        "flow_graph": {
            "flows": len(flows),
            "named": flows_named,
            "shared_nodes": flow_shared_nodes,
        },
        "feature_graph": {
            "features": len(features),
            "named": features_named,
            "dependencies": len(feature_deps),
            "mutual_dependencies": sum(1 for d in feature_deps if d.get("is_mutual")),
            "orphans": len(feature_orphans),
            "shared_nodes": feature_shared_nodes,
        },
        "artifact_sizes_bytes": artifact_sizes,
        "errors": errors or [],
    }


def append_run(
    out_dir: str | Path,
    *,
    started_at: str | None = None,
    duration_seconds: float | None = None,
    errors: list[str] | None = None,
) -> dict:
    """Aggregate this run's stats and append them to ``run_log.json``.

    Updates ``totals`` so callers can read cumulative info at a glance.
    Writes a tiny ``cost.json`` pointer for back-compat.
    """
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    stats = aggregate_run_stats(
        od, started_at=started_at, duration_seconds=duration_seconds, errors=errors,
    )

    log_path = od / RUN_LOG_FILENAME
    log = _safe_load(log_path) or {}
    runs = log.get("runs") or []
    runs.append(stats)

    totals = log.get("totals") or {
        "runs": 0, "duration_seconds": 0.0,
        "input_tokens": 0, "output_tokens": 0,
    }
    totals["runs"] = len(runs)
    totals["duration_seconds"] = round(
        (totals.get("duration_seconds") or 0.0) + (stats["duration_seconds"] or 0.0), 3
    )
    totals["input_tokens"] += stats["extraction"]["input_tokens"]
    totals["output_tokens"] += stats["extraction"]["output_tokens"]

    payload = {"schema_version": SCHEMA_VERSION, "totals": totals, "runs": runs}
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # back-compat pointer
    legacy = od / LEGACY_FILENAME
    legacy.write_text(json.dumps({
        "deprecated": True,
        "see": str(RUN_LOG_FILENAME),
        "totals": totals,
    }, indent=2), encoding="utf-8")

    return stats


def format_run_summary(stats: dict) -> str:
    """One-line-ish CLI summary for the skill to print."""
    f = stats.get("files") or {}
    e = stats.get("extraction") or {}
    g = stats.get("graph") or {}
    fl = stats.get("flow_graph") or {}
    ft = stats.get("feature_graph") or {}
    duration = stats.get("duration_seconds")
    parts = [
        f"files: {f.get('total', 0)}",
        f"~{f.get('total_words', 0):,} words",
        f"graph: {g.get('nodes', 0)} nodes / {g.get('edges', 0)} edges / {g.get('communities', 0)} communities",
        f"cache: {e.get('cache_hits', 0)}/{e.get('cache_total_non_code', 0)} hit",
        f"flows: {fl.get('flows', 0)} ({fl.get('named', 0)} named)",
        f"features: {ft.get('features', 0)} ({ft.get('named', 0)} named, {ft.get('dependencies', 0)} deps, {ft.get('orphans', 0)} orphans)",
    ]
    if duration is not None:
        parts.append(f"took {duration:.1f}s")
    return " · ".join(parts)
