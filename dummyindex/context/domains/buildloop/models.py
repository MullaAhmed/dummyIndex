"""Frozen dataclasses for the build loop.

Two tiny value objects, both immutable:

- ``ChecklistItem`` — one ``- [ ]`` / ``- [x]`` line parsed out of a
  proposal's ``checklist.md``. ``index`` is the 0-based position in the
  flat list (the key callers use for ``--check N``); ``done`` reflects
  whether the box is ticked.
- ``Choice`` — the outcome of mapping one checklist item to an equipment
  item. When nothing in the manifest matches, ``fallback`` is ``True`` and
  ``equipment_name`` is ``None`` — the CLI/skill renders the
  ``general-purpose`` agent name at that point; the model itself never
  stores that literal (the manifest didn't produce it).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChecklistItem:
    index: int
    text: str
    done: bool


@dataclass(frozen=True)
class Choice:
    item_text: str
    equipment_name: Optional[str]
    fallback: bool
    grounding: tuple[str, ...]
