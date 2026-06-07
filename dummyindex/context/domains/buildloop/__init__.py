"""Build loop — drive a proposal's ``checklist.md`` to completion.

The deterministic state layer behind ``dummyindex context build``:

- parse a proposal's flat ``checklist.md`` into items,
- map each unchecked item to the best-fit equipment item (capability-
  lexicon keyword overlap against ``.context/equipment.json``; defaults to
  the implement-capable item when an equipped repo's task matches no
  specialist, ``general-purpose`` fallback only when there's no implementer),
- atomically flip one ``- [ ]`` → ``- [x]`` as each item is verified.

The actual agent dispatch + verify-before-tick discipline live in the
``dummyindex-build`` skill (markdown), not here — this package is pure,
testable state management. When every item is ticked, the loop closes by
re-indexing via ``dummyindex context rebuild --changed``.

Public surface (kept stable for ``context/cli/*`` and tests):

- Dataclasses: ``ChecklistItem``, ``Choice``
- Exception: ``BuildLoopError``
- Checklist ops: ``parse_checklist``, ``flip_item``, ``counts``
- Mapping: ``map_task_to_equipment``
"""
from __future__ import annotations

from .checklist import counts, flip_item, parse_checklist
from .errors import BuildLoopError
from .mapping import map_task_to_equipment
from .models import ChecklistItem, Choice

__all__ = [
    "BuildLoopError",
    "ChecklistItem",
    "Choice",
    "counts",
    "flip_item",
    "map_task_to_equipment",
    "parse_checklist",
]
