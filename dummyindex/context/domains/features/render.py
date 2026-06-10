"""Markdown stub renderers and the .context/features/ HTML viewer hookup.

Pure functions: take dataclasses + dicts, return strings. No I/O.
`builder._write_all` is the orchestrator that calls these and writes the
strings to disk.
"""
from __future__ import annotations
from typing import Any
from .constants import SCHEMA_VERSION
from .models import Feature, Flow


def _stub_feature_spec(feat: Feature, flows: list[Flow]) -> str:
    lines: list[str] = []
    lines.append(f"# Feature: {feat.name}")
    lines.append("")
    lines.append(
        f"_Deterministic stub (`confidence: {feat.confidence}`). The `/dummyindex` "
        "skill will rewrite this `spec.md` — the feature's entry point — with a real "
        "summary based on the source code._"
    )
    lines.append("")
    lines.append("## At a glance")
    lines.append("")
    lines.append(f"- **Members:** {len(feat.members)} symbol(s)")
    lines.append(f"- **Files:** {len(feat.files)}")
    lines.append(f"- **Entry points:** {len(feat.entry_points)}")
    lines.append(f"- **Flows:** {len(flows)}")
    lines.append("")
    if feat.files:
        lines.append("## Files involved")
        lines.append("")
        for fp in feat.files:
            lines.append(f"- `{fp}`")
        lines.append("")
    if flows:
        lines.append("## Flows")
        lines.append("")
        for flow in flows:
            lines.append(
                f"- [`{flow.flow_id}`](./flows/{flow.flow_id}.md) — entry: "
                f"`{flow.entry_point_label}` "
                f"({len(flow.steps)} steps, {len(flow.files)} files)"
            )
        lines.append("")
    if feat.entry_points:
        lines.append("## Entry points")
        lines.append("")
        for ep in feat.entry_points:
            lines.append(f"- `{ep}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def _stub_flow_md(flow: Flow) -> str:
    lines: list[str] = []
    lines.append(f"# Flow: {flow.flow_id}")
    lines.append("")
    lines.append(
        f"_Deterministic trace from a BFS over `calls` edges (`confidence: "
        f"{flow.confidence}`). The `/dummyindex` skill will rewrite this file "
        "with a plain-language narrative._"
    )
    lines.append("")
    lines.append(
        f"**Entry point:** `{flow.entry_point_label}` "
        f"(`{flow.entry_point_path or '?'}`)"
    )
    lines.append("")
    lines.append("## Steps")
    lines.append("")
    for s in flow.steps:
        indent = "  " * s.depth
        loc = ""
        if s.path and s.range:
            loc = f" — `{s.path}:{s.range[0]}`"
        elif s.path:
            loc = f" — `{s.path}`"
        lines.append(f"{indent}- `{s.label}`{loc}")
    lines.append("")
    if flow.files:
        lines.append("## Files touched")
        lines.append("")
        for fp in flow.files:
            lines.append(f"- `{fp}`")
        lines.append("")
    return "\n".join(lines) + "\n"

def _index_md(features: tuple[Feature, ...], flows: tuple[Flow, ...]) -> str:
    lines = [
        "# Features",
        "",
        f"_{len(features)} feature(s), {len(flows)} flow(s). Stubs derived from "
        "graph communities (Leiden) + entry-point traces (in-degree 0 in the "
        "call subgraph). The `/dummyindex` skill renames, regroups, and "
        "summarizes._",
        "",
        "| Feature | Members | Files | Entry points | Flows |",
        "|---|---|---|---|---|",
    ]
    for f in features:
        lines.append(
            f"| [`{f.name}`](./{f.feature_id}/) | {len(f.members)} | "
            f"{len(f.files)} | {len(f.entry_points)} | {len(f.flow_ids)} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"

def _how_to_navigate_md() -> str:
    return (
        "# How to navigate `features/`\n"
        "\n"
        "This folder is the **feature-oriented** view of the codebase. Use it\n"
        "when the user asks about behavior (\"how does login work?\", \"what\n"
        "happens on checkout?\") rather than about symbols.\n"
        "\n"
        "## Read in this order\n"
        "\n"
        "1. **`INDEX.json`** — the machine-readable list of features. Each\n"
        "   entry has `feature_id`, `name`, `path`, and summary counts. Start\n"
        "   here; it's much smaller than walking every folder.\n"
        "2. **`<feature-id>/feature.json`** — canonical description of one\n"
        "   feature: members (symbol node_ids), files, entry_points, and a\n"
        "   `flow_ids` list pointing into `flows/`.\n"
        "3. **`<feature-id>/flows/<flow-id>.json`** — an ordered call sequence\n"
        "   from a single entry point. Each step has `node_id`, `label`,\n"
        "   `path`, `range`, and `depth`. Use this when the user wants the\n"
        "   sequence of calls that implements a particular flow.\n"
        "4. **`<feature-id>/spec.md`** (entry) / **`plan.md`** /\n"
        "   **`concerns.md`** / **`flows/<flow-id>.md`** — human prose.\n"
        "   `spec.md` is the entry point (what the feature does); `plan.md`\n"
        "   covers how it's built; `concerns.md` records risks/gaps. After\n"
        "   the `/dummyindex` skill enriches, these become the primary docs\n"
        "   for someone reading without an agent.\n"
        "\n"
        "## Cross-reference with `tree.json` and `map/`\n"
        "\n"
        "Every `node_id` in feature / flow JSON also appears in\n"
        "`../tree.json` and `../map/symbols.json` — use those to resolve a\n"
        "node to its exact source range when reading code.\n"
        "\n"
        "## Confidence\n"
        "\n"
        "Every feature / flow has a `confidence` field. `EXTRACTED` means\n"
        "deterministic (graph communities, BFS traces). `INFERRED` means an\n"
        "LLM (the Claude session running the `/dummyindex` skill) rewrote\n"
        "the name / summary / narrative based on actual source.\n"
        "\n"
        "## Don't grep `features/`\n"
        "\n"
        "Always start from `INDEX.json` and walk by `feature_id` /\n"
        "`flow_id`. Folder names may be renamed by enrichment; the\n"
        "`feature_id` in JSON is stable.\n"
    )


def _graph_view(
    features: tuple[Feature, ...],
    flows: tuple[Flow, ...],
    symbols: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Denormalized graph for the HTML viewer.

    Six node kinds, full folder → file → class/function → method → feature/flow:

    - ``folder`` — every unique directory along the path of any file
      involved in a feature/flow. The repo root is ``folder::.``.
    - ``file`` — every source file touched by at least one feature.
    - ``class`` — every class symbol whose enclosing file is in scope.
    - ``function`` — every top-level function (parent is a file).
    - ``method`` — every method (parent is a class).
    - ``feature`` — Leiden community wrapping one or more files.
    - ``flow`` — entry-point trace within a feature.

    Edge relations:

    - ``parent`` — folder → folder (containment in the directory tree)
    - ``contains`` — folder → file, file → class/function,
      class → method, feature → flow
    - ``touches`` — feature → file, flow → file, feature → symbol
      (only for symbols listed in `feature.members`)

    ``symbols`` is the ``map/symbols.json`` payload as
    ``{symbol_id: {kind, name, path, range, parent, ...}}``. When omitted,
    symbol nodes are skipped so the viewer falls back to file-level
    granularity. Callers that have the symbols map (``builder.scaffold_features``
    + ``indexes.rebuild_features_graph``) should always pass it through.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Collect every file used by any feature.
    all_files: set[str] = set()
    for f in features:
        all_files.update(f.files)
    for flow in flows:
        all_files.update(flow.files)

    # Build the folder hierarchy: every unique directory along every
    # file's path, plus the synthetic root folder.
    folder_paths: set[str] = {"."}
    for fp in all_files:
        parts = fp.split("/")
        for i in range(1, len(parts)):  # exclude the file itself
            folder_paths.add("/".join(parts[:i]))

    for fpath in sorted(folder_paths):
        label = "/" if fpath == "." else fpath.split("/")[-1]
        nodes.append(
            {
                "id": f"folder::{fpath}",
                "label": label,
                "kind": "folder",
                "path": fpath,
            }
        )
        # parent → child folder edge
        if fpath != ".":
            parent = "/".join(fpath.split("/")[:-1]) or "."
            edges.append(
                {
                    "source": f"folder::{parent}",
                    "target": f"folder::{fpath}",
                    "relation": "parent",
                }
            )

    # Files: emit each once and connect to its parent folder.
    for fp in sorted(all_files):
        file_id = f"file::{fp}"
        parts = fp.split("/")
        parent_folder = "/".join(parts[:-1]) or "."
        nodes.append(
            {
                "id": file_id,
                "label": parts[-1],
                "kind": "file",
                "path": fp,
            }
        )
        edges.append(
            {
                "source": f"folder::{parent_folder}",
                "target": file_id,
                "relation": "contains",
            }
        )

    # Symbol nodes (class / function / method). Surgical updates need
    # per-symbol IDs — without these the graph stops at file granularity
    # and the viewer can't point you at a specific class or method.
    emitted_symbols: set[str] = set()
    if symbols:
        # First pass: which symbols are in-scope? A symbol is in-scope if
        # its file is one of the files any feature touches.
        for sid, s in symbols.items():
            if s.get("kind") not in ("class", "function", "method"):
                continue
            path = s.get("path") or ""
            if path not in all_files:
                continue
            rng = s.get("range") or [None, None]
            nodes.append(
                {
                    "id": f"symbol::{sid}",
                    "label": s.get("name") or sid,
                    "kind": s.get("kind"),
                    "path": path,
                    "range": rng,
                    "exported": bool(s.get("exported")),
                }
            )
            emitted_symbols.add(sid)

        # Second pass: contains edges from parent file / parent symbol.
        for sid in emitted_symbols:
            s = symbols[sid]
            parent_id = s.get("parent")
            path = s.get("path") or ""
            if parent_id and parent_id in emitted_symbols:
                src = f"symbol::{parent_id}"
            else:
                src = f"file::{path}"
            edges.append(
                {
                    "source": src,
                    "target": f"symbol::{sid}",
                    "relation": "contains",
                }
            )

    # Features + their file touches.
    for f in features:
        nodes.append(
            {
                "id": f.feature_id,
                "label": f.name,
                "kind": "feature",
                "member_count": len(f.members),
                "file_count": len(f.files),
                "flow_count": len(f.flow_ids),
                "summary": f.summary,
                "confidence": f.confidence,
            }
        )
        for fp in f.files:
            edges.append(
                {
                    "source": f.feature_id,
                    "target": f"file::{fp}",
                    "relation": "touches",
                }
            )
        # feature → symbol touches (only symbols we actually emitted).
        for mid in f.members:
            if mid in emitted_symbols:
                edges.append(
                    {
                        "source": f.feature_id,
                        "target": f"symbol::{mid}",
                        "relation": "touches",
                    }
                )

    # Flows: under their feature, touching their files.
    for flow in flows:
        nodes.append(
            {
                "id": flow.flow_id,
                "label": flow.entry_point_label,
                "kind": "flow",
                "feature_id": flow.feature_id,
                "step_count": len(flow.steps),
                "file_count": len(flow.files),
            }
        )
        edges.append(
            {
                "source": flow.feature_id,
                "target": flow.flow_id,
                "relation": "contains",
            }
        )
        for fp in flow.files:
            edges.append(
                {
                    "source": flow.flow_id,
                    "target": f"file::{fp}",
                    "relation": "touches",
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "nodes": nodes,
        "edges": edges,
    }
