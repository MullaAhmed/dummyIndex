"""Disposable-workspace citations in authored durable docs.

Pure text/filesystem helpers shared by the write-time guard, ``context check
--refs``, and proposal closeout. Imports nothing from ``proposals/`` (cycle).
"""

from __future__ import annotations

import re
from pathlib import Path

DISPOSABLE_REF = re.compile(r"(?:proposals|audits)[/\\][a-zA-Z0-9_-]+[/\\]")

_FEATURE_DOCS = ("spec.md", "plan.md", "concerns.md")
_EXCLUDED_CONVENTIONS = ("naming.md",)  # generated


def _normalize(match: str) -> str:
    return match.replace("\\", "/")


def cites_disposable(text: str) -> bool:
    return DISPOSABLE_REF.search(text) is not None


def _citations(text: str) -> set[str]:
    return {_normalize(m.group(0)) for m in DISPOSABLE_REF.finditer(text)}


def citations(text: str) -> set[str]:
    """Disposable-workspace citations in ``text`` (`/`-normalized)."""
    return _citations(text)


def added_citations(old: str, new: str) -> list[str]:
    """Citations present in ``new`` but absent from ``old`` (sorted, `/`-normalized)."""
    return sorted(_citations(new) - _citations(old))


def is_durable_doc(rel: str) -> bool:
    """True for authored durable markdown (repo-relative posix path).

    Authored set: ``features/*/{spec,plan,concerns}.md``, ``conventions/*.md``
    except generated ``naming.md``, ``architecture/overview.md`` and
    ``PROJECT.md`` under ``.context/``; nothing under ``council/``.
    """
    parts = rel.split("/")
    if len(parts) < 2 or parts[0] != ".context" or "council" in parts:
        return False
    inner = parts[1:]
    name = inner[-1]
    if inner == ["PROJECT.md"] or inner == ["architecture", "overview.md"]:
        return True
    if inner[0] == "features":
        return len(inner) >= 3 and name in _FEATURE_DOCS
    if inner[0] == "conventions":
        return (
            len(inner) == 2
            and name.endswith(".md")
            and name not in _EXCLUDED_CONVENTIONS
        )
    return False


def scan_durable(root: Path) -> list[tuple[str, list[str]]]:
    """Scan authored (not generated) markdown for disposable citations.

    ``root`` is the repo root (the directory holding ``.context/``). Returns
    ``(repo-relative posix path, sorted citations)`` for each citing file.
    """
    context = root / ".context"
    result = []
    if not context.is_dir():
        return result
    for path in sorted(p for p in context.rglob("*.md") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if not is_durable_doc(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        found = sorted(_citations(text))
        if found:
            result.append((rel, found))
    return result
