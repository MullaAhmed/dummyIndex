# Architect notes — usage-report (stage 2)

## What I changed
- Reframed "Where it lives" around the one-caller reality: `usage/` is a
  stdlib-only domain with exactly one inbound caller (`__main__._run_usage`).
- **Corrected the memory.py coupling.** The prior plan said `_resolve_transcript`
  "reuses the transcript-location logic via `dummyindex.context.domains.memory`,"
  implying `cli/memory.py` consumes `usage/`. It does not — `memory.py:44` imports
  `find_main_transcript`/`resolve_session_id` from `dummyindex.context.domains.memory`,
  a *sibling* implementation. `usage/` has zero inbound dependency from memory.
- Collapsed "Architecture in three sentences" into a numbered 4-stage pipeline
  with each stage's I/O contract stated explicitly.
- Cut filler ("Architecture in three sentences" framing, repeated dedup prose)
  and folded the dedup-scope invariant into a tight bullet pair.
- Added a "Dependencies & boundaries" section that didn't exist before.

## Patterns named
- Strict one-way pipeline / single I/O module — `transcripts.py` only disk touch;
  `aggregate.py`/`render.py` pure (`transcripts.py:192-262`, `aggregate.py`, `render.py`).
- Dedup transform with reader-dependent seen-set scope —
  `_dedup_key` (`transcripts.py:100-111`), independent scope in `load_session`
  (`:192-227`), global scope in `iter_all_turns` (`:230-262`).
- Authoritative-session-id guard — `find_main_transcript` `if session_id:` branch
  returns `None` on no match (`transcripts.py:54-80`).
- CLI-boundary I/O — `_run_usage` (`__main__.py:50-98`).
- Path-based attribution of subagent turns to parent session (`load_session:192-227`).

## Dependencies surfaced
- `usage/__init__.py:8-9` — imports nothing from `pipeline`/`analysis`/`context`.
- One inbound caller: `__main__._run_usage` (`__main__.py:50-98`).
- `cli/memory.py:41-51` is NOT a consumer — separate transcript-locator in the
  memory domain; future unification is cross-domain, not internal.
- Env reads (`CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_SESSION_ID`) confined to
  `transcripts.default_projects_root`/`resolve_session_id` at the CLI seam.

## Decisions promoted
- "decided strict layering because it makes build_report testable + matches the
  CLI-boundary convention" (cited `conventions/coding-practices.md:55`,
  `folder-organization.md:30`).
- "decided session id is authoritative because borrowing a sibling's numbers is a
  silent correctness bug" (cited regression tests by name).
- "decided to infer the context limit because the transcript never records the window."
- "decided frozen dataclasses because the repo's data-only carrier convention requires it"
  (cited `coding-practices.md:8-11`).
- "decided best-effort reads because the corpus is large and churning."
