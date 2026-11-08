"""Frozen dataclasses for the doc-reorg safety net: DocBackup + RestoreResult."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocBackup:
    """A snapshot of the repo's prose docs taken before an in-place reorg."""

    backup_dir: str  # absolute path to the snapshot folder
    files: tuple[str, ...]  # repo-relative POSIX paths captured, sorted
    created_at: str  # UTC stamp used for the folder name

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_dir": self.backup_dir,
            "files": list(self.files),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RestoreResult:
    """Outcome of restoring a backup.

    ``restored``: docs the restore overwrites or recreates from the backup.
    ``created_since``: docs present now but not backed up (the reorg created
    them), left in place for ``git clean``. ``skipped``: manifest entries whose
    backup copy is missing, surfaced so a short restore never reads as complete.
    """

    backup_dir: str
    restored: tuple[str, ...]
    created_since: tuple[str, ...]
    skipped: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_dir": self.backup_dir,
            "restored": list(self.restored),
            "created_since": list(self.created_since),
            "skipped": list(self.skipped),
        }
