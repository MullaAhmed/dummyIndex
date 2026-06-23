"""Safety machinery for the in-place doc reorg.

Three guarantees before any real doc is edited:

1. **Refuse on a dirty tree.** ``require_clean_tree`` raises unless the working
   tree is clean (or the caller explicitly opts into ``--allow-dirty``), so git
   is always an authoritative undo.
2. **Backup first.** ``backup_docs`` snapshots every in-repo doc under
   ``.context/_doc_backups/<utc>/`` and records a manifest.
3. **Honest restore.** ``restore_backup`` recreates the original content and
   *reports* (does not delete) files the reorg created — point the user at
   ``git clean`` for those, since the tree was clean to begin with.

The destructive edits themselves are not done here — they happen in the running
session via the Edit tool (so the user confirms each). This module only makes
those edits reversible.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from .discovery import discover_doc_files
from .errors import BackupError, DirtyTreeError
from .models import DocBackup, RestoreResult

_BACKUP_REL = Path(".context") / "_doc_backups"
_MANIFEST_NAME = "manifest.json"
_IGNORE_LINE = "_doc_backups/"


def git_is_clean(root: Path) -> bool | None:
    """True when the working tree has no uncommitted changes.

    None when git isn't available or the command fails — callers treat an
    unknown state as "can't promise reversibility".
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() == ""


def require_clean_tree(root: Path, *, allow_dirty: bool = False) -> None:
    """Raise ``DirtyTreeError`` unless the tree is clean or the caller overrides.

    A clean tree is what makes ``git restore`` / ``git clean`` a complete undo
    for the reorg, so we refuse rather than edit real docs without it.
    """
    if allow_dirty:
        return
    clean = git_is_clean(root)
    if clean is None:
        raise DirtyTreeError(
            "could not determine git status (not a git repo, or git unavailable);"
            " refusing to edit docs in place. Pass --allow-dirty to override."
        )
    if not clean:
        raise DirtyTreeError(
            "working tree has uncommitted changes; commit or stash first so the"
            " reorg is reversible (or pass --allow-dirty to override)."
        )


def backup_docs(
    root: Path,
    files: Sequence[Path],
    *,
    timestamp: str | None = None,
) -> DocBackup:
    """Copy each doc in ``files`` under ``.context/_doc_backups/<utc>/``.

    Preserves repo-relative layout, writes a manifest, and makes sure the
    backup root is gitignored so it never dirties the tree the guard protects.
    """
    root = root.resolve()
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = root / _BACKUP_REL / stamp

    try:
        captured: list[str] = []
        for raw in files:
            src = raw if raw.is_absolute() else (root / raw)
            if not src.is_file():
                continue
            try:
                rel = src.resolve().relative_to(root)
            except ValueError:
                continue  # never back up anything outside the repo
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            captured.append(rel.as_posix())

        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = DocBackup(
            backup_dir=str(backup_dir),
            files=tuple(sorted(captured)),
            created_at=stamp,
        )
        (backup_dir / _MANIFEST_NAME).write_text(
            json.dumps(backup.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise BackupError(f"could not write backup under {backup_dir}: {exc}") from exc

    _ensure_backup_ignored(root / ".context")
    return backup


def restore_backup(root: Path, backup_dir: Path) -> RestoreResult:
    """Restore docs from ``backup_dir`` and report files the reorg created.

    Content-honest: overwrites changed docs and recreates deleted ones via an
    atomic tmp+rename. Files present now but absent from the backup are *not*
    deleted — they're returned in ``created_since`` for the caller to drop with
    ``git clean``.
    """
    root = root.resolve()
    backup_dir = Path(backup_dir).resolve()
    manifest_path = backup_dir / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise BackupError(f"no {_MANIFEST_NAME} in {backup_dir}; cannot restore.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BackupError(f"{manifest_path} is not valid JSON ({exc}).") from exc

    rels = [r for r in manifest.get("files", []) if isinstance(r, str)]
    restored: list[str] = []
    skipped: list[str] = []
    for rel in rels:
        # Guard against a tampered/foreign manifest: an absolute path or a
        # `../` entry would otherwise let `root / rel` escape the repo and
        # overwrite an arbitrary file. Refuse the whole restore on any escape.
        try:
            src = (backup_dir / rel).resolve()
            dest = (root / rel).resolve()
            src.relative_to(backup_dir)
            dest.relative_to(root)
        except ValueError as exc:
            raise BackupError(
                f"manifest entry {rel!r} escapes its directory; aborting restore."
            ) from exc
        if not src.is_file():
            skipped.append(rel)  # manifest lists it but the backup copy is gone
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            shutil.copy2(src, tmp)
            tmp.replace(dest)
        except OSError as exc:
            tmp.unlink(missing_ok=True)  # don't leave a stray .tmp dirtying the tree
            raise BackupError(f"could not restore {rel}: {exc}") from exc
        restored.append(rel)

    backed_up = set(rels)
    current = {p.relative_to(root).as_posix() for p in discover_doc_files(root)}
    created_since = tuple(sorted(current - backed_up))

    return RestoreResult(
        backup_dir=str(backup_dir),
        restored=tuple(sorted(restored)),
        created_since=created_since,
        skipped=tuple(sorted(skipped)),
    )


def _ensure_backup_ignored(context_dir: Path) -> None:
    """Append ``_doc_backups/`` to ``.context/.gitignore`` if it isn't already."""
    context_dir.mkdir(parents=True, exist_ok=True)
    gi = context_dir / ".gitignore"
    if gi.exists():
        current = gi.read_text(encoding="utf-8")
        if _IGNORE_LINE in current:
            return
        gi.write_text(current.rstrip() + f"\n{_IGNORE_LINE}\n", encoding="utf-8")
        return
    gi.write_text(f"{_IGNORE_LINE}\n", encoding="utf-8")
