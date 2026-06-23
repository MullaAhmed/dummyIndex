"""Create and locate the `.context/session-memory/` tier store."""

from __future__ import annotations

from pathlib import Path

from ..atomic_io import write_text_atomic
from .enums import TIER_HEADINGS, MemoryTier


def memory_dir(context_dir: Path) -> Path:
    """The session-memory store directory inside a `.context/` directory."""
    return context_dir / "session-memory"


def ensure_memory_store(context_dir: Path) -> tuple[str, ...]:
    """Create `session-memory/` + empty tier stubs if missing.

    Idempotent and **non-destructive**: an existing tier file is never
    overwritten. Returns the tier filenames newly created this call.
    """
    created: list[str] = []
    mdir = memory_dir(context_dir)
    mdir.mkdir(parents=True, exist_ok=True)
    for tier in MemoryTier:
        path = mdir / tier.value
        if path.exists():
            continue
        write_text_atomic(path, TIER_HEADINGS[tier] + "\n")
        created.append(tier.value)
    return tuple(created)
