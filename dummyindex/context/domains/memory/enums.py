"""Closed alphabet for the session-memory store."""
from __future__ import annotations

from enum import Enum


class MemoryTier(str, Enum):
    """The on-disk tier files under `.context/session-memory/`."""

    NOW = "now.md"
    RECENT = "recent.md"
    ARCHIVE = "archive.md"
    CORE = "core-memories.md"


class MemoryVerb(str, Enum):
    """The verbs accepted by `dummyindex context memory <verb>`."""

    SESSION_START = "session-start"
    ROLL = "roll"
    INIT = "init"


# The H1 title each freshly-seeded tier file carries.
TIER_HEADINGS: dict[MemoryTier, str] = {
    MemoryTier.NOW: "# Now",
    MemoryTier.RECENT: "# Recent",
    MemoryTier.ARCHIVE: "# Archive",
    MemoryTier.CORE: "# Core memories",
}
