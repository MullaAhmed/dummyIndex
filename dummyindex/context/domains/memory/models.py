"""Frozen data carriers for the session-memory domain."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """A `## …` markdown section: its heading line and its body text."""

    heading: str
    body: str


@dataclass(frozen=True)
class RollReport:
    """What a single `roll_tiers` call relocated."""

    now_to_recent: int = 0
    recent_to_archive: int = 0
    moved_dates: tuple[str, ...] = ()
