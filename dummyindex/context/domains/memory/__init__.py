"""Session-memory store: a markdown-first, agent-maintained remember-equivalent.

Deterministic mechanics live here; prose (writing/compressing summaries)
is the agent's job via the `/dummyindex-remember` skill.
"""

from __future__ import annotations

from .breadcrumb import (
    BreadcrumbFacts,
    build_breadcrumb_facts,
    run_breadcrumb,
    write_breadcrumb,
)
from .detect import remember_plugin_present
from .emit import render_session_start
from .enums import AUTO_BREADCRUMB_TAG, TIER_HEADINGS, MemoryTier, MemoryVerb
from .models import RollReport, Section
from .nudge import decide_nudge
from .roll import roll_tiers
from .store import (
    ensure_memory_store,
    memory_dir,
)
from .transcript import (
    SessionSignal,
    find_main_transcript,
    read_session_signal,
    resolve_session_id,
)

__all__ = [
    "AUTO_BREADCRUMB_TAG",
    "BreadcrumbFacts",
    "MemoryTier",
    "MemoryVerb",
    "TIER_HEADINGS",
    "RollReport",
    "Section",
    "SessionSignal",
    "build_breadcrumb_facts",
    "decide_nudge",
    "ensure_memory_store",
    "find_main_transcript",
    "memory_dir",
    "read_session_signal",
    "remember_plugin_present",
    "render_session_start",
    "resolve_session_id",
    "roll_tiers",
    "run_breadcrumb",
    "write_breadcrumb",
]
