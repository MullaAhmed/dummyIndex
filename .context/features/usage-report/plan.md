# Usage report — plan

confidence: INFERRED

## Where it lives

`dummyindex/usage/` is a stdlib-only domain package. One CLI seam sits above it. `transcripts.py` is the only I/O module. It locates, streams, parses, and dedups. `aggregate.py` holds pure roll-ups. `render.py` holds pure string formatting. `report.py` orchestrates. `models.py` holds frozen carriers. `enums.py` and `errors.py` hold enums and errors.

The sole caller is the CLI boundary `dummyindex/__main__.py:50-98`. `_run_usage`, the `usage` command, owns env reads, `print`, and exit codes. Tests live in `tests/usage/`, with a `conftest.py` fixture.

**Inbound surface is exactly one caller.** `dummyindex/cli/memory.py:45-56` (`resolve_transcript`) does not consume this package. It imports `find_main_transcript`/`resolve_session_id` from `dummyindex.context.domains.memory`, a sibling transcript locator in the memory domain. They share a concept but no code. `usage/` has no inbound dependency from the memory domain.

## Architecture

A strict one-way pipeline. Each stage has a narrower I/O contract than the last.

1. `transcripts.py` is the **only** module that touches the filesystem. It locates and streams a transcript line by line. It never slurps the file, since files run to tens of MB. It yields deduplicated frozen `TurnUsage` records.
2. `aggregate.py` takes those records and returns frozen buckets: `Totals`, `PeriodBucket`, `SessionBucket`, `Block`, and `ChatReport`. It is pure, with no I/O.
3. `render.py` turns buckets into display strings. It is pure, with no I/O.
4. `report.build_report` wires the three for one report kind. `__main__._run_usage` is the only place that reads env, prints, and exits.

## Data model

Source records are JSONL lines under `~/.claude/projects/<slug>/<session>.jsonl` (main thread) and `<slug>/<session>/subagents/agent-*.jsonl` (subagents). Each file is streamed via `_read_file`. It attributes `session_id` and `project` from the **file path**, not the line. So a subagent turn folds into its parent session (`transcripts.py:load_session:192-227`, `models.py` `TurnUsage`).

Parsing (`_turn_from_line`) keeps a line only when it is `type == "assistant"`. The line must carry a dict `message.usage`. It must not be the `<synthetic>` placeholder model. It needs a parseable ISO-8601 timestamp. Trailing `Z` is normalised to `+00:00` for Python 3.10. All timestamps are coerced to tz-aware UTC.

### Dedup is the load-bearing transform

Claude Code rewrites the same message across lines and resumed or forked transcripts. The same logical turn must be counted **once**. The dedup key (`transcripts.py:_dedup_key:100-111`) is `message.id|requestId`. It falls back to the line `uuid` without a message id. Genuinely distinct unkeyed lines are never collapsed.

Seen-set **scope differs by reader**. This is the subtle invariant:
- `load_session` (`transcripts.py:192-227`) dedups main and subagents with **independent** seen-sets. A subagent's message ids never collide with the parent's.
- `iter_all_turns` (`transcripts.py:230-262`) uses **one global** seen-set. It spans every project's main and subagent files. A turn duplicated across resumed transcripts counts once globally.

Downstream, session totals are deduplicated cumulative counts. `by_session` (`aggregate.py:by_session`) groups already-deduped turns by `session_id`. I/O is best-effort. An unreadable file is skipped via `_read_file`, not fatal.

### Roll-up shapes (`aggregate.py`)

- `Totals` holds the four token fields. `window_tokens` is input plus both cache fields: context occupancy, excluding output. `grand_total` sums all four.
- `into_blocks` floors the first turn to the hour. It opens a new 5-hour window when a turn lands ≥5h after the open time. It also opens one when a turn lands ≥5h after the previous turn (an idle gap). A window `is_active` when `now` is inside it and the last turn is within 5h of `now`.

## Key decisions

- **Strict layering, one I/O module.** Chosen because it makes the pipeline directly testable. `aggregate` and `render` are pure. `_run_usage` owns `print`/`sys.exit`/env. This mirrors the project's CLI-boundary rule, "I/O at the CLI boundary; logic in the domain package" (`.context/conventions/coding-practices.md:55`, `.context/conventions/folder-organization.md:30`). It lets `build_report` run over a synthetic dir with no env or stdout (`report.py` `build_report`, `__main__.py:50-98`).
- **Session id is authoritative and never substitutes a sibling.** Borrowing another chat's numbers is a silent correctness bug. A known session with no flushed transcript renders empty. It never falls back to the newest *other* session for the same project. The guard sits at the source (`transcripts.py:find_main_transcript:54-80`). The `if session_id:` branch returns `None` on no match. Regression tests cover it: `tests/usage/test_report.py` `test_chat_unknown_session_renders_empty_never_a_sibling` and `tests/usage/test_transcripts.py` `test_find_main_transcript_set_id_missing_never_substitutes_sibling`.
- **Infer the context limit.** The transcript never records the model's window. `infer_context_limit` (`aggregate.py`) picks the smallest `CONTEXT_TIERS` value (200K / 1M) that holds the session's peak window.
- **Frozen dataclasses throughout.** The repo's data-only carrier convention requires them (`.context/conventions/coding-practices.md:8-11`; `models.py` `TurnUsage`..`ChatReport`). `ReportKind(str, Enum)` lets a kind round-trip through CLI args with no conversion. It is Python-3.10-safe, with no `StrEnum` (`enums.py:ReportKind`).
- **Best-effort reads over hard failure.** The corpus is large and churning. A single bad line should not sink a read-mostly summary (`transcripts.py:_read_file`, skips on read/parse error).

## Dependencies & boundaries

- **Imports nothing from `pipeline`, `analysis`, or `context`.** It sits at the bottom of the layering table (`dummyindex/usage/__init__.py:8-9`).
- **One inbound caller:** `__main__._run_usage` (`__main__.py:50-98`). The memory domain (`cli/memory.py:45-56`) is not a consumer. It has its own `find_main_transcript`/`resolve_session_id` under `dummyindex.context.domains.memory`. Any future unification of the two transcript locators is a cross-domain change. It is not internal to `usage/`.
- **Env reads** (`CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_SESSION_ID`) live in `transcripts.default_projects_root` and `resolve_session_id`. They are called from the CLI seam, not scattered through aggregate or render.

## Open questions

- `feature.json` lists `transcripts_parse_timestamp` and `transcripts_subagent_files` as `entry_points`. In code both are module-private (`_parse_timestamp`, `_subagent_files`). Both are absent from `__all__` (`transcripts.py`, `__init__.py`). The public entry points are the re-exports. **Code wins**: these two are internal.
- `infer_context_limit` caps at the largest tier (1M). A session above 1M reports `≈>100%`. That is acceptable today, since no larger tier exists. But the window-percentage line in `render.py` has no clamp.
- `find_main_transcript` with no `session_id` falls back to the newest transcript for cwd's project (`transcripts.py:76-80`). The source docstring calls this a best guess, "flagged as such by the caller". Yet `render_chat` emits no explicit marker. The flagging is implicit in the header only.
