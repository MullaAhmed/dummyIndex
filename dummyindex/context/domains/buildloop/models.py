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
payloads. ``dispatch_mode`` derives it: GATE and binding ``— via`` items
(plugin commands, skills, MCP-bound tools) belong to the main session and
are never offered as Task-dispatchable subagent units. Two via-tag shapes
ARE subagent units: an explicit ``— via agent:<name>`` tag, and a bare
``— via <name>`` that exactly matches a ``kind: agent`` equipment-pool
name passed via ``agent_names`` (the defensive upgrade — the caller
records it). With ``agent_names=None`` bare names stay main-session, so
pool-less callers see the historical behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DispatchMode(str, Enum):
    """How a checklist item is executed by the build skill."""

    SUBAGENT = "subagent"  # dispatch via the Task tool
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


# Prefix that turns a via tag into an explicit subagent dispatch target:
# `— via agent:<name>` names a Task-tool agent, not a binding main-session
# tool. The `<name>` is resolved (and fails safe) by the caller's mapper.
AGENT_VIA_PREFIX = "agent:"


def dispatch_mode(
    item: ChecklistItem, agent_names: frozenset[str] | None = None
) -> DispatchMode:
    """Classify where ``item`` executes.

    A GATE (human decision) item is always main-session — even when it
    also carries a via tag. A ``— via <tool>`` item is a subagent unit
    only when the tag names an agent: either explicitly with the
    ``agent:`` prefix (:data:`AGENT_VIA_PREFIX`), or as a bare name that
    exactly matches one of ``agent_names`` (the caller's kind-agent pool;
    the caller records the upgrade). Any other via tag binds the
    conductor's own tool/skill and stays main-session; so does a bare
    name when ``agent_names`` is ``None`` or has no match. Items without
    a gate or via tag are subagent dispatch units.
    """
    if item.gate:
        return DispatchMode.MAIN_SESSION
    if item.via is not None:
        if item.via.startswith(AGENT_VIA_PREFIX):
            return DispatchMode.SUBAGENT
        if agent_names is not None and item.via in agent_names:
            return DispatchMode.SUBAGENT
        return DispatchMode.MAIN_SESSION
    return DispatchMode.SUBAGENT
