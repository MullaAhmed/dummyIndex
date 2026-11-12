"""Style lint for authored docs: STE-shaped rules. Pure, no NLP.

Strict rules count toward the style ratchet. Advice rules only print: a regex
cannot tell every gerund or allowed passive apart, so they never fail a check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

__all__ = ["StyleViolation", "count_violations", "lint_text"]

Severity = Literal["strict", "advice"]
Rule = Literal[
    "long-sentence",
    "long-paragraph",
    "contraction",
    "semicolon",
    "filler",
    "ing-form",
    "passive",
]

_BOM = "﻿"
_MAX_WORDS = 20
_MAX_SENTENCES = 6
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
_APOS = "['’]"
_CONTRACTION_RE = re.compile(
    rf"\b\w+n{_APOS}t\b"
    rf"|\b\w+{_APOS}(?:re|ll|ve|d|m)\b"
    rf"|\b(?:it|that|there|what){_APOS}s\b",
    re.IGNORECASE,
)
_SEMICOLON_RE = re.compile(";")
_ING_RE = re.compile(r"\b[a-z]{2,}ing\b", re.IGNORECASE)
# Closed list of -ing words that are nouns, not verb forms.
_ING_ALLOW = frozenset(
    {
        "string",
        "strings",
        "thing",
        "things",
        "during",
        "nothing",
        "something",
        "anything",
        "everything",
        "morning",
        "evening",
        "spring",
        "ceiling",
        "sibling",
        "siblings",
        "king",
        "ring",
        "wing",
    }
)
_BE_FORMS = ("am", "is", "are", "was", "were", "be", "been", "being")
_IRREGULAR_PARTICIPLES = (
    "written|given|taken|made|done|built|sent|shown|found|known|seen|chosen"
    "|kept|held|set|put|read|lost|brought|bought|caught|taught|thought|told|sold"
)
_PASSIVE_RE = re.compile(
    rf"\b(?:{'|'.join(_BE_FORMS)})\s+(?:\w{{2,}}ed|{_IRREGULAR_PARTICIPLES})\b",
    re.IGNORECASE,
)
_SEVERITY: dict[str, Severity] = {
    "long-sentence": "strict",
    "long-paragraph": "strict",
    "contraction": "strict",
    "semicolon": "strict",
    "filler": "strict",
    "ing-form": "advice",
    "passive": "advice",
}


@dataclass(frozen=True)
class StyleViolation:
    """One style finding; ``line`` is the 1-based first line of its unit."""

    line: int
    rule: Rule
    excerpt: str
    severity: Severity = "strict"


def _word_count(sentence: str) -> int:
    return sum(1 for tok in sentence.split() if any(c.isalnum() for c in tok))


def _excerpt(sentence: str) -> str:
    return sentence[:_EXCERPT_CHARS].strip()


def _v(line: int, rule: Rule, excerpt: str) -> StyleViolation:
    return StyleViolation(line, rule, _excerpt(excerpt), _SEVERITY[rule])


def _lint_unit(line: int, raw: str) -> list[StyleViolation]:
    text = _CODE_RE.sub(_CODE_PLACEHOLDER, raw)
    text = _EMPHASIS_RE.sub("", text.replace("*", ""))
    out: list[StyleViolation] = []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text)]
    if len(sentences) > _MAX_SENTENCES:
        out.append(_v(line, "long-paragraph", text))
    for sentence in sentences:
        if _word_count(sentence) > _MAX_WORDS:
            out.append(_v(line, "long-sentence", sentence))
        for pattern in _FILLER_RES:
            out.extend(_v(line, "filler", sentence) for _ in pattern.finditer(sentence))
        out.extend(
            _v(line, "contraction", sentence)
            for _ in _CONTRACTION_RE.finditer(sentence)
        )
        out.extend(
            _v(line, "semicolon", sentence) for _ in _SEMICOLON_RE.finditer(sentence)
        )
        out.extend(
            _v(line, "ing-form", sentence)
            for m in _ING_RE.finditer(sentence)
            if m.group(0).lower() not in _ING_ALLOW
        )
        out.extend(
            _v(line, "passive", sentence) for _ in _PASSIVE_RE.finditer(sentence)
        )
    return out


def _frontmatter_end(lines: list[str]) -> int:
    """Index of the closing ``---`` of a leading YAML block, or -1."""
    if not lines or lines[0].strip() != "---":
        return -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return idx
    return -1


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

    lines = text.removeprefix(_BOM).splitlines()
    front_end = _frontmatter_end(lines)
    for idx, raw in enumerate(lines):
        lineno = idx + 1
        if idx <= front_end:
            continue
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
    """Strict violation count for a UTF-8 file; unreadable or non-UTF-8 files count 0."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    return sum(1 for v in lint_text(text) if v.severity == "strict")
