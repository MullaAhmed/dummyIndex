# Usage report — plan

confidence: INFERRED

## Where it lives

`dummyindex/usage/` — a stdlib-only domain package, one CLI seam above it.
The package splits by responsibility along the pipeline: `transcripts.py`
(the only I/O module: locate + stream + parse + dedup), `aggregate.py` (pure
roll-ups), `render.py` (pure str formatting), `report.py` (orchestration),
`models.py` (frozen carriers), `enums.py`, `errors.py`. The sole caller is the
CLI boundary `dummyindex/__main__.py:50-98` (`_run_usage`, the `usage`
top-level command), which owns env reads, `print`, and exit codes. Tests live
under `tests/usage/` over one synthetic corpus fixture (`conftest.py`).

**Inbound surface is exactly one caller.** `dummyindex/cli/memory.py:41-51`
(`_resolve_transcript`) does *not* consume this package — it imports
`find_main_transcript`/`resolve_session_id` from
`dummyindex.context.domains.memory`, a sibling transcript-location
implementation in the memory domain. The two share a concept (locate a
session's transcript) but no code; `usage/` has no inbound dependency from the
memory domain.

## Architecture

A strict one-way pipeline, each stage with a narrower I/O contract than the
last:

1. `transcripts.py` is the **only** module that touches the filesystem. It
   locates a transcript, streams it line by line (never slurps — files run to
   tens of MB), and yields deduplicated frozen `TurnUsage` records.
2. `aggregate.py` takes those records and returns frozen buckets (`Totals`,
   `PeriodBucket`, `SessionBucket`, `Block`, `ChatReport`) — pure, no I/O.
3. `render.py` turns buckets into display strings — pure, no I/O.
4. `report.build_report` wires the three for one report kind;
   `__main__._run_usage` is the only place that reads env, prints, and exits.

## Data model

Source records are JSONL lines under `~/.claude/projects/<slug>/<session>.jsonl`
(main thread) and `<slug>/<session>/subagents/agent-*.jsonl` (subagents). Each
file is streamed via `_read_file`, attributing `session_id`/`project` from the
**file path**, not the line — so a subagent turn is folded into its parent
session (`transcripts.py:load_session:192-227`, `models.py` `TurnUsage`).

Parsing (`_turn_from_line`) keeps a line only when it is `type == "assistant"`,
carries a dict `message.usage`, is not the `<synthetic>` placeholder model, and
has a parseable ISO-8601 timestamp (trailing `Z` normalised to `+00:00` for
Python 3.10; all timestamps coerced to tz-aware UTC).

### Dedup is the load-bearing transform

Claude Code rewrites the same assistant message across multiple lines (and
across resumed/forked transcripts), so the same logical turn must be counted
**once**. The dedup key (`transcripts.py:_dedup_key:100-111`) is
`message.id|requestId`, falling back to the line `uuid` when no message id is
present (so genuinely distinct unkeyed lines aren't collapsed into one).

Seen-set **scope differs by reader** — this is the subtle invariant:
- `load_session` (`transcripts.py:192-227`) dedups main and subagents with
  **independent** seen-sets (a subagent's message ids never collide with the
  parent's).
- `iter_all_turns` (`transcripts.py:230-262`) uses **one global** seen-set
  spanning main + subagent files across every project, so a turn duplicated
  across resumed transcripts is counted once globally.

Downstream, session totals are deduplicated cumulative counts and `by_session`
(`aggregate.py:by_session`) groups already-deduped turns by `session_id`. I/O is
best-effort: an unreadable file is skipped via `_read_file`, not fatal.

### Roll-up shapes (`aggregate.py`)

- `Totals` holds the four token fields; `window_tokens` = input + both cache
  fields (context occupancy, excludes output); `grand_total` sums all four.
- `into_blocks` floors the first turn to the hour and opens a new 5-hour window
  when a turn lands ≥5h after the open time **or** ≥5h after the previous turn
  (an idle gap); a window `is_active` when `now` is inside it and the last turn
  is within 5h of `now`.

## Key decisions

- **Decided strict layering / single I/O module because it makes the pipeline
  directly testable and matches the project convention.** Only `transcripts.py`
  touches disk; `aggregate`/`render` are pure; `_run_usage` owns
  `print`/`sys.exit`/env. This mirrors the project's CLI-boundary rule —
  "I/O at the CLI boundary; logic in the domain package"
  (`.context/conventions/coding-practices.md:55`,
  `folder-organization.md:30`) — and lets `build_report` run over a synthetic
  dir with no env or stdout (`report.py` `build_report`, `__main__.py:50-98`).
- **Decided session id is authoritative and never substitutes a sibling because
  borrowing another chat's numbers is a silent correctness bug.** A known
  session with no flushed transcript renders empty rather than the newest
  *other* session for the same project — guarded at the source
  (`transcripts.py:find_main_transcript:54-80`, the `if session_id:` branch
  returns `None` on no match) and regression-tested
  (`tests/usage/test_report.py` `test_chat_unknown_session_renders_empty_never_a_sibling`,
  `tests/usage/test_transcripts.py` `test_find_main_transcript_set_id_missing_never_substitutes_sibling`).
- **Decided to infer the context limit rather than read it because the
  transcript never records the model's window.** `infer_context_limit`
  (`aggregate.py`) picks the smallest `CONTEXT_TIERS` value (200K / 1M) that
  holds the session's peak window.
- **Decided frozen dataclasses throughout because the repo's data-only carrier
  convention requires it** (`.context/conventions/coding-practices.md:8-11`;
  `models.py` `TurnUsage`..`ChatReport`). `ReportKind(str, Enum)` so a kind
  round-trips through CLI args without conversion — Python-3.10-safe, no
  `StrEnum` (`enums.py:ReportKind`).
- **Decided best-effort reads over hard failure because the corpus is large and
  churning** and a single bad line shouldn't sink a read-mostly summary
  (`transcripts.py:_read_file`, skips on read/parse error).

## Dependencies & boundaries

- **Imports nothing from `pipeline`, `analysis`, or `context`** — stdlib-only,
  bottom of the layering table (`dummyindex/usage/__init__.py:8-9`).
- **One inbound caller:** `__main__._run_usage` (`__main__.py:50-98`). The
  memory domain (`cli/memory.py:41-51`) is *not* a consumer — it has its own
  `find_main_transcript`/`resolve_session_id` under
  `dummyindex.context.domains.memory`. Any future unification of the two
  transcript-locators is a cross-domain change, not internal to `usage/`.
- **Env reads** (`CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_SESSION_ID`) live in
  `transcripts.default_projects_root`/`resolve_session_id`, called from the CLI
  seam — not scattered through aggregate/render.

## Open questions

- `feature.json` lists `transcripts_parse_timestamp` and
  `transcripts_subagent_files` as `entry_points`, but in code both are
  module-private (`_parse_timestamp`, `_subagent_files`) and absent from
  `__all__` (`transcripts.py`, `__init__.py`). The public entry points are the
  re-exported names; **code wins** — these two are internal.
- `infer_context_limit` caps at the largest tier (1M); a session exceeding 1M
  reports `≈>100%`. Acceptable today (no larger tier exists), but the
  window-percentage line in `render.py` has no clamp.
- `find_main_transcript` with no `session_id` falls back to the newest
  transcript for cwd's project (`transcripts.py:76-80`); the source docstring
  calls this a best guess "flagged as such by the caller," but `render_chat`
  emits no explicit "guessed session" marker — the flagging is implicit in the
  header only.
