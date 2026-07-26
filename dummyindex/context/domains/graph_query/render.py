"""Render a :class:`GraphQueryResult` as CLI markdown or machine JSON."""

from __future__ import annotations

import json

from .enums import EdgeDirection
from .models import GraphQueryResult


def render_markdown(result: GraphQueryResult) -> str:
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
    qualifier = " (truncated by --limit)" if result.truncated else ""
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
    return "\n".join(lines).rstrip() + "\n"


def render_json(result: GraphQueryResult) -> str:
    return json.dumps(result.to_dict(), indent=2) + "\n"
