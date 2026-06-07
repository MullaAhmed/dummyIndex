"""Frozen dataclasses for the build loop.

Two tiny value objects, both immutable:

- ``ChecklistItem`` — one ``- [ ]`` / ``- [x]`` line parsed out of a
  proposal's ``checklist.md``. ``index`` is the 0-based position in the
  flat list (the key callers use for ``--check N``); ``done`` reflects
  whether the box is ticked.
- ``Choice`` — the outcome of mapping one checklist item to an equipment
  item. When nothing scores, the mapper still routes to the manifest's
  implement-capable item if one exists (``fallback=False``) — the work is
  implementation. ``fallback`` is ``True`` and ``equipment_name`` is ``None``
  only when the manifest is empty, or has items but no implement-capable one;
  the CLI/skill renders the ``general-purpose`` agent name at that point. The
  model itself never stores that literal (the manifest didn't produce it).
  ``subagent_type`` is the chosen item's dispatch target (the build skill's
  Task-tool agent), or ``None`` when the item declared none / a fallback
  occurred — the CLI renders the ``general-purpose`` fallback there too.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChecklistItem:
    index: int
    text: str
    done: bool


@dataclass(frozen=True)
class Choice:
    item_text: str
    equipment_name: str | None
    fallback: bool
    grounding: tuple[str, ...]
    subagent_type: str | None = None
