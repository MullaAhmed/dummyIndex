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


@dataclass(frozen=True)
class BreadcrumbFacts:
    """Deterministic session facts captured for a breadcrumb entry."""

    branch: str
    files_changed: int
    insertions: int
    deletions: int
    changed_files: tuple[str, ...]
    main_turns: int
    subagents: int
