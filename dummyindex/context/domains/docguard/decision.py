"""Pure decision builder for the PreToolUse doc-write guard.

No I/O, no subprocess: maps a :class:`DocClassification` to the payload in the
exact shape Claude Code's PreToolUse hook consumes. No ``migrate-docs`` hint in
the deny reason: that command relocates *existing* files, while this guard fires
on a *fresh* write, so the only useful guidance is the managed home.
"""

from __future__ import annotations

from typing import Any

from .enums import DocRole
from .models import DocClassification

HOOK_EVENT_NAME = "PreToolUse"
PERMISSION_DENY = "deny"


def decide(classification: DocClassification) -> dict[str, Any]:
    """Map a classification to a PreToolUse decision payload.

    Returns ``deny`` only for a *placeable* stray: a planning doc outside
    ``.context/`` with a concrete ``suggested_home``. Anything else (non-planning,
    already managed, or unslug-able) returns ``{}``, which the guard treats as
    "print nothing, exit 0" — so the guard stays fail-open and never blocks a
    write it cannot redirect.
    """
    if not (classification.is_planning_doc and not classification.in_managed_location):
        return {}
    home = classification.suggested_home
    if not home:
        # Unplaceable stray (no slug-able content): nowhere coherent to point
        # the write, so fail open rather than emit a "None/spec.md" deny.
        return {}
    target = "spec.md" if classification.role is DocRole.SPEC else "plan.md"
    rel_path = classification.rel_path or ""
    reason = (
        f"{rel_path} is an internal planning doc; "
        f"write it to {home}/{target} instead of docs/."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "permissionDecision": PERMISSION_DENY,
            "permissionDecisionReason": reason,
        }
    }
