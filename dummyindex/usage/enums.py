"""Usage-area enums.

Closed-alphabet constants for the token-usage reporter. Real `str` values
(via `(str, Enum)`) so a report kind round-trips through CLI args without
conversion. Python 3.10-compatible (no `enum.StrEnum`, which lands in 3.11).
"""

from __future__ import annotations

from enum import Enum


class ReportKind(str, Enum):
    """Which token-usage report `dummyindex usage <kind>` renders.

    `CHAT` is the single-session view (the `/tokens` slash command); the rest
    aggregate every project's transcripts under `~/.claude/projects/`.
    """

    CHAT = "chat"
    DAILY = "daily"
    SESSION = "session"
    MONTHLY = "monthly"
    BLOCKS = "blocks"


# The `<model>` value Claude Code writes for injected, zero-usage placeholder
# turns (hook output, resume banners). Excluded from every aggregate.
SYNTHETIC_MODEL = "<synthetic>"
