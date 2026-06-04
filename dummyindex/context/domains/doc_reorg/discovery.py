"""Find the in-repo prose docs a reorg may touch.

Reuses the source-docs default discovery, then expands directories (``docs/``,
``adr/``, …) into their individual text files. Only rewritable text formats are
in scope — binaries (pdf/docx/xlsx) are never reorganised in place.
"""
from __future__ import annotations

import os
from pathlib import Path

from dummyindex.context.domains.source_docs.discovery import (
    discover_default_doc_paths,
)

# Rewritable prose formats only. A reorg edits text in place; it never touches
# binary docs even when the catalog tracks them.
_REWRITABLE_EXTS: frozenset[str] = frozenset({".md", ".mdx", ".rst", ".txt"})

_SKIP_DIRS: frozenset[str] = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", ".context"}
)


def discover_doc_files(root: Path) -> tuple[Path, ...]:
    """Absolute paths of every rewritable in-repo doc, deduplicated and sorted."""
    root = root.resolve()
    out: set[Path] = set()
    for path in discover_default_doc_paths(root):
        if path.is_file():
            if path.suffix.lower() in _REWRITABLE_EXTS:
                out.add(path)
        elif path.is_dir():
            out.update(_walk(path))
    return tuple(sorted(out))


def _walk(doc_dir: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(doc_dir):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in _REWRITABLE_EXTS:
                found.append(p.resolve())
    return found
