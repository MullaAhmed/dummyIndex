"""In-flight checks shared by proposal deletion and equipment GC candidates.

A proposal is in flight when its ``proposal.json`` status is ``in_progress`` or its
checklist has unchecked boxes. Deleting or retiring such a workspace would drop a
plan a ``/dummyindex-build`` is still executing.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..buildloop.checklist import counts, parse_checklist


def _liveness_block(target: Path) -> str | None:
    """Return a refusal reason if the proposal is in-flight, else ``None``.

    In-flight = ``proposal.json`` status ``in_progress`` or any unchecked
    checklist box. An unreadable/absent file simply contributes no block.
    """
    if _proposal_status(target) == "in_progress":
        return "in-flight (status in_progress)"
    if _checklist_partial(target):
        return "in-flight (checklist partial)"
    return None


def _proposal_status(target: Path) -> str | None:
    """Read ``proposal.json``'s ``status`` field, tolerantly (``None`` on miss)."""
    path = target / "proposal.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return status if isinstance(status, str) else None


def _checklist_partial(target: Path) -> bool:
    """Whether ``checklist.md`` has any unchecked box (``done < total``).

    An absent, unparseable or empty checklist is not partial (no block).
    """
    path = target / "checklist.md"
    if not path.is_file():
        return False
    try:
        items = parse_checklist(path)
    except Exception:  # noqa: BLE001 — a malformed checklist must not block GC
        return False
    done, total = counts(items)
    if total == 0:
        return False
    return done < total
