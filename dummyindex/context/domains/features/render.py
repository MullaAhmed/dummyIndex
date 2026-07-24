"""Markdown stub renderers and the .context/features/ HTML viewer hookup.

Pure functions: take dataclasses + dicts, return strings. No I/O.
`builder._write_all` is the orchestrator that calls these and writes the
strings to disk.
"""

from __future__ import annotations

from typing import Any

from .models import Feature, Flow
from .scan import SeedRank, seed_scan, slugify


def _stub_feature_spec(feat: Feature, flows: list[Flow]) -> str:
    lines: list[str] = []
    lines.append(f"# Feature: {feat.name}")
    lines.append("")
    lines.append(
        f"_Deterministic stub (`confidence: {feat.confidence}`). The `/dummyindex` "
        "(Claude) or `$dummyindex` (Codex) skill will rewrite this `spec.md` — "
        "the feature's entry point — with a real "
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
        f"{flow.confidence}`). The `/dummyindex` (Claude) or `$dummyindex` "
        "(Codex) skill will rewrite this file "
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
        "call subgraph). The `/dummyindex` (Claude) or `$dummyindex` (Codex) "
        "skill renames, regroups, and "
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
        'when the user asks about behavior ("how does login work?", "what\n'
        'happens on checkout?") rather than about symbols.\n'
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
        "   the `/dummyindex` (Claude) or `$dummyindex` (Codex) skill enriches,\n"
        "   these become the primary docs\n"
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
        "LLM (the active host session running the `dummyindex` skill) rewrote\n"
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
    *,
    project_name: str,
    slug: str | None = None,
    links: tuple[dict[str, Any], ...] = (),
    rank: SeedRank | None = None,
) -> dict[str, Any]:
    """The deterministic seed for `features/graph.json` (schema v2).

    Thin wrapper over :func:`scan.seed_scan` — the shape lives there; this
    exists so `builder` and `indexes` have one call site to write, and so
    the name the rest of the package already imports keeps working.

    v1 of this function denormalized the whole extraction into the viewer
    payload: folder → file → class → function → method → feature → flow. On
    this repo that was 4,083 nodes and 8,062 edges, which is a complete and
    completely unreadable answer to "how does this work?". Per-symbol
    navigation did not disappear with it — `map/symbols.json` and
    `features/symbol-graph.json` still carry every symbol and every call
    edge, and they are what agents actually query. What is gone is the
    pretense that dumping them into a force layout was a *map*.
    """
    return seed_scan(
        features,
        flows,
        project_name=project_name,
        slug=slug or slugify(project_name),
        links=links,
        rank=rank,
    ).to_dict()
