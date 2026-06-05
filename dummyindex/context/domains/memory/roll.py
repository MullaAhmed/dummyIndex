"""Relocate dated tier entries downward. Deterministic + idempotent.

``now.md`` sections dated before today move into ``recent.md``;
``recent.md`` sections older than ``recent_keep_days`` move into
``archive.md``. Sections with no parseable date stay put. Compression of
the relocated prose is the agent's job, not this function's.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

from ._parse import render, section_date, split_sections
from .enums import TIER_HEADINGS, MemoryTier
from .models import RollReport, Section
from .store import memory_dir, write_text_atomic


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _partition(
    sections: tuple[Section, ...], predicate: Callable[[Section], bool]
) -> tuple[list[Section], list[Section]]:
    keep: list[Section] = []
    move: list[Section] = []
    for section in sections:
        (move if predicate(section) else keep).append(section)
    return keep, move


def _sort_desc(sections: list[Section]) -> tuple[Section, ...]:
    """Newest date first; undated sections sort last, order preserved."""
    return tuple(
        sorted(sections, key=lambda s: section_date(s.heading) or "", reverse=True)
    )


def _ordinal(iso_date: str) -> int:
    year, month, day = (int(part) for part in iso_date.split("-"))
    return date(year, month, day).toordinal()


def roll_tiers(
    context_dir: Path,
    *,
    today: date | None = None,
    recent_keep_days: int = 7,
) -> RollReport:
    """Roll stale sections down through the now → recent → archive tiers.

    Sections that survive in a tier after a roll are re-sorted newest-date-first;
    undated sections sort last, preserving their original order.
    """
    today = today or date.today()
    today_str = today.isoformat()
    cutoff_ordinal = today.toordinal() - recent_keep_days

    mdir = memory_dir(context_dir)
    now_path = mdir / MemoryTier.NOW.value
    recent_path = mdir / MemoryTier.RECENT.value
    archive_path = mdir / MemoryTier.ARCHIVE.value

    now_pre, now_secs = split_sections(_read(now_path))
    rec_pre, rec_secs = split_sections(_read(recent_path))
    arc_pre, arc_secs = split_sections(_read(archive_path))

    def _is_before_today(section: Section) -> bool:
        iso = section_date(section.heading)
        return iso is not None and iso < today_str

    def _is_stale_recent(section: Section) -> bool:
        iso = section_date(section.heading)
        return iso is not None and _ordinal(iso) < cutoff_ordinal

    now_keep, now_down = _partition(now_secs, _is_before_today)
    rec_pool = list(rec_secs) + now_down
    rec_keep, rec_down = _partition(tuple(rec_pool), _is_stale_recent)
    arc_all = list(arc_secs) + rec_down

    if not now_down and not rec_down:
        return RollReport()  # nothing relocated → leave files byte-for-byte unchanged

    if now_down:
        write_text_atomic(
            now_path, render(now_pre or TIER_HEADINGS[MemoryTier.NOW], _sort_desc(now_keep))
        )
    if now_down or rec_down:
        write_text_atomic(
            recent_path,
            render(rec_pre or TIER_HEADINGS[MemoryTier.RECENT], _sort_desc(rec_keep)),
        )
    if rec_down:
        write_text_atomic(
            archive_path,
            render(arc_pre or TIER_HEADINGS[MemoryTier.ARCHIVE], _sort_desc(arc_all)),
        )

    moved = now_down + rec_down
    moved_dates = tuple(
        sorted({iso for s in moved if (iso := section_date(s.heading)) is not None})
    )
    return RollReport(
        now_to_recent=len(now_down),
        recent_to_archive=len(rec_down),
        moved_dates=moved_dates,
    )
