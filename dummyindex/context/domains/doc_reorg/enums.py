"""Fixed alphabet for the doc-reorg CLI."""
from __future__ import annotations

from enum import StrEnum


class DocReorgAction(StrEnum):
    """The `context doc-reorg <action>` verbs."""

    GUARD = "guard"
    LIST = "list"
    BACKUP = "backup"
    RESTORE = "restore"
