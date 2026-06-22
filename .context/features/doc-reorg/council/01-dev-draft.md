# Documentation reorganizer — plan

confidence: INFERRED

## Where it lives

Domain `dummyindex/context/domains/doc_reorg/`: `enums.py` (the four verbs), `discovery.py` (which docs are in scope), `safety.py` (guard/backup/restore machinery), `models.py` (`DocBackup`, `RestoreResult`), `errors.py` (typed exception tree), and `__init__.py` (public re-exports). The CLI seam is `dummyindex/cli/doc_reorg.py`, dispatched as `context doc-reorg`. Tests: `tests/context/domains/test_doc_reorg.py`. Discovery reuses `source_docs.discovery.discover_default_doc_paths` (`discovery.py:12-14,29`).

## Architecture in three sentences

The CLI parses an action enum and scope/root, then routes to one of four pure-ish domain functions, mapping their typed errors to exit codes (`cli/doc_reorg.py:32-120`). The domain layer never edits real docs — it only discovers them, gates on a clean git tree, snapshots them with a manifest, and restores from that manifest — because the destructive rewriting is delegated to the running session's Edit tool under per-file confirmation (`__init__.py:1-6`, `safety.py:13-17`). Every guarantee is built so that, given a clean starting tree, `git restore` + `git clean` is always a complete undo.

## Data model

**`DocBackup`** (frozen, `models.py:8-21`) — the snapshot manifest: `backup_dir` (absolute path to `.context/_doc_backups/<utc>/`), `files` (sorted repo-relative POSIX paths actually captured), `created_at` (the UTC stamp used as the folder name). Serialised verbatim to `manifest.json` (`safety.py:108-116`).

**`RestoreResult`** (frozen, `models.py:24-47`) — the honest outcome of a restore: `restored` (docs overwritten/recreated), `created_since` (docs present now but absent from the backup — i.e. files the reorg created; left in place, never guessed-deleted), `skipped` (manifest entries whose backup copy was missing — a partial/tampered backup, surfaced so a short restore never reads as complete). Computed at `safety.py:171-182`.

**Layout on disk:** `<root>/.context/_doc_backups/<utc>/<repo-relative-path>` mirrors the source tree; the manifest sits at the snapshot root; `.context/.gitignore` carries `_doc_backups/`.

## Key decisions (safety gates)

- **Refuse on dirty OR unknown git state.** Unknown (non-repo / git missing) is treated like dirty — both raise `DirtyTreeError` — because without git there is no authoritative undo (`safety.py:57-75`). `allow_dirty=True` is the single deliberate escape hatch.
- **Backup is gitignored.** `_ensure_backup_ignored` appends `_doc_backups/` to `.context/.gitignore` so the snapshot can't dirty the tree the guard just certified clean (`safety.py:120,185-195`).
- **Rewritable-text-only scope.** Discovery keeps `.md/.mdx/.rst/.txt` and expands doc dirs while skipping `.git/node_modules/.venv/__pycache__/.context` and dotdirs — binaries are never reorganised in place (`discovery.py:18-22,38-48`).
- **Path-escape refusal on restore.** A manifest entry that resolves outside `backup_dir` or `root` (absolute or `../`) aborts the whole restore with `BackupError` before any write — defends against a tampered/foreign manifest (`safety.py:145-157`).
- **Atomic, content-honest restore.** Each file is written via tmp+`replace`, and a stray `.tmp` is cleaned up on `OSError` so a failed restore doesn't dirty the tree (`safety.py:161-168`).
- **No destruction in code.** Creating files is the session's job; restore reports `created_since` rather than deleting, deferring `git clean -fd` to the user (`cli/doc_reorg.py:113-119`, `models.py:26-34`).
- **Errors map to exit codes.** `2` for usage (bad/absent action, missing `--from`, unknown flag, restore `BackupError`), `1` for guard-dirty and backup `BackupError` (`cli/doc_reorg.py:36-120`).

## Open questions

- `feature.json` lists `dummyindex/context/domains/equip/wiring/safety.py` as a member file, but the doc-reorg domain imports nothing from it; the link looks like a name collision (`safety.py`), not a real dependency — flag for reconcile.
- `--allow-dirty` is honored by `require_clean_tree` but the CLI `guard` action never calls `require_clean_tree` and exposes no `--allow-dirty` flag; the override is library-only today (`cli/doc_reorg.py:51-66` vs `safety.py:63-64`). Intentional, or a missing CLI surface?
- `git_is_clean` shells out to `git status --porcelain` per call (guard, then restore re-discovers); fine at current scale, but no caching if a future flow chains many actions.
