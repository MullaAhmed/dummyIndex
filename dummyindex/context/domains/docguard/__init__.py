"""docguard: the shared stray-planning-doc classifier (managed-doc-home).

Single source of truth for "this ``.md`` is an internal planning artifact that
leaked outside ``.context/``, and here is its managed home". The migration command
and the PreToolUse write-guard both consume this one classifier so they can never
disagree. ``classify_doc_path`` is location-gated and does no I/O.
"""

from __future__ import annotations

from .classify import classify_doc_path, group_strays
from .enums import DocKind, DocRole
from .errors import DocGuardError, DocPathError
from .models import DocClassification, StrayGroup

__all__ = [
    "DocClassification",
    "DocGuardError",
    "DocKind",
    "DocPathError",
    "DocRole",
    "StrayGroup",
    "classify_doc_path",
    "group_strays",
]
