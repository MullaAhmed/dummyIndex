# doc-reorg — architect notes (stage 2)

## What I changed

- Replaced "Architecture in three sentences" preamble's implicit boundary with an explicit **Bounded context** section stating the one invariant the whole package defends (clean tree ⇒ `git restore`+`git clean` is a complete undo) and the hard line: this code is the safety net, never the reorg.
- Promoted the buried dependency notes into a first-class **Dependencies** section: upstream (`discover_default_doc_paths`, shared CLI helpers), the deliberate internal safety→discovery cycle on the restore path, and "no downstream."
- Extracted the recurring guard idiom into a named **safety-gate pattern** ("refuse before you write") with its three concrete forms at `path:range`.
- Reframed "Key decisions" so each gate states *why* (the failure it prevents), not just what it does.
- Tightened the open questions: the guard/`require_clean_tree` divergence is now stated as logic duplication that can drift, with its `--allow-dirty` consequence spelled out. Cut filler from the architecture sentences.

## Patterns named

- **Safety-gate pattern (refuse-before-write):** reversibility gate `safety.py:57-75`; path-escape gate `safety.py:145-157`; cleanup-on-failure (tmp+replace, unlink stray `.tmp`) `safety.py:161-168`. All abort before any mutation, so a refusal leaves no partial state.
- **Gitignore-the-snapshot:** `_ensure_backup_ignored` `safety.py:120,185-195` — the net must not violate its own precondition.
- **Content-honest restore:** report `created_since`/`skipped` instead of deleting `safety.py:171-182`, `models.py:24-47`.

## Dependencies surfaced

- Upstream: `source_docs.discovery.discover_default_doc_paths` (`discovery.py:12-14,29`) seeds scope — changes there resize reorg scope silently. Shared CLI helpers `parse_path_and_root`/`parse_kv_flags`/`resolve_context_root` (`cli/doc_reorg.py:45-50`) own scope/root + `--from` parsing.
- Internal cycle (deliberate): `restore_backup` → `discover_doc_files` (`safety.py:188-190`) to compute `created_since`; same discovery defines both backup scope and "appeared-since," consistent by construction at the cost of a re-walk.
- Downstream: none in-repo; CLI is the sole caller of the domain.

## Decisions promoted

- Each safety gate now carries its rationale (the irreversible act it prevents): refuse-on-unknown-git = "no authoritative undo"; gitignore-backup = "don't dirty the certified-clean tree"; text-only scope = "never corrupt a binary"; report-don't-delete = "deleting an un-backed-up file is the one irreversible act."
- Open question sharpened to a real design concern: CLI `GUARD` duplicates clean/dirty/unknown branching inline (`cli/doc_reorg.py:51-66`) instead of routing through `require_clean_tree` (`safety.py:57-64`), leaving `--allow-dirty` library-only and two code paths that can drift.
