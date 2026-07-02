"""Pure decision builder for the PreToolUse doc-write guard.

No I/O, no subprocess — just maps a :class:`DocClassification` to the JSON-shaped
PreToolUse decision payload the guard prints. A *placeable* stray planning doc
(a planning doc not already in a managed location, for which the classifier
produced a concrete ``suggested_home``) yields a ``deny`` payload whose reason
interpolates that home and the spec/plan filename; everything else yields ``{}``
(allow — the guard prints nothing and exits 0).

The deny payload is the exact shape Claude Code's PreToolUse hook consumes::

    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "<rel_path> is an internal planning doc; "
            "write it to <suggested_home>/<spec.md|plan.md> instead of docs/."}}

No ``migrate-docs`` suggestion appears here: that command relocates *existing*
files, while this guard fires on a *fresh* write, so the only useful guidance is
the managed home the doc should have been written to in the first place.
"""

from __future__ import annotations

from typing import Any

from .enums import DocRole
from .models import DocClassification

HOOK_EVENT_NAME = "PreToolUse"
PERMISSION_DENY = "deny"


def decide(classification: DocClassification) -> dict[str, Any]:
    """Map a classification to a PreToolUse decision payload.

    Returns the ``deny`` payload only for a *placeable* stray — a planning doc
    that is not already in a managed location and for which the classifier
    produced a concrete ``suggested_home`` to point at. Every other path — a
    non-planning doc, a doc already under ``.context/``, or an unslug-able stray
    with no coherent home to suggest — returns ``{}`` (allow). The guard treats
    ``{}`` as "print nothing, exit 0", so this builder is what keeps the guard
    fail-open: it only ever asks to block when it can name where the doc belongs.
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
