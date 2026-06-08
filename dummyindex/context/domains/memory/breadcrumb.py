"""PreCompact breadcrumb: a deterministic, factual now.md entry.

Written before context is lost to compaction so a session is never blank
even if the handoff CTA is ignored. No prose, no LLM. Tagged with
AUTO_BREADCRUMB_TAG so a later agent-authored handoff supersedes it.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from dummyindex.usage.transcripts import load_session

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


def _git_text(root: Path, *args: str) -> str:
    """Run a git command in *root*, returning stdout or "" on any failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout


def _git_branch(root: Path) -> str:
    branch = _git_text(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return branch or "unknown"


def _git_diffstat(root: Path) -> tuple[int, int, int, tuple[str, ...]]:
    """(files_changed, insertions, deletions, changed_files) vs HEAD.

    Parses `git diff --numstat HEAD`; binary files report '-' for counts and
    are counted as changed files with zero line deltas.
    """
    out = _git_text(root, "diff", "--numstat", "HEAD")
    files: list[str] = []
    insertions = 0
    deletions = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        add_s, del_s, path = parts
        insertions += int(add_s) if add_s.isdigit() else 0
        deletions += int(del_s) if del_s.isdigit() else 0
        files.append(path)
    return len(files), insertions, deletions, tuple(files)


def gather_breadcrumb_facts(
    root: Path, main_transcript: Optional[Path]
) -> BreadcrumbFacts:
    """Collect deterministic session facts: git state + transcript counts."""
    branch = _git_branch(root)
    files_changed, insertions, deletions, changed_files = _git_diffstat(root)
    main_turns = 0
    subagents = 0
    if main_transcript is not None and main_transcript.exists():
        turns, _sub_turns, subagents = load_session(main_transcript)
        main_turns = len(turns)
    return BreadcrumbFacts(
        branch=branch,
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
        changed_files=changed_files,
        main_turns=main_turns,
        subagents=subagents,
    )
