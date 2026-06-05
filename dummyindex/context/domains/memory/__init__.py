"""Session-memory store: a markdown-first, agent-maintained remember-equivalent.

Deterministic mechanics live here; prose (writing/compressing summaries)
is the agent's job via the `/dummyindex-remember` skill.
"""
from __future__ import annotations

from .detect import remember_plugin_present
from .emit import render_session_start
from .enums import TIER_HEADINGS, MemoryTier, MemoryVerb
from .models import RollReport, Section
from .roll import roll_tiers
from .store import (
    ensure_memory_store,
    memory_dir,
)

__all__ = [
    "MemoryTier",
    "MemoryVerb",
    "TIER_HEADINGS",
    "RollReport",
    "Section",
    "ensure_memory_store",
    "memory_dir",
    "remember_plugin_present",
    "render_session_start",
    "roll_tiers",
]
