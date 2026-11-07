"""Lint a parsed checklist for live-testing steps.

Build checklists must be closeable by an unattended agent, so unticked
items that demand live, production, or manual verification are flagged.
An item carrying ``<!-- live-ok: <reason> -->`` opts out (false-positive
escape); ticked items are grandfathered. ``parse_checklist`` keeps the
HTML comment in ``ChecklistItem.text`` (it strips only ``task:`` markers).

No ``print`` here — callers own output.
"""

from __future__ import annotations

import re

from .models import ChecklistItem

_LIVE_RE = re.compile(
    r"\b(live[- ]tests?|live testing|production (test|run|smoke|verification)"
    r"|smoke[- ]tests?|manual(ly)? (test|verif\w*)"
    r"|against (production|staging|a live)|real (api|account)s?)\b",
    re.IGNORECASE,
)
_LIVE_OK_RE = re.compile(r"<!--\s*live-ok:\s*\S.*?-->", re.IGNORECASE)


def live_items(items: tuple[ChecklistItem, ...]) -> tuple[ChecklistItem, ...]:
    """Unticked items that mention live testing and carry no ``live-ok``."""
    return tuple(
        it
        for it in items
        if not it.done and _LIVE_RE.search(it.text) and not _LIVE_OK_RE.search(it.text)
    )
