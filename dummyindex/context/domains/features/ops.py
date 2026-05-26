"""Atomic feature/flow ops: rename, merge, remove_flow, write_section.

Each function raises `FeatureRenameError` for any condition that would
leave the on-disk scaffolding inconsistent — slug collisions, missing
sources, unwritable targets. The CLI catches these in
`context/cli/features.py` and maps to exit codes.
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel
import json
from pathlib import Path
from typing import Any, Optional

from ._constants import _VALID_MERGE_SECTIONS
from ._helpers import (
    _validate_feature_id,
    _format_merge_block,
    _append_section,
    _rmtree,
    _write_json,
    _write_text,
)
from .errors import FeatureRenameError
from .indexes import _index_md_from_index_json
from .models import MergeResult, RenameResult


def rename_feature(
    features_dir: Path,
    *,
    from_id: str,
    to_id: str,
    new_name: Optional[str] = None,
    new_summary: Optional[str] = None,
) -> RenameResult:
    """Atomically rename a feature folder and refresh every JSON reference.

    Updates: ``<features_dir>/<from_id>/``  →  ``<features_dir>/<to_id>/``,
    plus the ``feature_id`` / ``name`` / ``summary`` fields in
    ``feature.json``, the ``feature_id`` in every nested ``flows/*.json``,
    and the matching entries in ``INDEX.json`` and ``graph.json``.

    Idempotent: passing ``from_id == to_id`` only refreshes metadata.
    Setting ``new_name`` / ``new_summary`` flips the touched feature's
    ``confidence`` to ``INFERRED``.
    """
    features_dir = features_dir.resolve()
    to_id = _validate_feature_id(to_id)
    from_id = from_id.strip()

    src = features_dir / from_id
    dst = features_dir / to_id
    if not src.is_dir():
        raise FeatureRenameError(
            f"feature folder {src} not found; valid ids: "
            f"{sorted(p.name for p in features_dir.iterdir() if p.is_dir())}"
        )
    if dst.exists() and dst != src:
        raise FeatureRenameError(
            f"target {dst} already exists; pick a different `to` id"
        )

    touched: list[str] = []

    if dst != src:
        src.rename(dst)
        touched.append(f"features/{to_id}/")

    # Refresh feature.json
    feature_json_path = dst / "feature.json"
    if feature_json_path.exists():
        payload = json.loads(feature_json_path.read_text(encoding="utf-8"))
        payload["feature_id"] = to_id
        if new_name is not None:
            payload["name"] = new_name
        elif payload.get("name") == from_id:
            payload["name"] = to_id
        if new_summary is not None:
            payload["summary"] = new_summary
        if new_name is not None or new_summary is not None:
            payload["confidence"] = ConfidenceLevel.INFERRED
        _write_json(feature_json_path, payload)
        touched.append(f"features/{to_id}/feature.json")

    # Refresh every flow.json under flows/
    flows_dir = dst / "flows"
    if flows_dir.is_dir():
        for flow_path in sorted(flows_dir.glob("*.json")):
            payload = json.loads(flow_path.read_text(encoding="utf-8"))
            if payload.get("feature_id") != to_id:
                payload["feature_id"] = to_id
                _write_json(flow_path, payload)
                touched.append(f"features/{to_id}/flows/{flow_path.name}")

    # Refresh INDEX.json (machine) and INDEX.md (human).
    index_path = features_dir / "INDEX.json"
    if index_path.exists():
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        changed_index = False
        for entry in index_payload.get("features", []):
            if entry.get("feature_id") == from_id or entry.get("feature_id") == to_id:
                entry["feature_id"] = to_id
                entry["path"] = f"features/{to_id}/"
                if new_name is not None:
                    entry["name"] = new_name
                elif entry.get("name") == from_id:
                    entry["name"] = to_id
                if new_summary is not None:
                    entry["summary"] = new_summary
                if new_name is not None or new_summary is not None:
                    entry["confidence"] = ConfidenceLevel.INFERRED
                changed_index = True
        if changed_index:
            _write_json(index_path, index_payload)
            touched.append("features/INDEX.json")
            # Rebuild the human-readable INDEX.md from the updated INDEX.json
            # so its links don't 404 after a rename.
            _write_text(
                features_dir / "INDEX.md",
                _index_md_from_index_json(index_payload),
            )
            touched.append("features/INDEX.md")

    # Refresh the viewer's graph.json
    graph_view_path = features_dir / "graph.json"
    if graph_view_path.exists():
        gv = json.loads(graph_view_path.read_text(encoding="utf-8"))
        changed_gv = False
        for n in gv.get("nodes", []):
            if n.get("id") == from_id:
                n["id"] = to_id
                if new_name is not None:
                    n["label"] = new_name
                elif n.get("label") == from_id:
                    n["label"] = to_id
                changed_gv = True
            elif n.get("kind") == "flow" and n.get("feature_id") == from_id:
                n["feature_id"] = to_id
                changed_gv = True
        for e in gv.get("edges", []):
            if e.get("source") == from_id:
                e["source"] = to_id
                changed_gv = True
            if e.get("target") == from_id:
                e["target"] = to_id
                changed_gv = True
        if changed_gv:
            _write_json(graph_view_path, gv)
            touched.append("features/graph.json")

    return RenameResult(
        from_id=from_id,
        to_id=to_id,
        new_name=new_name,
        new_summary=new_summary,
        files_touched=tuple(touched),
    )


# ----- merge_feature --------------------------------------------------------

def merge_feature(
    features_dir: Path,
    *,
    from_id: str,
    into_id: str,
    as_section: str,
    note: Optional[str] = None,
) -> MergeResult:
    """Absorb a trivial feature ``from_id`` into ``into_id`` as a section.

    Used by the chairman during the trivial-feature consolidation pass
    when a tiny utility cluster belongs to a real feature rather than
    standing alone.

    Behavior:

    - Appends the source feature's entry-point prose (``spec.md``, or the
      legacy ``README.md`` if the source predates v0.14; plus a header noting
      the source feature_id) into ``features/<into_id>/<as_section>.md``.
      The block is wrapped in dummyindex sentinels so a second merge
      under the same section appends another block instead of clobbering.
    - Merges ``members`` / ``files`` / ``entry_points`` from source into
      target's ``feature.json`` (deduplicated). Bumps target confidence
      to ``INFERRED``.
    - Deletes the source feature folder (and any flows under it).
    - Drops the source entry from ``features/INDEX.json`` and refreshes
      ``features/INDEX.md``.
    - Drops the source feature node + its edges from ``features/graph.json``.
    - Appends a stage-0 chairman entry to the target feature's
      ``council/_council-log.json`` so the consolidation pass leaves an
      audit trail even when the operator forgot to run ``council-log``
      themselves. ``note`` is written verbatim; if omitted, a default
      ``"merged-from:<from_id>"`` is generated.

    ``as_section`` must be one of ``_VALID_MERGE_SECTIONS`` — currently
    only ``"supporting"``. Ad-hoc section names (e.g. ``noise-absorbed``)
    are rejected so consolidation passes can't quietly invent new audit
    formats; broadening the allowlist requires updating the procedure
    in ``dummyindex/skills/council/filter-trivial.md``.

    Idempotent: merging a folder that no longer exists raises.
    """
    features_dir = features_dir.resolve()
    from_id = from_id.strip()
    into_id = _validate_feature_id(into_id)
    if from_id == into_id:
        raise FeatureRenameError(
            f"cannot merge feature {from_id!r} into itself"
        )
    if as_section not in _VALID_MERGE_SECTIONS:
        raise FeatureRenameError(
            f"invalid section name {as_section!r}; "
            f"allowed: {sorted(_VALID_MERGE_SECTIONS)}"
        )

    src = features_dir / from_id
    dst = features_dir / into_id
    if not src.is_dir():
        raise FeatureRenameError(f"source feature folder not found: {src}")
    if not dst.is_dir():
        raise FeatureRenameError(f"target feature folder not found: {dst}")

    touched: list[str] = []

    # --- 1. Append the source content into the target section file. ---------
    src_feature_payload: dict[str, Any] = {}
    src_feature_json = src / "feature.json"
    if src_feature_json.exists():
        src_feature_payload = json.loads(
            src_feature_json.read_text(encoding="utf-8")
        )
    # Prefer the v0.14 entry point (spec.md); fall back to the legacy
    # README.md so `.context/` repos scaffolded before this release still
    # merge cleanly during the transition window.
    src_entry_md = ""
    src_spec_path = src / "spec.md"
    src_readme_path = src / "README.md"
    if src_spec_path.exists():
        src_entry_md = src_spec_path.read_text(encoding="utf-8")
    elif src_readme_path.exists():
        src_entry_md = src_readme_path.read_text(encoding="utf-8")

    section_target = dst / f"{as_section}.md"
    block = _format_merge_block(from_id, src_feature_payload, src_entry_md)
    _append_section(section_target, as_section, block)
    touched.append(f"features/{into_id}/{as_section}.md")

    # --- 2. Merge feature.json fields into the target. ----------------------
    dst_feature_json = dst / "feature.json"
    if dst_feature_json.exists():
        dst_payload = json.loads(dst_feature_json.read_text(encoding="utf-8"))
        for key in ("members", "files", "entry_points"):
            merged = sorted(
                {*dst_payload.get(key, []), *src_feature_payload.get(key, [])}
            )
            dst_payload[key] = merged
        dst_payload["confidence"] = ConfidenceLevel.INFERRED
        _write_json(dst_feature_json, dst_payload)
        touched.append(f"features/{into_id}/feature.json")

    # --- 3. Delete the source folder (and all flows inside it). -------------
    _rmtree(src)
    touched.append(f"features/{from_id}/ (removed)")

    # --- 4. Drop source from INDEX.json + refresh counts for target. --------
    index_path = features_dir / "INDEX.json"
    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        entries = idx.get("features", []) or []
        new_entries: list[dict[str, Any]] = []
        dropped_flow_count = 0
        for entry in entries:
            if entry.get("feature_id") == from_id:
                dropped_flow_count += int(entry.get("flow_count", 0) or 0)
                continue
            if entry.get("feature_id") == into_id and dst_feature_json.exists():
                merged_payload = json.loads(
                    dst_feature_json.read_text(encoding="utf-8")
                )
                entry["member_count"] = len(merged_payload.get("members", []))
                entry["file_count"] = len(merged_payload.get("files", []))
                entry["entry_point_count"] = len(
                    merged_payload.get("entry_points", [])
                )
                entry["confidence"] = ConfidenceLevel.INFERRED
            new_entries.append(entry)
        if len(new_entries) != len(entries):
            idx["features"] = new_entries
            idx["flow_count"] = max(
                0, int(idx.get("flow_count", 0) or 0) - dropped_flow_count
            )
            _write_json(index_path, idx)
            touched.append("features/INDEX.json")
            _write_text(
                features_dir / "INDEX.md",
                _index_md_from_index_json(idx),
            )
            touched.append("features/INDEX.md")

    # --- 5. Drop source node + its edges from graph.json. -------------------
    graph_path = features_dir / "graph.json"
    if graph_path.exists():
        gv = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = gv.get("nodes", []) or []
        edges = gv.get("edges", []) or []
        # Find flow ids that were under the source so we can drop them too —
        # they no longer belong to a feature.
        flow_ids_to_drop = {
            n.get("id")
            for n in nodes
            if n.get("kind") == "flow" and n.get("feature_id") == from_id
        }
        drop_ids = {from_id, *flow_ids_to_drop}
        new_nodes = [n for n in nodes if n.get("id") not in drop_ids]
        new_edges = [
            e for e in edges
            if e.get("source") not in drop_ids
            and e.get("target") not in drop_ids
        ]
        if len(new_nodes) != len(nodes) or len(new_edges) != len(edges):
            gv["nodes"] = new_nodes
            gv["edges"] = new_edges
            _write_json(graph_path, gv)
            touched.append("features/graph.json")

    # --- 6. Auto-log the chairman decision on the target. -------------------
    # Imported lazily so the features package stays loadable in environments
    # where the council module's deps drift; the side-effect is the audit
    # trail required by filter-trivial.md.
    from dummyindex.context.domains.council import append_log

    log_note = note if note is not None else f"merged-from:{from_id}"
    append_log(
        features_dir,
        feature_id=into_id,
        stage=0,
        agent="chairman",
        status="complete",
        note=log_note,
    )
    touched.append(f"features/{into_id}/council/_council-log.json")

    return MergeResult(
        from_id=from_id,
        to_id=into_id,
        section=as_section,
        files_touched=tuple(touched),
    )

def remove_flow(
    features_dir: Path,
    *,
    feature_id: str,
    flow_id: str,
) -> RenameResult:
    """Atomically delete a flow from a feature.

    Used by the senior-developer council agent to drop noise flows
    (private helpers misdetected as entry points, enum classes,
    trivially-traced sequences). Touches:

    - ``features/<feature_id>/flows/<flow_id>.{json,md}`` — deleted.
    - ``features/<feature_id>/feature.json`` — `flow_ids` filtered.
    - ``features/INDEX.json`` — `flow_count` decremented for the feature,
      top-level `flow_count` decremented.
    - ``features/graph.json`` — flow node + its edges removed.

    Idempotent: re-running on a missing flow is a no-op (no error).
    """
    features_dir = features_dir.resolve()
    feat_dir = features_dir / feature_id
    if not feat_dir.is_dir():
        raise FeatureRenameError(
            f"feature folder {feat_dir} not found"
        )

    touched: list[str] = []

    flow_json = feat_dir / "flows" / f"{flow_id}.json"
    flow_md = feat_dir / "flows" / f"{flow_id}.md"
    removed_anything = False
    for p in (flow_json, flow_md):
        if p.exists():
            p.unlink()
            touched.append(str(p.relative_to(features_dir.parent)))
            removed_anything = True

    # feature.json
    feature_json = feat_dir / "feature.json"
    if feature_json.exists():
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
        old = list(payload.get("flow_ids", []))
        new = [f for f in old if f != flow_id]
        if old != new:
            payload["flow_ids"] = new
            _write_json(feature_json, payload)
            touched.append(f"features/{feature_id}/feature.json")

    # INDEX.json
    index_path = features_dir / "INDEX.json"
    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        changed_idx = False
        for entry in idx.get("features", []):
            if entry.get("feature_id") == feature_id:
                # Use the current flow_ids count from feature.json if available.
                if feature_json.exists():
                    fp = json.loads(feature_json.read_text(encoding="utf-8"))
                    new_count = len(fp.get("flow_ids", []))
                else:
                    new_count = max(0, entry.get("flow_count", 0) - 1)
                if entry.get("flow_count") != new_count:
                    entry["flow_count"] = new_count
                    changed_idx = True
        if removed_anything:
            idx["flow_count"] = max(0, idx.get("flow_count", 0) - 1)
            changed_idx = True
        if changed_idx:
            _write_json(index_path, idx)
            touched.append("features/INDEX.json")
            _write_text(
                features_dir / "INDEX.md",
                _index_md_from_index_json(idx),
            )
            touched.append("features/INDEX.md")

    # graph.json — drop the flow node + every edge touching it.
    gv_path = features_dir / "graph.json"
    if gv_path.exists():
        gv = json.loads(gv_path.read_text(encoding="utf-8"))
        nodes = gv.get("nodes", []) or []
        edges = gv.get("edges", []) or []
        new_nodes = [n for n in nodes if n.get("id") != flow_id]
        new_edges = [
            e for e in edges
            if e.get("source") != flow_id and e.get("target") != flow_id
        ]
        if len(new_nodes) != len(nodes) or len(new_edges) != len(edges):
            gv["nodes"] = new_nodes
            gv["edges"] = new_edges
            _write_json(gv_path, gv)
            touched.append("features/graph.json")

    return RenameResult(
        from_id=flow_id,
        to_id="",
        new_name=None,
        new_summary=None,
        files_touched=tuple(touched),
    )

def write_section(
    features_dir: Path,
    *,
    feature_id: str,
    section: str,
    source_file: Path,
) -> Path:
    """Atomically place a markdown into ``features/<feature_id>/<section>.md``.

    Canonical section names (v0.14): ``spec``, ``plan``, ``concerns``. The
    legacy essay names (``README``, ``architecture``, ``implementation``,
    ``data-model``, ``security``, ``product``) are still accepted during the
    transition. Other names are accepted too but a warning is surfaced via
    the return path's parent existence — callers should sanity-check.

    Idempotent: writing the same content twice yields the same file. Uses
    a tmp-file + rename for atomicity.
    """
    features_dir = features_dir.resolve()
    feat_dir = features_dir / feature_id
    if not feat_dir.is_dir():
        raise FeatureRenameError(
            f"feature folder {feat_dir} not found"
        )

    section = section.strip()
    if not section or "/" in section or section.startswith("."):
        raise FeatureRenameError(f"invalid section name: {section!r}")

    # Allow .md extension to be either present or absent.
    target_name = section if section.endswith(".md") else f"{section}.md"
    target = feat_dir / target_name

    if not source_file.exists():
        raise FeatureRenameError(f"source file not found: {source_file}")

    content = source_file.read_text(encoding="utf-8")
    _write_text(target, content)
    return target

