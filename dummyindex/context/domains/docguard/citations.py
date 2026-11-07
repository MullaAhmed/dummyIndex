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


def added_citations(old: str, new: str) -> list[str]:
    """Citations present in ``new`` but absent from ``old`` (sorted, `/`-normalized)."""
    return sorted(_citations(new) - _citations(old))


def scan_durable(root: Path) -> list[tuple[str, list[str]]]:
    """Scan authored (not generated) markdown for disposable citations.

    ``root`` is the repo root (the directory holding ``.context/``). Returns
    ``(repo-relative posix path, sorted citations)`` for each citing file.
    """
    context = root / ".context"
    files: list[Path] = []
    features = context / "features"
    if features.is_dir():
        for name in _FEATURE_DOCS:
            files.extend(p for p in features.rglob(name) if p.is_file())
    conventions = context / "conventions"
    if conventions.is_dir():
        files.extend(
            p
            for p in conventions.glob("*.md")
            if p.is_file() and p.name not in _EXCLUDED_CONVENTIONS
        )
    for rel in ("architecture/overview.md", "PROJECT.md"):
        if (context / rel).is_file():
            files.append(context / rel)
    result = []
    for path in sorted(files):
        if "council" in path.relative_to(context).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        found = sorted(_citations(text))
        if found:
            result.append((path.relative_to(root).as_posix(), found))
    return result
