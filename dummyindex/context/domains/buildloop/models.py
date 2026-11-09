"""Frozen dataclasses + dispatch alphabet for the build loop.

``ChecklistItem`` is one parsed checklist line; ``index`` is its 0-based
``--check N`` key. ``Choice`` is an item's equipment mapping: ``fallback=True``
(``equipment_name=None``) or ``subagent_type=None`` makes the CLI render
``general-purpose``, a literal the model never stores. ``DispatchMode`` is
``(str, Enum)`` so ``.value`` is wire-compatible in ``build --json``.
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
    item_id: str = ""


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

    A GATE item is always main-session, even with a via tag. A via item is a
    subagent unit only when the tag names an agent: the ``agent:`` prefix
    (:data:`AGENT_VIA_PREFIX`) or a bare name in ``agent_names`` (the caller's
    kind-agent pool; the caller records the upgrade). Other via tags bind the
    conductor's own tool and stay main-session. Items with neither are subagents.
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
