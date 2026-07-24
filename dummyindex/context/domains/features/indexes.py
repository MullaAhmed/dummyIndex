"""Rebuild `.context/features/INDEX.md` and `graph.json` from disk.

Called by `dummyindex context refresh-indexes` after enrichment touches
individual feature folders, so the top-level navigation stays in sync.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dummyindex.context.output.viewer import render_viewer_html
from dummyindex.pipeline.enums import ConfidenceLevel

from .helpers import _project_name, _write_json, _write_text
from .models import Feature, Flow, FlowStep
from .render import _graph_view
from .scan import load_seed_rank


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
                    feature_id=fl.get(
                        "feature_id", fp.get("feature_id", feat_dir.name)
                    ),
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

    # A curated scan is the one thing in `.context/` that re-extraction can
    # never reproduce, so it outranks the seed: regenerate only what was
    # generated. Same contract that keeps an enriched `spec.md` safe.
    scan = _curated_scan(graph_json_path)
    if scan is None:
        scan = _graph_view(
            tuple(features),
            tuple(flows),
            project_name=_project_name(features_dir.parent),
            links=_load_call_links(features_dir / "symbol-graph.json"),
            # Same on-disk shortlist the scaffolder consumed, so the two
            # regeneration paths stay byte-identical.
            rank=load_seed_rank(features_dir),
        )

    _write_json(graph_json_path, scan)
    _write_text(graph_html_path, render_viewer_html(scan, features_dir=features_dir))
    return graph_json_path, graph_html_path


def _load_call_links(path: Path) -> tuple[dict[str, Any], ...]:
    """Read the symbol graph's edge list, or an empty tuple if it isn't there.

    The seed needs this to connect features whose flows were all discarded.
    Parsing it is cheap next to what a refresh already does (~0.1s for the
    ~10MB graph this repo produces), and a missing or unreadable file just
    means a sparser seed — never a failed refresh.
    """
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    links = payload.get("links") or payload.get("edges") or ()
    return tuple(link for link in links if isinstance(link, dict))


def _curated_scan(path: Path) -> dict[str, Any] | None:
    """Return the on-disk scan iff a model authored it, else ``None``.

    Deliberately keyed on `confidence` alone and not on validity. A curated
    scan that breaks a cap is a scan that needs `dummyindex context
    scan-check` and a fix — deleting someone's map because a label ran four
    characters long would be the worse failure by a wide margin.

    Unreadable JSON, a legacy v1 graph (no `confidence` at all), or a
    payload that isn't an object all fall through to regeneration: those
    are generated artifacts, and replacing them is the point.
    """
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("confidence") != ConfidenceLevel.INFERRED:
        return None
    return payload


def _load_symbols_map(path: Path) -> dict[str, dict[str, Any]] | None:
    """Read `map/symbols.json` into a `{symbol_id: payload}` dict, or None if missing.

    Tolerates an absent file so older `.context/` layouts (pre-symbols-map)
    fall back to file-level granularity in the viewer.
    """
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    out: dict[str, dict[str, Any]] = {}
    for s in payload.get("symbols", []) or []:
        if not isinstance(s, dict):
            continue
        sid = s.get("symbol_id") or s.get("id") or s.get("node_id")
        if not sid:
            continue
        out[sid] = s
    return out


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
        "skill on Claude or `$dummyindex` on Codex names, regroups, and "
        "summarizes — stub names are still "
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
