"""Style lint for authored docs: long sentences and filler words. Pure."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

__all__ = ["StyleViolation", "count_violations", "lint_text"]

_BOM = "﻿"
_MAX_WORDS = 20
_EXCERPT_CHARS = 60
_FENCE_PREFIXES = ("```", "~~~")
_LIST_RE = re.compile(r"(?:[-*+]|\d+[.)])\s+")
_CODE_RE = re.compile(r"(`+).*?\1")
_CODE_PLACEHOLDER = "CODE"
# Underscores at word edges are emphasis; inner underscores (snake_case) stay.
_EMPHASIS_RE = re.compile(r"(?<!\w)_+|_+(?!\w)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_FILLERS = (
    "in summary",
    "in conclusion",
    "to summarize",
    "it is important to note",
    "it's worth noting",
    "as mentioned",
    "basically",
    "simply",
    "just",
    "really",
    "actually",
    "let me",
    "hope this helps",
    "feel free",
)
_FILLER_RES = tuple(re.compile(rf"\b{re.escape(f)}\b", re.IGNORECASE) for f in _FILLERS)


@dataclass(frozen=True)
class StyleViolation:
    """One style finding; ``line`` is the 1-based first line of its unit."""

    line: int
    rule: Literal["long-sentence", "filler"]
    excerpt: str


def _word_count(sentence: str) -> int:
    return sum(1 for tok in sentence.split() if any(c.isalnum() for c in tok))


def _excerpt(sentence: str) -> str:
    return sentence[:_EXCERPT_CHARS].strip()


def _lint_unit(line: int, raw: str) -> list[StyleViolation]:
    text = _CODE_RE.sub(_CODE_PLACEHOLDER, raw)
    text = _EMPHASIS_RE.sub("", text.replace("*", ""))
    out: list[StyleViolation] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if _word_count(sentence) > _MAX_WORDS:
            out.append(StyleViolation(line, "long-sentence", _excerpt(sentence)))
        for pattern in _FILLER_RES:
            out.extend(
                StyleViolation(line, "filler", _excerpt(sentence))
                for _ in pattern.finditer(sentence)
            )
    return out


def lint_text(text: str) -> tuple[StyleViolation, ...]:
    """Style violations in Markdown ``text``; code, comments, tables, headings skipped."""
    out: list[StyleViolation] = []
    unit: list[str] = []
    unit_line = 0
    in_fence = False
    in_comment = False

    def flush() -> None:
        if unit:
            out.extend(_lint_unit(unit_line, " ".join(unit)))
            unit.clear()

    for lineno, raw in enumerate(text.removeprefix(_BOM).splitlines(), 1):
        stripped = raw.lstrip()
        if in_fence:
            in_fence = not stripped.startswith(_FENCE_PREFIXES)
            continue
        if stripped.startswith(_FENCE_PREFIXES):
            in_fence = True
            flush()
            continue
        if in_comment:
            in_comment = "-->" not in raw
            continue
        if "<!--" in raw:
            # Single-line comment: the whole line is skipped, nothing after it counts.
            in_comment = "-->" not in raw[raw.index("<!--") + len("<!--") :]
            flush()
            continue
        if not raw.strip():
            flush()
            continue
        if stripped.startswith(("|", "#")):
            flush()
            continue
        match = _LIST_RE.match(stripped)
        if match:
            flush()
            unit_line = lineno
            unit.append(stripped[match.end() :].strip())
            continue
        if not unit:
            unit_line = lineno
        unit.append(raw.strip())
    flush()
    return tuple(out)


def count_violations(path: Path) -> int:
    """Style violation count for a UTF-8 file; unreadable or non-UTF-8 files count 0."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    return len(lint_text(text))
