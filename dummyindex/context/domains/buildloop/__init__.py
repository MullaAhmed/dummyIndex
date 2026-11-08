"""Build loop — drive a proposal's ``checklist.md`` to completion.

Deterministic state for ``dummyindex context build``: parse items (GATE and binding
``— via <tool>`` items run in the main session), map each to an equipment item,
atomically tick or skip boxes, and resolve the model-routing block. Dispatch and
verify-before-tick live in the ``dummyindex-build`` skill, never here. A finished
build reconciles into ``.context/``: a bare rebuild leaves its new files unassigned.
"""

from __future__ import annotations

from .checklist import counts, flip_item, next_wave, parse_checklist, skip_item
from .errors import BuildLoopError
from .mapping import map_task_to_equipment
from .models import AGENT_VIA_PREFIX, ChecklistItem, Choice, DispatchMode, dispatch_mode
from .routing import parse_route_flags, resolve_routing

__all__ = [
    "AGENT_VIA_PREFIX",
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
    "parse_route_flags",
    "resolve_routing",
    "skip_item",
]
