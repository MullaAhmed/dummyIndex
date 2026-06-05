"""Session-memory store: a markdown-first, agent-maintained remember-equivalent.

Deterministic mechanics live here; prose (writing/compressing summaries)
is the agent's job via the `/dummyindex-remember` skill.
"""
from __future__ import annotations

from .detect import remember_plugin_present
from .emit import render_session_start
from .enums import TIER_HEADINGS, MemoryTier
from .errors import MemoryStoreError, SessionMemoryError
from .models import RollReport, Section
from .roll import roll_tiers
from .store import (
    ensure_memory_store,
    memory_dir,
    tier_path,
    write_text_atomic,
)

__all__ = [
    "MemoryTier",
    "TIER_HEADINGS",
    "RollReport",
    "Section",
    "SessionMemoryError",
    "MemoryStoreError",
    "ensure_memory_store",
    "memory_dir",
    "tier_path",
    "write_text_atomic",
    "remember_plugin_present",
    "render_session_start",
    "roll_tiers",
]
