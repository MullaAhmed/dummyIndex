# Documentation reorganizer — spec

confidence: INFERRED

## Intent

Reorganise a repo's prose docs in place, safely. The domain `context/domains/doc_reorg/` and `cli/doc_reorg.py` discover the rewritable in-repo docs. They refuse to touch docs unless git can serve as a complete undo. They snapshot docs before editing and restore honestly.

The destructive rewriting is deliberately NOT performed by this code. It runs in the session via the Edit tool, so the user confirms each file (`cli/doc_reorg.py:8-12`, `context/domains/doc_reorg/__init__.py:1-6`). This package is only the safety net: refuse-on-dirty, backup, honest restore (`context/domains/doc_reorg/safety.py:1-17`).

## User-visible behavior

CLI: `dummyindex context doc-reorg <action>` with four verbs (`context/domains/doc_reorg/enums.py:7-13`). An absent or unrecognised action prints the verb list to stderr and exits `2` (`cli/doc_reorg.py:32-39`). An unknown leftover flag also exits `2` (`cli/doc_reorg.py:46-48`).

- **guard** — the reorg pre-check. Exits `0` and prints "working tree clean — safe to reorg" when clean. Exits `1` when DIRTY, printing to stderr. It also exits `1` when git status is unknown (not a repo or git unavailable) (`cli/doc_reorg.py:51-66`).
- **list** — prints repo-relative docs a reorg would consider, one per line plus a count, or JSON array under `--json` (`cli/doc_reorg.py:68-76`). Scope is only rewritable text formats `.md/.mdx/.rst/.txt`. Binaries (png/pdf/…) are excluded (`context/domains/doc_reorg/discovery.py:18,25-35`).
- **backup** — **re-asserts the clean tree itself** (`require_clean_tree`). It exits `1` on a dirty or unknown-git tree before snapshotting anything. It snapshots every in-scope doc under `.context/_doc_backups/<utc>/` and writes a `manifest.json`. It prints the count, destination, and exact restore command, or the backup dict under `--json`. A `BackupError` also exits `1` (`cli/doc_reorg.py:77-105`).
- **restore** — `doc-reorg restore --from <backup-dir>`. A missing `--from` exits `2` (`cli/doc_reorg.py:93-96`). It reports restored docs and warns about manifest entries with no backup copy (`skipped`). It lists docs the reorg created but restore left in place (`created_since`). It points the user at `git clean -fd` for a full rollback. A `BackupError` exits `2` (`cli/doc_reorg.py:97-120`).

**Gating.** `require_clean_tree` raises `DirtyTreeError` unless the tree is clean. It treats unknown git state as "can't promise reversibility" and refuses it. `allow_dirty=True` overrides (`context/domains/doc_reorg/safety.py:57-75`). A clean tree makes `git restore` and `git clean` a complete undo.

The reorg **phase** is no longer opt-in. It runs as skill Phase 5.5 of the normal pipeline (`skills/council/60-doc-reorg.md:1-9`). `/dummyindex --reorg-docs` only runs that phase *alone*.

That is why `backup` now enforces the gate instead of trusting the operator to run `guard` first. With the phase always in the pipeline, a snapshot on a dirty tree would record modified docs as "originals". A later `restore` would faithfully reproduce that dirty state instead of the committed baseline.

`restore` is deliberately **not** gated. Restoring is the recovery path.

**Backup.** It preserves repo-relative layout, skips anything outside the repo, and writes the manifest. It appends `_doc_backups/` to `.context/.gitignore`, so the snapshot never dirties the tree the guard protects (`context/domains/doc_reorg/safety.py:78-121,185-195`).

**Confirm.** No destructive edit happens here. The Edit tool rewrites each file under user confirmation (`cli/doc_reorg.py:9-11`).

## Contracts

Public surface (re-exported from `context/domains/doc_reorg/__init__.py:9-27`):

- `discover_doc_files(root: Path) -> tuple[Path, ...]` — absolute paths of every rewritable in-repo doc, deduplicated and sorted (`discovery.py:25-35`).
- `git_is_clean(root: Path) -> Optional[bool]` — `True` when clean, `False` when dirty, `None` when git is unavailable or fails (`safety.py:36-54`).
- `require_clean_tree(root: Path, *, allow_dirty: bool = False) -> None` — raises `DirtyTreeError` on dirty or unknown state unless overridden (`safety.py:57-75`).
- `backup_docs(root: Path, files: Sequence[Path], *, timestamp: Optional[str] = None) -> DocBackup` — snapshot, manifest, and gitignore update. Raises `BackupError` on `OSError` (`safety.py:78-121`).
- `restore_backup(root: Path, backup_dir: Path) -> RestoreResult` — content-honest restore via atomic tmp+rename. Raises `BackupError` on a missing or invalid manifest, or a path-escaping entry (`safety.py:124-182`).
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
