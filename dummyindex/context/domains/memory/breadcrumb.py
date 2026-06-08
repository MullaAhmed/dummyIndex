"""PreCompact breadcrumb: a deterministic, factual now.md entry.

Written before context is lost to compaction so a session is never blank
even if the handoff CTA is ignored. No prose, no LLM. Tagged with
AUTO_BREADCRUMB_TAG so a later agent-authored handoff supersedes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .._io import write_text_atomic
from ._parse import read_text_or_empty, render, split_sections
from .enums import AUTO_BREADCRUMB_TAG, TIER_HEADINGS, MemoryTier
from .models import Section
from .store import memory_dir

# How many changed-file paths to list before collapsing to "+k more".
MAX_LISTED_FILES = 8


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


def render_entry(facts: BreadcrumbFacts, now: datetime) -> Section:
    """Build the tagged `## …` breadcrumb section."""
    heading = f"## {now:%Y-%m-%d %H:%M} | {facts.branch} {AUTO_BREADCRUMB_TAG}"
    listed = list(facts.changed_files[:MAX_LISTED_FILES])
    more = len(facts.changed_files) - len(listed)
    touched = ", ".join(listed) if listed else "(no tracked changes)"
    if more > 0:
        touched += f", +{more} more"
    body = (
        f"Auto-saved before compaction. {facts.files_changed} files changed "
        f"(+{facts.insertions}/-{facts.deletions}); subagents: {facts.subagents}; "
        f"main turns: {facts.main_turns}.\n"
        f"Touched: {touched}."
    )
    return Section(heading, body)


def write_breadcrumb(context_dir: Path, facts: BreadcrumbFacts, now: datetime) -> bool:
    """Prepend the breadcrumb to now.md, or update the existing breadcrumb
    in place if the newest entry is already one. Returns True (written)."""
    now_path = memory_dir(context_dir) / MemoryTier.NOW.value
    preamble, sections = split_sections(read_text_or_empty(now_path))
    entry = render_entry(facts, now)
    if sections and AUTO_BREADCRUMB_TAG in sections[0].heading:
        new_sections = (entry, *sections[1:])
    else:
        new_sections = (entry, *sections)
    text = render(preamble or TIER_HEADINGS[MemoryTier.NOW], new_sections)
    write_text_atomic(now_path, text)
    return True
