# Feature: Managed doc homes

Keeps internal planning artifacts (plans, specs, design docs, audits) in managed `.context/` homes instead of the user-facing `docs/` tree. One shared, location-gated classifier backs relocation and a stray-doc write guard. A citation guard keeps authored durable docs from linking disposable proposal or audit workspaces.

## Architecture

`dummyindex/context/domains/docguard/classify.py:53` `classify_doc_path` is the single verdict for stray planning docs. Consumers:

1. **Migration** (`domains/docguard/migrate.py`, `cli/migrate_docs.py`) relocates strays under `docs/` into managed homes, preserving git history.
2. **Stray guard** (`domains/docguard/decision.py:33`, `cli/guard_doc_write.py`) denies a fresh `Write` that would create a planning doc in an unmanaged location.
3. **Citation guard** (`domains/docguard/citations.py`, `cli/guard_doc_write.py:141`) denies new text that adds a workspace path to an authored durable doc. `check --refs` (`cli/check.py:199`) and proposal closeout (`domains/proposals/closeout.py:426`) reuse the same predicate.

## Citation guard

- Pattern: `proposals` or `audits`, a separator, a slug, a separator. Slash or backslash both match. The `.context/` prefix is not required (`citations.py:12`).
- Durable set: feature `spec.md`, `plan.md`, `concerns.md`, `PROJECT.md`, `architecture/overview.md`, and `conventions/*.md` except generated `naming.md`. Nothing under `council/` (`citations.py:35-57`).
- Only added citations deny. Existing citations are compared against the file on disk, so removing one is allowed (`citations.py:30-32`).
- Tools: `Write`, `Edit`, `MultiEdit` (`guard_doc_write.py:32`). `Write` scans `content`. `Edit` and `MultiEdit` scan `new_string` only (`guard_doc_write.py:101-115`).
- `doc_guard_allow` does not exempt citations. Only the stray check reads it (`guard_doc_write.py:91`).
- The deny reason tells the agent to state the fact, not link to it (`guard_doc_write.py:166-171`).
- Input over 1 MB is allowed unscanned (`guard_doc_write.py:33,152`).

## Key components

- `context/git.py:39-77`: `is_git_repo`, `run_git`, `is_tracked`. Callers branch on `is_git_repo` first.
- `classify.py:120` `group_strays`: pure, lexical. Planning segments are location-gated (`constants.py:49`). `docs/{guide,reference,sources}` are excluded (`constants.py:57`).
- `migrate.py:64` `enumerate_strays`, `:94` `plan_moves` (validates every group before any move), `:165` `apply_moves` (dry-run unless `yes`).
- `decision.py:33` `decide` returns `deny` only for a placeable stray.
- `guard_doc_write.py:36-46` `run`: fail-open catch-all. Never `exit 2`.
- `domains/proposals/store.py` `write_proposal_json` writes only `proposal.json` at `done`. Migration uses it.

## Config and wiring

- `read_doc_guard_settings` (`domains/config.py:571`) reads `doc_guard_enabled` and `doc_guard_allow`. Tolerant. Defaults to `(True, ())`.
- `doc_guard_enabled` gates both guards (`guard_doc_write.py:64-68`).
- `context/hooks.py:245-267`: PreToolUse matcher `Write|Edit|MultiEdit` (`hooks.py:248`), built from `_SILENT_GATE`.
- Verbs: `context/enums.py:162` (`GUARD_DOC_WRITE`), `check --refs` (`cli/check.py:71`).

## Invariants

- The guard denies only the one tool call, with a reason. It never `exit 2`, so it never blocks the session.
- Unplaceable strays fail open (`decision.py:45-50`). The citation check fails open on its own errors (`guard_doc_write.py:76-78`).
- The stray guard is `Write`-only. `Edit` and `MultiEdit` cannot create a new planning doc (`guard_doc_write.py:83-86`).
- Hooks never rebuild the backbone. The guard reads and decides only.
- Migration never clobbers a non-empty file (`migrate.py:347-354`).
- When enabled, the stray guard denies superpowers `writing-plans` output under `docs/superpowers/{plans,specs}`. Segments `plans` and `specs` are not excluded (`constants.py:49`, `:57`).
- Repos can exempt those paths with `doc_guard_allow`, which the stray check reads (`guard_doc_write.py:91`).
