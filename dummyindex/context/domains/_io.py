"""Shared I/O helper for domain store modules.

Kept in the `domains` package so any domain store can import without
creating cross-domain dependencies.
"""
from __future__ import annotations

from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a tmp file + ``replace`` (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
