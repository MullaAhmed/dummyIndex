# Documentation reorganizer — plan

confidence: INFERRED

## Bounded context

This feature owns exactly one thing: **the safety net around an in-place doc reorg, never the reorg itself.** The destructive rewriting is delegated to the running session's Edit tool under per-file confirmation; this code only discovers what's in scope, gates on a reversible git state, snapshots before any edit, and restores honestly (`__init__.py:1-6`, `safety.py:1-17`). The invariant the whole package defends: *given a clean starting tree, `git restore` + `git clean` is always a complete undo.*

## Where it lives

Domain `dummyindex/context/domains/doc_reorg/` — `enums.py` (the four verbs), `discovery.py` (scope), `safety.py` (guard/backup/restore machinery), `models.py` (`DocBackup`, `RestoreResult`), `errors.py` (typed exception tree), `__init__.py` (public re-exports). CLI seam `dummyindex/cli/doc_reorg.py`, dispatched as `context doc-reorg`. Tests `tests/context/domains/test_doc_reorg.py`.

## Architecture in three sentences

The CLI parses an action enum + scope/root via shared helpers, routes to one of four domain functions, and maps their typed errors to exit codes (`cli/doc_reorg.py:22-130`). The domain layer is pure of destructive writes — it discovers docs, gates on a clean tree, snapshots them with a manifest, and restores from that manifest. The only file writes it ever performs are *to the backup tree and from the backup tree* — never an arbitrary in-place edit, which stays the session's job.

## Dependencies

**Upstream (this feature depends on):**
- `source_docs.discovery.discover_default_doc_paths` — discovery seeds its scope from the source-docs catalog, then expands doc dirs and filters to rewritable text (`discovery.py:12-14,29`). A change to default-doc discovery silently widens/narrows reorg scope.
- Shared CLI helpers `parse_path_and_root`, `parse_kv_flags`, `resolve_context_root` (`cli/doc_reorg.py:45-50`) — scope/root resolution and `--from` parsing are inherited, not local; flag semantics live upstream.

**Internal cycle (deliberate):** `restore_backup` re-calls `discover_doc_files` to compute `created_since` (`safety.py:188-190`) — so safety → discovery on the restore path. The same discovery that defines backup scope defines "what counts as a doc that appeared since," which keeps the two consistent by construction. Re-running it (rather than caching) is the price.

**Downstream:** none in-repo. The CLI is the only caller of the domain; nothing imports `doc_reorg` internals.

## Data model

**`DocBackup`** (frozen, `models.py:8-21`) — the snapshot manifest: `backup_dir` (absolute path to `.context/_doc_backups/<utc>/`), `files` (sorted repo-relative POSIX paths actually captured), `created_at` (the UTC stamp used as the folder name). Serialised verbatim to `manifest.json` (`safety.py:108-116`).

**`RestoreResult`** (frozen, `models.py:24-47`) — the honest outcome of a restore: `restored` (docs overwritten/recreated), `created_since` (docs present now but absent from the backup — files the reorg created; left in place, never guessed-deleted), `skipped` (manifest entries whose backup copy was missing — a partial/tampered backup, surfaced so a short restore never reads as complete). Computed at `safety.py:171-182`.

**Layout on disk:** `<root>/.context/_doc_backups/<utc>/<repo-relative-path>` mirrors the source tree; the manifest sits at the snapshot root; `.context/.gitignore` carries `_doc_backups/`.

## The safety-gate pattern

One pattern recurs in three forms — **refuse before you write**. Each gate is a guard that aborts *before* any filesystem mutation, so a refusal never leaves partial state:

1. **Reversibility gate** (`require_clean_tree`, `safety.py:57-75`) — refuse to edit unless git can serve as undo.
2. **Path-escape gate** (`restore_backup`, `safety.py:145-157`) — refuse the *whole* restore the instant any manifest entry resolves outside `backup_dir` or `root`, before the first write.
3. **Cleanup-on-failure gate** (`safety.py:161-168`) — tmp+`replace` per file, and a stray `.tmp` is unlinked on `OSError`, so even a mid-restore failure leaves the tree clean.

## Key decisions (why each gate)

- **Refuse on dirty OR unknown git state.** Unknown (non-repo / git missing) is treated like dirty — both raise `DirtyTreeError` — because without git there is no authoritative undo, so promising reversibility would be a lie (`safety.py:57-75`). `allow_dirty=True` is the single deliberate escape hatch.
- **Backup is gitignored.** `_ensure_backup_ignored` appends `_doc_backups/` to `.context/.gitignore` so the snapshot can't dirty the very tree the guard just certified clean — otherwise the safety net would defeat its own precondition (`safety.py:120,185-195`).
- **Rewritable-text-only scope.** Discovery keeps `.md/.mdx/.rst/.txt` and expands doc dirs while skipping `.git/node_modules/.venv/__pycache__/.context` and dotdirs — an in-place text reorg must never corrupt a binary, so binaries are excluded by extension, not by guesswork (`discovery.py:18-22,38-48`).
- **Restore is content-honest, not destructive.** Creating files is the session's job; restore overwrites/recreates from the manifest but reports `created_since` rather than deleting, deferring `git clean -fd` to the user — because deleting an un-backed-up file would be the one irreversible act in an otherwise reversible flow (`cli/doc_reorg.py:113-119`, `models.py:26-34`).
- **Partial backups surface, never hide.** `skipped` exists so a restore from a tampered/short backup reports honestly instead of reading as complete (`safety.py:171-182`).
- **Errors map to exit codes.** `2` for usage (bad/absent action, missing `--from`, unknown flag, restore `BackupError`), `1` for guard-dirty and backup `BackupError` (`cli/doc_reorg.py:36-120`).

## Open questions (flag for reconcile)

- **Guard bypasses `require_clean_tree`.** The CLI `GUARD` action calls `git_is_clean` directly and re-implements the clean/dirty/unknown branching inline (`cli/doc_reorg.py:51-66`), never routing through `require_clean_tree` (`safety.py:57-64`). Consequence: `--allow-dirty` is honored only by the library, the CLI exposes no such flag, and the gate logic is duplicated in two places that can drift. Intentional (guard is read-only, so the override is meaningless there), or a missing CLI surface?
- **`feature.json` lists a foreign `safety.py`.** `dummyindex/context/domains/equip/wiring/safety.py` is a member file, but doc-reorg imports nothing from it — a name collision (`safety.py`), not a real dependency.
- **No git-status caching.** `git_is_clean` shells out to `git status --porcelain` per call (guard, then restore re-discovers); fine at current scale, but a future flow chaining many actions re-pays it each time.
