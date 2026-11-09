"""Ownership probe for an existing ``.context/`` directory.

The marker is ``.context/meta.json`` with a ``dummyindex_version`` field (every
build writes one); other tools use ``.context/`` too, and dummyindex must never
claim a foreign one. Never raises: a bad ``meta.json`` in a non-empty dir reads
FOREIGN. Deliberately not ``context.build.meta.read_meta``, which raises on a
**newer** ``schema_version`` that must still read as OURS.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

_META_FILENAME = "meta.json"
_OWNERSHIP_MARKER = "dummyindex_version"


class ContextOwnership(str, Enum):
    """Who an existing ``.context/`` directory belongs to."""

    ABSENT = "absent"  # no .context/, or an empty one — safe to create
    OURS = "ours"  # meta.json carries dummyindex_version — ours to manage
    FOREIGN = "foreign"  # content present without our marker — hands off


def context_ownership(context_dir: Path) -> ContextOwnership:
    """Classify ``context_dir`` (a ``.context/`` path) by ownership.

    ``ABSENT``: missing or empty (writing creates, never clobbers). ``OURS``:
    ``meta.json`` is a JSON object with a ``dummyindex_version`` key.
    ``FOREIGN``: anything else with content, including an unreadable marker;
    callers must not write into it. Never raises.
    """
    if not context_dir.is_dir():
        return ContextOwnership.ABSENT
    if _is_empty_dir(context_dir):
        return ContextOwnership.ABSENT
    if _has_dummyindex_marker(context_dir / _META_FILENAME):
        return ContextOwnership.OURS
    return ContextOwnership.FOREIGN


def _is_empty_dir(path: Path) -> bool:
    """True when ``path`` has no entries. Unreadable reads as non-empty."""
    try:
        return next(iter(path.iterdir()), None) is None
    except OSError:
        return False


def _has_dummyindex_marker(meta_path: Path) -> bool:
    """True when ``meta_path`` is a JSON object carrying our version marker."""
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(raw, dict) and _OWNERSHIP_MARKER in raw
