# Feature: Managed doc homes

Keeps internal planning docs (plans, specs, design docs, audits) in managed `.context/` homes, not `docs/`. One location-gated classifier backs relocation and the stray guard. A citation guard blocks durable docs from linking disposable workspaces.

## Architecture

`dummyindex/context/domains/docguard/classify.py:53` `classify_doc_path` is the single stray verdict. Consumers:

1. **Migration** (`domains/docguard/migrate.py`, `cli/migrate_docs.py`) relocates strays into managed homes.
2. **Stray guard** (`domains/docguard/decision.py:33`, `cli/guard_doc_write.py`) denies a fresh `Write` that creates a stray.
3. **Citation guard** (`domains/docguard/citations.py`, `cli/guard_doc_write.py:178`) denies new workspace citations in durable docs.

`check --refs` (`cli/check.py:263`) and closeout (`domains/proposals/closeout.py:426`) reuse the predicate.

## Citation guard

- Tools: `Write`, `Edit`, `MultiEdit` (`guard_doc_write.py:35`).
- Pattern: `proposals` or `audits`, separator, slug, separator. Slash or backslash (`citations.py:12`).
- Durable set: feature `spec.md`, `plan.md`, `concerns.md`, `PROJECT.md`, `architecture/overview.md`, `conventions/*.md` except `naming.md`. Not `council/` (`citations.py:35-57`).
- Only added citations deny (set difference against disk, `citations.py:30-32`).
- `Write` scans `content`. `MultiEdit` scans `edits[].new_string` (`_new_texts`, `:138-151`).
- `Edit` scans post-edit text from `old_string`, `new_string` (`_post_edit_text`, `:169-175`, `:195`).
- `doc_guard_allow` does not exempt citations (`:97`).
- The deny asks agents to state facts, not link (`:198-209`).
- Input over 1 MB is unscanned (`:37,189`).

## Key components

- `context/git.py:39-77`: `is_git_repo`, `run_git`, `is_tracked`. Branch on `is_git_repo` first.
- `classify.py:120` `group_strays`: pure, lexical. Location gate `constants.py:49`. Excluded `docs/{guide,reference,sources}` (`constants.py:57`).
- `migrate.py:64` `enumerate_strays`, `:94` `plan_moves`, `:165` `apply_moves` (dry-run unless `yes`).
- `decision.py:33` `decide` returns `deny` only for a placeable stray.
- `guard_doc_write.py:40-50` `run`: fail-open, never `exit 2`.
- `domains/proposals/store.py` `write_proposal_json` writes `proposal.json` at `done`.

## Config and wiring

- `read_doc_guard_settings` (`domains/config.py:571`) tolerantly reads `doc_guard_enabled`, `doc_guard_allow`. Defaults `(True, ())`.
- `doc_guard_enabled` gates the citation and stray checks (`guard_doc_write.py:70-74`).
- `context/hooks.py:258-279`: PreToolUse matcher `Write|Edit|MultiEdit|Agent|Task|SendMessage` (`hooks.py:260`), built from `_SILENT_GATE`.
- Verbs: `context/enums.py:162` (`GUARD_DOC_WRITE`), `check --refs` (`cli/check.py:75-89`).

## Language hint

- `LANGUAGE_TOOLS` (`Agent`, `Task`, `SendMessage`) runs first in `_decide` (`guard_doc_write.py:58-59`). `doc_guard_enabled` does not gate it.
- `Agent`/`Task` read `prompt`; `SendMessage` reads `message`. Non-string or oversize input is silent (`_language_hint`, `:107-135`).
- `cjk_share` (`domains/docguard/language.py`) strips fenced code, inline code, URLs, paths, and filenames. Under 200 non-whitespace characters, it returns `None`.
- Otherwise it returns CJK / (CJK + Latin words). CJK is U+4E00–U+9FFF and U+3400–U+4DBF.
- `needs_warning` is true below 0.5.
- Output: one `hookSpecificOutput.additionalContext` line, no `permissionDecision`. Always returns 0.
- The text asks for concise Chinese prompts. Code, commits, docs, and reports stay English.

## Invariants

- A deny affects one tool call, with a reason. Never `exit 2`.
- Unplaceable strays fail open (`decision.py:45-50`). Citation errors fail open (`guard_doc_write.py:81-84`).
- The stray guard is `Write`-only (`guard_doc_write.py:89-92`).
- The guard reads and decides only. Hooks never rebuild the backbone.
- Migration never clobbers a non-empty file (`migrate.py:347-354`).
- Language hints only warn, never deny.
- When enabled, the stray guard denies `writing-plans` output under `docs/superpowers/{plans,specs}`. `plans` and `specs` are not excluded (`constants.py:49`, `:57`).
- `doc_guard_allow` exempts those paths (`guard_doc_write.py:97`).
