"""Frozen dataclasses + dispatch alphabet for the build loop.

Two tiny value objects, both immutable:

- ``ChecklistItem`` — one ``- [ ]`` / ``- [x]`` line parsed out of a
  proposal's ``checklist.md``. ``index`` is the 0-based position in the
  flat list (the key callers use for ``--check N``); ``done`` reflects
  whether the box is ticked. ``gate`` is True for human-decision items
  (text leads with a ``**GATE**`` / ``GATE`` marker) and ``via`` carries
  the tool name from a trailing ``— via <tool>`` tag — both parsed
  structurally so the CLI never re-derives them from prose.
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

``DispatchMode`` is the closed alphabet for *where an item executes* —
``(str, Enum)`` so ``.value`` lands wire-compatible in ``build --json``
payloads. ``dispatch_mode`` derives it: GATE and ``— via`` items belong to
the main session (a human decision, or a binding tool/skill invocation) and
are never offered as Task-dispatchable subagent units.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DispatchMode(str, Enum):
    """How a checklist item is executed by the build skill."""

    SUBAGENT = "subagent"          # dispatch via the Task tool
    MAIN_SESSION = "main-session"  # gate/via/interactive — run in THIS session


@dataclass(frozen=True)
class ChecklistItem:
    index: int
    text: str
    done: bool
    group: int = 0
    gate: bool = False
    via: str | None = None


@dataclass(frozen=True)
class Choice:
    item_text: str
    equipment_name: str | None
    fallback: bool
    grounding: tuple[str, ...]
    subagent_type: str | None = None


def dispatch_mode(item: ChecklistItem) -> DispatchMode:
    """Classify where ``item`` executes.

    A GATE (human decision) or ``— via <tool>`` (binding tool/skill
    invocation) item is a main-session item — the conductor handles it
    itself; everything else is a subagent dispatch unit.
    """
    if item.gate or item.via:
        return DispatchMode.MAIN_SESSION
    return DispatchMode.SUBAGENT
