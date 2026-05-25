"""Rebuild `.context/features/INDEX.md` and `graph.json` from disk.

Called by `dummyindex context refresh-indexes` after enrichment touches
individual feature folders, so the top-level navigation stays in sync.
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel
import json
from pathlib import Path
from typing import Any

from dummyindex.context.output.viewer import VIEWER_HTML

from ._helpers import _write_json, _write_text
from .models import Feature, Flow, FlowStep
from .render import _graph_view


def refresh_features_index_md(features_dir: Path) -> Path:
    """Rebuild ``<features_dir>/INDEX.md`` from the canonical INDEX.json.

    Use after a session of `features-rename` calls so the human-readable
    table reflects the renamed features. Raises ``FileNotFoundError`` if
    ``features/INDEX.json`` doesn't exist (no scaffolding to refresh).
    """
    index_json_path = features_dir / "INDEX.json"
    if not index_json_path.exists():
        raise FileNotFoundError(index_json_path)
    payload = json.loads(index_json_path.read_text(encoding="utf-8"))
    out_path = features_dir / "INDEX.md"
    _write_text(out_path, _index_md_from_index_json(payload))
    return out_path

def rebuild_features_graph(features_dir: Path) -> tuple[Path, Path]:
    """Regenerate ``graph.json`` + ``graph.html`` from disk.

    Walks ``features/<id>/feature.json`` + ``features/<id>/flows/*.json``
    and re-emits the denormalized viewer payload. Use when the schema
    changed (e.g. you upgraded dummyindex and want the richer folder
    hierarchy in the viewer) without forcing a full re-ingest that
    would clobber LLM-enriched names + summaries.

    Raises ``FileNotFoundError`` if ``features_dir`` doesn't exist.
    """
    if not features_dir.is_dir():
        raise FileNotFoundError(features_dir)

    features: list[Feature] = []
    flows: list[Flow] = []

    for feat_dir in sorted(p for p in features_dir.iterdir() if p.is_dir()):
        feature_json = feat_dir / "feature.json"
        if not feature_json.exists():
            continue
        fp = json.loads(feature_json.read_text(encoding="utf-8"))
        features.append(
            Feature(
                feature_id=fp.get("feature_id", feat_dir.name),
                kind=fp.get("kind", "community"),
                name=fp.get("name", feat_dir.name),
                summary=fp.get("summary"),
                members=tuple(fp.get("members", [])),
                files=tuple(fp.get("files", [])),
                entry_points=tuple(fp.get("entry_points", [])),
                flow_ids=tuple(fp.get("flow_ids", [])),
                confidence=fp.get("confidence", ConfidenceLevel.EXTRACTED),
            )
        )
        flows_dir = feat_dir / "flows"
        if not flows_dir.is_dir():
            continue
        for flow_path in sorted(flows_dir.glob("*.json")):
            fl = json.loads(flow_path.read_text(encoding="utf-8"))
            steps = tuple(
                FlowStep(
                    depth=int(s.get("depth", 0)),
                    node_id=s.get("node_id", ""),
                    label=s.get("label", ""),
                    path=s.get("path"),
                    range=s.get("range"),
                )
                for s in fl.get("steps", [])
            )
            flows.append(
                Flow(
                    flow_id=fl.get("flow_id", flow_path.stem),
                    feature_id=fl.get("feature_id", fp.get("feature_id", feat_dir.name)),
                    entry_point=fl.get("entry_point", ""),
                    entry_point_label=fl.get("entry_point_label", ""),
                    entry_point_path=fl.get("entry_point_path"),
                    steps=steps,
                    files=tuple(fl.get("files", [])),
                    confidence=fl.get("confidence", ConfidenceLevel.EXTRACTED),
                )
            )

    graph_json_path = features_dir / "graph.json"
    graph_html_path = features_dir / "graph.html"
    _write_json(graph_json_path, _graph_view(tuple(features), tuple(flows)))
    _write_text(graph_html_path, VIEWER_HTML)
    return graph_json_path, graph_html_path


# ----- doc → feature linking ------------------------------------------------

def _index_md_from_index_json(payload: dict[str, Any]) -> str:
    """Re-render features/INDEX.md from the canonical features/INDEX.json.

    Used by ``rename_feature`` so the human-readable index never lags
    behind the machine-readable one. Falls back to the feature_id when
    a real `name` hasn't been written yet.
    """
    features = payload.get("features", []) or []
    flow_count = int(payload.get("flow_count", 0) or 0)
    lines = [
        "# Features",
        "",
        f"_{len(features)} feature(s), {flow_count} flow(s). The `/dummyindex` "
        "skill names, regroups, and summarizes — stub names are still "
        "`community-N` until enriched._",
        "",
        "| Feature | Members | Files | Entry points | Flows | Confidence |",
        "|---|---|---|---|---|---|",
    ]
    for entry in features:
        name = entry.get("name") or entry.get("feature_id")
        fid = entry.get("feature_id")
        lines.append(
            f"| [`{name}`](./{fid}/) | {entry.get('member_count', 0)} | "
            f"{entry.get('file_count', 0)} | "
            f"{entry.get('entry_point_count', 0)} | "
            f"{entry.get('flow_count', 0)} | "
            f"{entry.get('confidence', 'EXTRACTED')} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"

