"""Render a :class:`GraphQueryResult` as CLI markdown or machine JSON."""

from __future__ import annotations

import json
from dataclasses import replace

from .enums import EdgeDirection
from .models import GraphQueryResult


def _render_markdown(result: GraphQueryResult) -> str:
    """Render one result as the markdown the CLI prints by default."""
    title = f"# graph {result.verb}"
    if result.args:
        title += " " + " ".join(result.args)
    lines: list[str] = [title, ""]
    if result.subject is not None:
        s = result.subject
        lines.append(
            f"Subject: `{s.label}` `{s.node_id}` — {s.citation} "
            f"(community {s.community})"
        )
        if s.docstring:
            lines.append(f"> {s.docstring}")
        lines.append("")
    qualifier = " (truncated by row or byte budget)" if result.truncated else ""
    lines.append(f"_{len(result.rows)} of {result.total} row(s){qualifier}._")
    if result.note:
        lines.append(f"_{result.note}_")
    lines.append("")
    for row in result.rows:
        parts: list[str] = []
        if row.depth:
            parts.append(f"depth {row.depth}")
        if row.relation:
            if row.direction == EdgeDirection.IN.value:
                parts.append(f"←{row.relation}")
            else:
                parts.append(f"{row.relation}→")
        if row.site:
            parts.append(f"at {row.site}")
        meta = f"  [{', '.join(parts)}]" if parts else ""
        lines.append(f"- `{row.label}` `{row.node_id}` — {row.citation}{meta}")
        if row.docstring:
            lines.append(f"  > {row.docstring}")
        if row.resolution == "ambiguous":
            lines.append(
                f"  Ambiguous reference ({row.candidate_total} candidates); choose a cited symbol ID:"
            )
            lines.extend("  - " + candidate for candidate in row.candidates)
    return "\n".join(lines).rstrip() + "\n"


def _bounded(result: GraphQueryResult, max_bytes: int) -> GraphQueryResult:
    if not 512 <= max_bytes <= 65_536:
        raise ValueError("graph output budget must be between 512 and 65536 bytes")
    while (
        max(
            len((json.dumps(result.to_dict(), indent=2) + "\n").encode("utf-8")),
            len(_render_markdown(result).encode("utf-8")),
        )
        > max_bytes
    ):
        if not result.rows:
            raise ValueError(
                "graph subject or arguments exceed output budget; use a shorter symbol ID"
            )
        result = replace(result, rows=result.rows[:-1], truncated=True)
    return result


def render_markdown(result: GraphQueryResult, *, max_bytes: int = 16_000) -> str:
    return _render_markdown(_bounded(result, max_bytes))


def render_json(result: GraphQueryResult, *, max_bytes: int = 16_000) -> str:
    return json.dumps(_bounded(result, max_bytes).to_dict(), indent=2) + "\n"
