# Usage report — plan

confidence: INFERRED

## Where it lives

`dummyindex/usage/` (stdlib-only package) plus two CLI seams:
`dummyindex/__main__.py:50-98` (`_run_usage`, the `usage` top-level command)
and `dummyindex/cli/memory.py:41-51` (`_resolve_transcript`, which reuses the
transcript-location logic via `dummyindex.context.domains.memory`). The package
is split by responsibility: `transcripts.py` (I/O + parse + dedup),
`aggregate.py` (pure roll-ups), `models.py` (frozen carriers), `render.py`
(str formatting), `report.py` (orchestration), `enums.py`, `errors.py`. Tests
live under `tests/usage/` with a single synthetic corpus fixture in
`conftest.py`.

## Architecture in three sentences

A strict one-way pipeline: `transcripts.py` is the **only** module that touches
the filesystem — it locates transcripts, streams them line by line, and yields
deduplicated frozen `TurnUsage` records. `aggregate.py` takes those records and
returns frozen buckets (`Totals`, `PeriodBucket`, `SessionBucket`, `Block`,
`ChatReport`) with no I/O, and `render.py` turns buckets into display strings
with no I/O. `report.build_report` wires the three together for one report kind,
and the CLI boundary (`__main__._run_usage`) is the only place that reads the
environment, prints, and sets exit codes.

## Data model

Source records are JSONL lines under `~/.claude/projects/<slug>/<session>.jsonl`
(main thread) and `<slug>/<session>/subagents/agent-*.jsonl` (subagents). Each
file is **streamed**, never slurped — transcripts run to tens of MB
(`transcripts.py:1-17,156-181`).

Parsing keeps a line only when it is `type == "assistant"`, has a dict
`message.usage`, is not the `<synthetic>` placeholder model, and has a parseable
ISO-8601 timestamp (the trailing `Z` is normalised to `+00:00` for Python 3.10,
and all timestamps are coerced to tz-aware UTC) (`transcripts.py:83-97,114-143`).
A kept line becomes a frozen `TurnUsage` whose `session_id`/`project` come from
the **file path**, not the line — so a subagent turn is attributed to its parent
session (`transcripts.py:133-143`, `models.py:14-30`).

**Dedup** is the load-bearing transform. Claude Code rewrites the same assistant
message across multiple lines (and across resumed/forked transcripts), so the
same logical turn is counted once via a `seen` set keyed by
`message.id|requestId`, falling back to the line `uuid` when no message id is
present (so genuinely distinct unkeyed lines aren't collapsed)
(`transcripts.py:100-111,171-181`). Scope of the seen-set differs by reader:
`load_session` dedups main and subagents **independently** (their message ids
never collide) (`transcripts.py:204-227`); `iter_all_turns` uses **one global**
seen-set spanning main + subagent files across every project, so a turn
duplicated across resumed transcripts is counted once globally
(`transcripts.py:243-262`). Session **totals** are therefore deduplicated
cumulative counts, and `by_session` groups the already-deduped turns by
`session_id` (`aggregate.py:137-155`). I/O is best-effort: an unreadable file is
skipped, not fatal (`transcripts.py:146-159`).

Roll-up shapes: `Totals` holds the four token fields; `window_tokens` =
input + both cache fields (context occupancy, excludes output)
(`aggregate.py:57-59`); `grand_total` sums all four (`aggregate.py:47-54`).
`into_blocks` floors the first turn to the hour and opens a new 5-hour window
when a turn lands ≥5h after the open time **or** ≥5h after the previous turn (an
idle gap); a window is `is_active` when `now` is inside it and the last turn is
within 5h of `now` (`aggregate.py:158-202`).

## Key decisions

- **Strict layering / single I/O module.** Only `transcripts.py` touches disk;
  `aggregate`/`render` are pure; the CLI owns `print`/`sys.exit`/env. Mirrors
  the project's CLI-boundary convention and keeps `build_report` directly
  testable over a synthetic dir (`report.py:1-7`, `__main__.py:50-98`).
- **Session id is authoritative; never substitute a sibling.** A known session
  with no flushed transcript renders empty rather than borrowing the newest
  *other* session's numbers — a correctness guard against mislabelling one
  chat's usage as another's (`transcripts.py:54-80`, `report.py:57-78`,
  regression test `tests/usage/test_report.py:37-44`).
- **Infer the context limit, don't read it.** The transcript never records the
  model's window, so `infer_context_limit` picks the smallest `CONTEXT_TIERS`
  value (200K / 1M) that holds the session's peak window
  (`aggregate.py:26-28,66-71`).
- **Frozen dataclasses throughout** for the immutable-data convention
  (`models.py:14-109`); `ReportKind(str, Enum)` so a kind round-trips through
  CLI args without conversion (Python-3.10-safe — no `StrEnum`)
  (`enums.py:13-24`).
- **Best-effort reads over hard failure** for a read-mostly summary over a
  large, churning corpus (`transcripts.py:146-159`).

## Open questions

- `feature.json` lists `transcripts_parse_timestamp` and
  `transcripts_subagent_files` as `entry_points`, but in code both are
  module-private (`_parse_timestamp`, `_subagent_files`) and not in `__all__`
  (`transcripts.py:83,184`, `__init__.py:47-74`). The public entry points are
  the re-exported names; **code wins** — these two are internal.
- `infer_context_limit` caps at the largest tier (1M); a session exceeding 1M
  would report `≈>100%`. Acceptable today (no larger tier exists), but the
  window-percentage line has no clamp (`render.py:87-95`).
- `_chat` with no `session_id` falls back to the newest transcript for cwd's
  project (`transcripts.py:76-80`); the spec calls this a "best guess flagged
  by the caller," but `render_chat` emits no explicit "guessed session" marker
  — the flagging is implicit in the header only.
