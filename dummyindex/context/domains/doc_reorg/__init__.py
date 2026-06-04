"""Gated in-place reorganisation of a repo's prose docs.

Public surface: discover the docs, refuse on a dirty tree, snapshot before any
edit, and restore. The actual rewriting is done by the running session (Edit
tool, per-file confirm); this package only makes it safe and reversible.
"""
from __future__ import annotations

from .discovery import discover_doc_files
from .enums import DocReorgAction
from .errors import BackupError, DirtyTreeError, DocReorgError
from .models import DocBackup, RestoreResult
from .safety import backup_docs, git_is_clean, require_clean_tree, restore_backup

__all__ = [
    "BackupError",
    "DirtyTreeError",
    "DocBackup",
    "DocReorgAction",
    "DocReorgError",
    "RestoreResult",
    "backup_docs",
    "discover_doc_files",
    "git_is_clean",
    "require_clean_tree",
    "restore_backup",
]
