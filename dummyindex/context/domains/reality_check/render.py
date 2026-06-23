"""Rendering — write the JSON + Markdown reality-check reports to disk."""

from __future__ import annotations

import json
from pathlib import Path

from ..atomic_io import write_text_atomic
from .models import RealityReport


def write_report(feat_dir: Path, report: RealityReport) -> tuple[Path, Path]:
    """Atomically write the JSON + MD reports."""
    feat_dir = feat_dir.resolve()
    feat_dir.mkdir(parents=True, exist_ok=True)
    json_path = feat_dir / "_reality-check.json"
    md_path = feat_dir / "_reality-check.md"
    write_text_atomic(
        json_path, json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    )
    write_text_atomic(md_path, render_report_md(report))
    return json_path, md_path


def render_report_md(report: RealityReport) -> str:
    lines: list[str] = [
        f"# Reality check — `{report.feature_id}`",
        "",
        (
            f"_{report.claims_total} concrete claim(s) extracted from "
            f"the chairman's docs: "
            f"**{report.verified} verified**, "
            f"**{report.contradicted} contradicted**, "
            f"**{report.ambiguous} ambiguous**._"
        ),
        "",
    ]
    if report.has_contradictions:
        lines.append("## Contradicted")
        lines.append("")
        lines.append(
            "These claims couldn't be reconciled with the AST. The original "
            "persona should revise or remove them on the next council pass."
        )
        lines.append("")
        for c in report.claims:
            if c.status != "contradicted":
                continue
            lines.append(f"- `{c.text}` ({c.source_file}) — {c.reason or 'no detail'}")
        lines.append("")
    ambig = [c for c in report.claims if c.status == "ambiguous"]
    if ambig:
        lines.append("## Ambiguous")
        lines.append("")
        lines.append(
            "Symbols exist but the relation couldn't be confirmed. Often "
            "indirect calls or aliases — worth a manual look."
        )
        lines.append("")
        for c in ambig:
            lines.append(f"- `{c.text}` ({c.source_file}) — {c.reason or '—'}")
        lines.append("")
    return "\n".join(lines) + "\n"
