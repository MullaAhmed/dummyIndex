"""docguard: the shared stray-planning-doc classifier (managed-doc-home).

Single source of truth for "this ``.md`` is an internal planning artifact that
leaked outside ``.context/``, and here is the managed home it belongs in." The
migration command and the PreToolUse write-guard both consume this one
classifier so they can never disagree.

Public surface (the migration domain + write-guard import target):

- ``DocKind``, ``DocRole`` — closed alphabets
- ``DocClassification``, ``StrayGroup`` — frozen dataclasses
- ``DocGuardError``, ``DocPathError`` — typed errors
- ``classify_doc_path`` — verdict for one path (location-gated, no I/O)
- ``group_strays`` — pair + group + collision-disambiguate placeable strays
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
