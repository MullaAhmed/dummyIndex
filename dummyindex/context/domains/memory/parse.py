"""Markdown section helpers shared by the tier files.

A tier file is an H1 title (`# Now`) followed by zero or more `## …`
sections. These helpers split / re-join that shape so `roll` can relocate
whole sections without disturbing the rest.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Section


def read_text_or_empty(path: Path) -> str:
    """Return the UTF-8 text of *path*, or ``""`` when the file doesn't exist."""
    return path.read_text(encoding="utf-8") if path.exists() else ""


_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def split_sections(text: str) -> tuple[str, tuple[Section, ...]]:
    """Split markdown into ``(preamble, sections)`` on ``## `` headings.

    The preamble is everything before the first ``## `` line (e.g. the
    ``# Now`` title). Each Section keeps its heading verbatim and the body
    up to the next ``## `` line.
    """
    preamble: list[str] = []
    sections: list[Section] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is None:
                preamble = body
            else:
                sections.append(Section(heading, "\n".join(body).strip("\n")))
            heading = line
            body = []
        else:
            body.append(line)
    if heading is None:
        preamble = body
    else:
        sections.append(Section(heading, "\n".join(body).strip("\n")))
    return "\n".join(preamble).strip("\n"), tuple(sections)


def section_date(heading: str) -> str | None:
    """Return the first ``YYYY-MM-DD`` in a heading, or ``None``."""
    match = _DATE_RE.search(heading)
    return match.group(1) if match else None


def render(preamble: str, sections: tuple[Section, ...]) -> str:
    """Inverse of :func:`split_sections` — join into a text block."""
    parts: list[str] = []
    if preamble:
        parts.append(preamble)
    for section in sections:
        block = (
            section.heading
            if not section.body
            else f"{section.heading}\n{section.body}"
        )
        parts.append(block)
    return "\n\n".join(parts).rstrip("\n") + "\n"
