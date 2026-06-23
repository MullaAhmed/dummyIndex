"""`dummyindex context doc-reorg <action>` — gated in-place doc reorganisation.

Actions:
  guard    exit 0 if the tree is clean, 1 otherwise (the reorg's pre-check).
  list     print the in-repo docs a reorg would consider (--json for a list).
  backup   snapshot every doc under .context/_doc_backups/<utc>/ (--json).
  restore  restore a snapshot: `doc-reorg restore --from <backup-dir>`.

The destructive edits are NOT done here — they happen in the running session via
the Edit tool, so the user confirms each. This command supplies the safety net:
refuse-on-dirty, backup, and honest restore.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import parse_kv_flags, parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    from dummyindex.context.domains.doc_reorg import (
        BackupError,
        DirtyTreeError,
        DocReorgAction,
        backup_docs,
        discover_doc_files,
        require_clean_tree,
        restore_backup,
    )

    try:
        action = DocReorgAction(args[0]) if args else None
    except ValueError:
        action = None
    if action is None:
        actions = " | ".join(a.value for a in DocReorgAction)
        print(f"error: doc-reorg requires an action: {actions}", file=sys.stderr)
        return 2
    rest = args[1:]
    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]

    scope, explicit_root, leftover = parse_path_and_root(rest)
    parsed, leftover = parse_kv_flags(leftover)
    if leftover:
        print(
            f"error: unknown argument(s) for `doc-reorg`: {leftover}", file=sys.stderr
        )
        return 2
    root = resolve_context_root(scope, explicit_root=explicit_root)

    if action is DocReorgAction.GUARD:
        # Single source of truth for the dirty-tree gate: the same wrapper the
        # reorg's backup/restore path uses. Clean → 0; unknown or dirty raises
        # DirtyTreeError → 1 (the wrapper's richer message goes to stderr).
        try:
            require_clean_tree(root)
        except DirtyTreeError as exc:
            print(f"doc-reorg guard: {exc}", file=sys.stderr)
            return 1
        print("doc-reorg guard: working tree clean — safe to reorg.")
        return 0

    if action is DocReorgAction.LIST:
        files = [p.relative_to(root).as_posix() for p in discover_doc_files(root)]
        if as_json:
            print(json.dumps(files, indent=2))
        else:
            for f in files:
                print(f)
            print(f"\n{len(files)} doc(s) in scope.")
        return 0

    if action is DocReorgAction.BACKUP:
        doc_files = discover_doc_files(root)
        try:
            backup = backup_docs(root, doc_files)
        except BackupError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if as_json:
            print(json.dumps(backup.to_dict(), indent=2))
        else:
            print(
                f"doc-reorg backup: {len(backup.files)} doc(s) -> {backup.backup_dir}"
            )
            print(
                f"  restore with: dummyindex context doc-reorg restore --from {backup.backup_dir}"
            )
        return 0

    # action is DocReorgAction.RESTORE
    from_dir = parsed.get("from")
    if not from_dir:
        print("error: restore requires --from <backup-dir>", file=sys.stderr)
        return 2
    try:
        result = restore_backup(root, Path(from_dir))
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"doc-reorg restore: restored {len(result.restored)} doc(s).")
        if result.skipped:
            print(
                f"  WARNING: {len(result.skipped)} manifest entr(ies) had no backup "
                "copy and were NOT restored:"
            )
            for f in result.skipped:
                print(f"    {f}")
        if result.created_since:
            print(
                f"  {len(result.created_since)} file(s) the reorg created are left "
                "in place — drop them with `git clean -fd` for a full rollback:"
            )
            for f in result.created_since:
                print(f"    {f}")
    return 0
