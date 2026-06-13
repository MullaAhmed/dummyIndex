"""Ownership probe for an existing ``.context/`` directory.

dummyindex's de-facto ownership marker is ``.context/meta.json`` carrying a
``dummyindex_version`` field — every build writes one. Other tools also use a
``.context/`` folder (docs, plain-markdown agent memory, …); dummyindex must
only claim and manage a ``.context/`` that carries its own marker, never a
foreign one.

Tolerant by design: a missing, unreadable, or malformed ``meta.json`` inside a
non-empty ``.context/`` classifies as FOREIGN (refuse to claim) — it never
raises. The probe deliberately does *not* reuse the strict
``context.build.meta.read_meta`` loader: an index written by a **newer**
dummyindex (higher ``schema_version``) must still read as OURS, and
``read_meta`` raises on it.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

_META_FILENAME = "meta.json"
_OWNERSHIP_MARKER = "dummyindex_version"


class ContextOwnership(str, Enum):
    """Who an existing ``.context/`` directory belongs to."""

    ABSENT = "absent"     # no .context/, or an empty one — safe to create
    OURS = "ours"         # meta.json carries dummyindex_version — ours to manage
    FOREIGN = "foreign"   # content present without our marker — hands off


def context_ownership(context_dir: Path) -> ContextOwnership:
    """Classify ``context_dir`` (a ``.context/`` path) by ownership.

    - ``ABSENT`` — the directory is missing or empty: writing creates, never
      clobbers.
    - ``OURS`` — ``meta.json`` parses as a JSON object with a
      ``dummyindex_version`` key.
    - ``FOREIGN`` — anything else with content: another tool's ``.context/``,
      or one whose marker can't be read. Callers must not write into it.

    Never raises; unreadable state classifies as FOREIGN (the conservative
    choice — don't claim what can't be verified).
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
