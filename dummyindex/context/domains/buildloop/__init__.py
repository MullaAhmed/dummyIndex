"""Build loop — drive a proposal's ``checklist.md`` to completion.

The deterministic state layer behind ``dummyindex context build``:

- parse a proposal's flat ``checklist.md`` into items — including the
  structural ``**GATE**`` marker and trailing ``— via <tool>`` tag
  (``dispatch_mode`` classifies those as main-session items, never
  Task-dispatchable subagent units),
- map each unchecked item to the best-fit equipment item (capability-
  lexicon keyword overlap against ``.context/equipment.json``, item-kind
  aware: the implement-capable item is the default owner of checklist work
  and a specialist needs a scoring margin to take work from it;
  ``general-purpose`` fallback only when there's no implementer),
- atomically flip one ``- [ ]`` → ``- [x]`` as each item is verified, or
  close it as ``- [~] … — skipped: <reason>`` when scope is renegotiated.

The actual agent dispatch + verify-before-tick discipline live in the
``dummyindex-build`` skill (markdown), not here — this package is pure,
testable state management. When every item is ticked, the loop closes by
**reconciling** the new code into ``.context/`` (``dummyindex context
reconcile`` → place/enrich → ``reconcile-stamp``), not a bare deterministic
rebuild — a build adds files a rebuild would leave unassigned.

Public surface (kept stable for ``context/cli/*`` and tests):

- Dataclasses: ``ChecklistItem``, ``Choice``
- Enums: ``DispatchMode``
- Exception: ``BuildLoopError``
- Checklist ops: ``parse_checklist``, ``flip_item``, ``skip_item``, ``counts``
- Mapping: ``map_task_to_equipment``, ``dispatch_mode``
"""
from __future__ import annotations

from .checklist import counts, flip_item, next_wave, parse_checklist, skip_item
from .errors import BuildLoopError
from .mapping import map_task_to_equipment
from .models import ChecklistItem, Choice, DispatchMode, dispatch_mode

__all__ = [
    "BuildLoopError",
    "ChecklistItem",
    "Choice",
    "DispatchMode",
    "counts",
    "dispatch_mode",
    "flip_item",
    "map_task_to_equipment",
    "next_wave",
    "parse_checklist",
    "skip_item",
]
