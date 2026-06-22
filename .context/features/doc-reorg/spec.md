# Documentation reorganizer — spec

confidence: INFERRED

## Intent

Reorganise a repo's prose docs in place, safely. The domain `context/domains/doc_reorg/` plus `cli/doc_reorg.py` discover the rewritable in-repo docs, refuse to touch them unless git can serve as a complete undo, snapshot them before any edit, and restore from a snapshot honestly. The destructive rewriting itself is deliberately NOT performed by this code — it happens in the running session via the Edit tool so the user confirms each file (`cli/doc_reorg.py:8-12`, `context/domains/doc_reorg/__init__.py:1-6`). This package is only the safety net: refuse-on-dirty, backup, honest restore (`context/domains/doc_reorg/safety.py:1-17`).

## User-visible behavior

CLI: `dummyindex context doc-reorg <action>` with four verbs (`context/domains/doc_reorg/enums.py:7-13`). An absent or unrecognised action prints the verb list to stderr and exits `2` (`cli/doc_reorg.py:32-39`). An unknown leftover flag also exits `2` (`cli/doc_reorg.py:46-48`).

- **guard** — the reorg pre-check. Exits `0` and prints "working tree clean — safe to reorg" when clean; exits `1` and prints to stderr when DIRTY, or when git status is unknown (not a repo / git unavailable) (`cli/doc_reorg.py:51-66`).
- **list** — prints the repo-relative docs a reorg would consider, one per line plus a count, or a JSON array under `--json` (`cli/doc_reorg.py:68-76`). Scope is only rewritable text formats `.md/.mdx/.rst/.txt`; binaries (png/pdf/…) are excluded (`context/domains/doc_reorg/discovery.py:18,25-35`).
- **backup** — snapshots every in-scope doc under `.context/_doc_backups/<utc>/`, writes a `manifest.json`, prints the count, destination, and the exact restore command (or the backup dict under `--json`). A `BackupError` exits `1` (`cli/doc_reorg.py:78-90`).
- **restore** — `doc-reorg restore --from <backup-dir>`. Missing `--from` exits `2` (`cli/doc_reorg.py:93-96`). Reports restored docs; warns about manifest entries with no backup copy (`skipped`); and lists docs the reorg created but restore left in place (`created_since`), pointing the user at `git clean -fd` for a full rollback. A `BackupError` exits `2` (`cli/doc_reorg.py:97-120`).

**Gating.** `require_clean_tree` raises `DirtyTreeError` unless the tree is clean, treating unknown git state as "can't promise reversibility" and refusing it too; `allow_dirty=True` overrides (`context/domains/doc_reorg/safety.py:57-75`). A clean tree is what makes `git restore`/`git clean` a complete undo.

**Backup.** Preserves repo-relative layout, skips anything outside the repo, writes the manifest, and appends `_doc_backups/` to `.context/.gitignore` so the snapshot never dirties the very tree the guard protects (`context/domains/doc_reorg/safety.py:78-121,185-195`).

**Confirm.** No destructive edit is in this code path; the session's Edit tool performs each rewrite under per-file user confirmation (`cli/doc_reorg.py:9-11`).

## Contracts

Public surface (re-exported from `context/domains/doc_reorg/__init__.py:9-27`):

- `discover_doc_files(root: Path) -> tuple[Path, ...]` — absolute paths of every rewritable in-repo doc, deduplicated and sorted (`discovery.py:25-35`).
- `git_is_clean(root: Path) -> Optional[bool]` — `True` when clean, `False` when dirty, `None` when git is unavailable/fails (`safety.py:36-54`).
- `require_clean_tree(root: Path, *, allow_dirty: bool = False) -> None` — raises `DirtyTreeError` on dirty/unknown unless overridden (`safety.py:57-75`).
- `backup_docs(root: Path, files: Sequence[Path], *, timestamp: Optional[str] = None) -> DocBackup` — snapshot + manifest + gitignore; raises `BackupError` on `OSError` (`safety.py:78-121`).
- `restore_backup(root: Path, backup_dir: Path) -> RestoreResult` — content-honest restore via atomic tmp+rename; raises `BackupError` on missing/invalid manifest or a path-escaping entry (`safety.py:124-182`).
- `DocReorgAction(str, Enum)` — `GUARD|LIST|BACKUP|RESTORE` (`enums.py:7-13`).
- `DocBackup` (frozen) — `backup_dir: str`, `files: tuple[str, ...]`, `created_at: str`, `to_dict()` (`models.py:8-21`).
- `RestoreResult` (frozen) — `backup_dir: str`, `restored: tuple[str, ...]`, `created_since: tuple[str, ...]`, `skipped: tuple[str, ...] = ()`, `to_dict()` (`models.py:24-47`).
- Errors: `DocReorgError` base → `DirtyTreeError`, `BackupError` (`errors.py:5-16`).

## Examples

```
# 1. Pre-check, then snapshot before letting the session rewrite docs.
$ dummyindex context doc-reorg guard
doc-reorg guard: working tree clean — safe to reorg.        # exit 0
$ dummyindex context doc-reorg backup
doc-reorg backup: 7 doc(s) -> /repo/.context/_doc_backups/20260617T0900Z
  restore with: dummyindex context doc-reorg restore --from /repo/.context/_doc_backups/20260617T0900Z

# 2. Dirty tree refuses (cli/doc_reorg.py:61-66).
$ dummyindex context doc-reorg guard
doc-reorg guard: working tree DIRTY — commit or stash first.  # exit 1 (stderr)

# 3. Restore after a reorg that also created a file.
$ dummyindex context doc-reorg restore --from /repo/.context/_doc_backups/20260617T0900Z
doc-reorg restore: restored 7 doc(s).
  1 file(s) the reorg created are left in place — drop them with `git clean -fd` for a full rollback:
    docs/new_section.md
```

Round-trip, created-file reporting, path-traversal refusal, partial-backup `skipped`, and CLI exit codes are pinned by `tests/context/domains/test_doc_reorg.py:84-191`.
