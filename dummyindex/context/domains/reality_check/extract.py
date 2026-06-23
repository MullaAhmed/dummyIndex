"""Claim extraction — pull regex-matchable claims out of the canonical docs.

Each claim arrives with a placeholder ``status="ambiguous"``; verification
(see :mod:`.verify`) replaces it with the AST-backed verdict.
"""
from __future__ import annotations

import re

from .models import Claim

# Sections we re-read. Order matters only for stable output ordering.
_CANONICAL_DOCS: tuple[str, ...] = (
    "plan.md",
    "concerns.md",
    "architecture.md",
    "implementation.md",
    "data-model.md",
    "security.md",
    "product.md",
)

# Claim patterns. Each yields a dict of named groups via re.finditer.
_CALL_RE = re.compile(
    r"`([A-Za-z_][\w.]*)(?:\(\))?`\s+calls?\s+`([A-Za-z_][\w.]*)(?:\(\))?`",
    re.IGNORECASE,
)
_USES_RE = re.compile(
    r"`([A-Za-z_][\w.]*)(?:\(\))?`\s+uses\s+`([A-Za-z_][\w.]*)(?:\(\))?`",
    re.IGNORECASE,
)
_FILE_LINE_RE = re.compile(
    r"`([\w./\-]+\.[A-Za-z0-9]{1,6}):(\d+)`"
)
_HAS_METHOD_RE = re.compile(
    r"(?:class\s+)?`([A-Za-z_][\w]*)`\s+has\s+(?:a\s+)?(?:method|function)\s+`([A-Za-z_][\w]*)(?:\(\))?`",
    re.IGNORECASE,
)


def _extract_claims(text: str, source_file: str) -> list[Claim]:
    """Pull every regex-matchable claim from ``text``."""
    out: list[Claim] = []
    seen: set[tuple[str, str, str]] = set()

    def _push(kind: str, subject: str, obj: str, raw: str) -> None:
        key = (kind, subject.lower(), obj.lower())
        if key in seen:
            return
        seen.add(key)
        out.append(Claim(
            text=raw.strip(),
            source_file=source_file,
            kind=kind,
            subject=subject,
            object=obj,
            status="ambiguous",
            reason=None,
        ))

    for m in _CALL_RE.finditer(text):
        _push("calls", m.group(1), m.group(2), m.group(0))
    for m in _USES_RE.finditer(text):
        _push("uses", m.group(1), m.group(2), m.group(0))
    for m in _HAS_METHOD_RE.finditer(text):
        _push("has_method", m.group(1), m.group(2), m.group(0))
    for m in _FILE_LINE_RE.finditer(text):
        _push("file:line", m.group(1), m.group(2), m.group(0))

    return out
