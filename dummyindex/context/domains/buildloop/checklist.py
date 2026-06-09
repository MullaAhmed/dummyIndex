"""Parse + atomically flip a proposal's ``checklist.md``.

A checklist is a markdown list of ``- [ ]`` / ``- [x]`` lines (produced by
Slice A). This module is the deterministic state layer:

- ``parse_checklist`` reads the file into ``ChecklistItem`` tuples, each
  carrying a ``group`` id (see *waves* below).
- ``next_wave`` returns every unchecked item in the earliest incomplete
  group — the set the build skill may dispatch in parallel.
- ``flip_item`` sets exactly one ``- [ ]`` → ``- [x]`` and writes the
  file back atomically (tmp + replace). Flipping an already-ticked item is
  a no-op (idempotent). The ``key`` is either the 0-based item index (int
  or digit string) or a case-insensitive substring of the item text.
- ``counts`` returns ``(done, total)``.

Waves: a ``## Wave N — label`` (or ``## Group N``) heading opens a
PARALLEL group — every item under it shares one ``group`` id and is
mutually independent by construction (the plan step only groups tasks
that touch disjoint files). Any *other* heading (e.g. a ``# Checklist``
title) closes the open group, and items outside any wave heading each get
their own singleton group — so a legacy flat checklist stays strictly
serial. Group ids increase in document order; a wave only becomes
dispatchable once every earlier group is fully ticked.

No ``print`` here — the CLI owns stdout. Boundary failures raise
``BuildLoopError``.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Union

from .errors import BuildLoopError
from .models import ChecklistItem

# A checkbox line: optional indent, "- ", "[", a single fill char, "]",
# a space, then the item text. The fill char is " " (unchecked) or any
# non-space (treated as checked — "x" in practice).
_ITEM_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<mark>.)\]\s+(?P<text>.*\S)\s*$")

# Headings drive wave grouping. A heading whose text starts with "wave" or
# "group" opens a parallel group; any other heading closes it (so a plain
# title never accidentally parallelises a legacy flat checklist).
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_WAVE_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(?:wave|group)\b", re.IGNORECASE)


def parse_checklist(path: Path) -> tuple[ChecklistItem, ...]:
    """Parse ``checklist.md`` into an ordered tuple of items.

    Only checkbox lines become items; headings steer ``group`` assignment
    (wave headings open a shared group, other headings close it) and
    prose / blank lines are ignored, so a checklist may carry a title
    without breaking indexing.
    """
    if not path.is_file():
        raise BuildLoopError(f"checklist not found: {path}")
    items: list[ChecklistItem] = []
    next_group = 0
    in_wave = False          # an open `## Wave N` heading governs items below
    wave_group: int | None = None  # its id — assigned lazily at the first item,
    for line in path.read_text(encoding="utf-8").splitlines():  # so an empty
        m = _ITEM_RE.match(line)                  # heading never burns an id
        if m is None:
            if _WAVE_HEADING_RE.match(line):
                in_wave, wave_group = True, None
            elif _HEADING_RE.match(line):
                in_wave, wave_group = False, None
            continue
        if in_wave:
            if wave_group is None:
                wave_group = next_group
                next_group += 1
            group = wave_group
        else:
            group = next_group
            next_group += 1
        done = m.group("mark").strip().lower() == "x"
        items.append(
            ChecklistItem(index=len(items), text=m.group("text"), done=done, group=group)
        )
    return tuple(items)


def next_wave(items: tuple[ChecklistItem, ...]) -> tuple[ChecklistItem, ...]:
    """Every unchecked item sharing the first unchecked item's group.

    This is the parallel-dispatch frontier: groups are monotonic in
    document order, so the first unchecked item always belongs to the
    earliest incomplete group — and that group must finish before any
    later one starts. Returns ``()`` when everything is ticked.
    """
    first = next((it for it in items if not it.done), None)
    if first is None:
        return ()
    return tuple(it for it in items if not it.done and it.group == first.group)


def counts(items: tuple[ChecklistItem, ...]) -> tuple[int, int]:
    """Return ``(done, total)`` for a parsed checklist."""
    done = sum(1 for it in items if it.done)
    return done, len(items)


def _resolve_index(items: tuple[ChecklistItem, ...], key: Union[int, str]) -> int:
    """Map a user-supplied ``key`` to a 0-based item index.

    Accepts an int, a digit string (treated as an index), or a
    case-insensitive substring of the item text. Raises ``BuildLoopError``
    on no/ambiguous match so the CLI can surface a clear message.
    """
    if isinstance(key, int):
        idx = key
    elif isinstance(key, str) and key.strip().lstrip("-").isdigit():
        idx = int(key.strip())
    else:
        needle = str(key).strip().lower()
        matches = [it.index for it in items if needle in it.text.lower()]
        if not matches:
            raise BuildLoopError(f"no checklist item matches {key!r}")
        if len(matches) > 1:
            raise BuildLoopError(
                f"ambiguous checklist key {key!r} matches {len(matches)} items"
            )
        return matches[0]
    if idx < 0 or idx >= len(items):
        raise BuildLoopError(
            f"checklist index {idx} out of range (0..{len(items) - 1})"
        )
    return idx


def flip_item(path: Path, key: Union[int, str]) -> ChecklistItem:
    """Atomically set the item identified by ``key`` to ``- [x]``.

    Returns the resulting (ticked) item. Idempotent: if the target is
    already ticked, the file is left untouched and the existing item is
    returned. Only the n-th checkbox line in the file is rewritten — prose
    and other items are preserved verbatim.
    """
    items = parse_checklist(path)
    idx = _resolve_index(items, key)
    target = items[idx]
    if target.done:
        # No-op: already ticked. Don't rewrite the file (keeps mtime and
        # makes the operation truly idempotent).
        return target

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    seen = -1
    rewritten: list[str] = []
    flipped = False
    for line in lines:
        body = line.rstrip("\n")
        m = _ITEM_RE.match(body)
        if m is not None:
            seen += 1
            if seen == idx:
                newline = "\n" if line.endswith("\n") else ""
                rewritten.append(f"{m.group('indent')}- [x] {m.group('text')}{newline}")
                flipped = True
                continue
        rewritten.append(line)

    if not flipped:  # pragma: no cover - parse + rewrite agree by construction
        raise BuildLoopError(f"failed to locate checklist item {idx} for rewrite")

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(rewritten), encoding="utf-8")
    tmp.replace(path)
    return replace(target, done=True)
