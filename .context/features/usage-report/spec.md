# Usage report — spec

confidence: INFERRED

## Intent

Aggregate Claude Code token usage out of the on-disk JSONL transcripts under
`~/.claude/projects/` and render it as plain-text reports. The transcripts are
the only source of truth; the package adds three things they lack: it counts
each logical assistant turn **once** (Claude Code rewrites the same message
across lines and across resumed/forked transcripts), it folds **subagent**
(`Task`) turns into their parent session, and it rolls the four token fields
into per-chat / per-day / per-month / per-session / per-5h-block views. The
`usage/` package is stdlib-only and sits at the bottom of the layering table —
it imports nothing from `pipeline`, `analysis`, or `context`
(`dummyindex/usage/__init__.py:8`).

## User-visible behavior

`dummyindex usage [chat|daily|session|monthly|blocks]` — kind defaults to
`chat` when omitted (`dummyindex/__main__.py:67`). `-h`/`--help` prints the
one-line usage and exits 0; an unknown kind exits 2 with the valid list; any
extra positional argument exits 2; a `UsageError` (missing projects dir, no
usage, unidentifiable session) prints `error: <msg>` to stderr and exits 1
(`dummyindex/__main__.py:68-98`).

- `chat` (the `/tokens` slash command): the single-session view. Prints the
  current context-window occupancy with an inferred percentage, a per-model
  cumulative table (deduplicated, subagents included), and a subagent note.
  The live session is identified authoritatively by `$CLAUDE_CODE_SESSION_ID`;
  a brand-new session whose transcript isn't flushed yet renders as **empty**,
  never another session's numbers (`dummyindex/usage/report.py:57-78`,
  `dummyindex/usage/transcripts.py:54-80`).
- `daily` / `monthly`: per-UTC-day / per-UTC-month table, oldest first, with a
  `TOTAL` row (`dummyindex/usage/render.py:131-168`).
- `session`: one row per chat session (subagents folded in), newest activity
  first (`dummyindex/usage/render.py:171-186`).
- `blocks`: 5-hour billing-style windows, oldest first; the live window is
  marked `ACTIVE` (`dummyindex/usage/render.py:189-203`).

The four non-chat kinds aggregate **every** project's transcripts and raise
`UsageError` when no usage is found (`dummyindex/usage/report.py:36-40`).

## Contracts

Public surface re-exported from `dummyindex/usage/__init__.py:47-74`.

Orchestration (the one entry point the CLI calls):
- `build_report(kind, *, projects_root, now, session_id, cwd) -> str`
  (`dummyindex/usage/report.py:20-54`) — renders the requested report; raises
  `UsageError` when required data is absent. Free of `print`/`sys.exit`/env
  reads so it is testable; the caller resolves `session_id`, `cwd`,
  `projects_root` (`dummyindex/__main__.py:86-93`).

Transcript I/O (`dummyindex/usage/transcripts.py` — the only I/O module):
- `default_projects_root() -> Path` (`:36-40`) — `~/.claude/projects`,
  honouring `CLAUDE_CONFIG_DIR`.
- `resolve_session_id() -> Optional[str]` (`:43-46`) — live session id from
  `$CLAUDE_CODE_SESSION_ID`, else None.
- `encode_project_slug(path) -> str` (`:49-51`) — cwd → project-dir slug
  (every non-alphanumeric char → `-`).
- `find_main_transcript(projects_root, *, session_id, cwd) -> Optional[Path]`
  (`:54-80`) — session-id-keyed lookup is authoritative; only with no
  session id does it fall back to the newest transcript for cwd's project.
- `load_session(main_transcript) -> tuple[tuple[TurnUsage,...], tuple[TurnUsage,...], int]`
  (`:192-227`) — `(main_turns, subagent_turns, subagent_file_count)`,
  deduplicated independently.
- `iter_all_turns(projects_root, *, include_subagents=True) -> Iterator[TurnUsage]`
  (`:230-263`) — every deduplicated turn across all projects; raises
  `UsageError` when the dir is absent.

Aggregation (`dummyindex/usage/aggregate.py` — pure, no I/O):
- `sum_totals(turns) -> Totals` (`:31-44`), `grand_total(totals) -> int`
  (`:47-54`), `window_tokens(turn) -> int` (`:57-59`).
- `infer_context_limit(peak_window) -> int` (`:66-71`) — smallest of
  `CONTEXT_TIERS = (200_000, 1_000_000)` that holds the peak.
- `by_model(turns) -> tuple[ModelUsage,...]` (`:74-83`, biggest spender first).
- `chat_report(session_id, main_turns, sub_turns, *, subagent_count) -> ChatReport`
  (`:86-109`).
- `by_day` / `by_month` (`:127-134`), `by_session` (`:137-155`),
  `into_blocks(turns, *, now, window_hours=5) -> tuple[Block,...]` (`:158-202`).

Rendering (`dummyindex/usage/render.py` — pure str-out):
- `render_chat(report) -> str` (`:81-128`), `render_periods(buckets, *, title,
  key_header) -> str` (`:131-151`), `render_sessions` (`:171-186`),
  `render_blocks` (`:189-203`).

Data model (`dummyindex/usage/models.py`, all `@dataclass(frozen=True)`):
`TurnUsage` (`:14-30`), `Totals` (`:33-40`), `PeriodBucket` (`:43-50`),
`SessionBucket` (`:53-63`), `Block` (`:66-75`), `ModelUsage` (`:78-84`),
`ChatReport` (`:87-109`).

Enums / errors: `ReportKind(str, Enum)` with `CHAT/DAILY/SESSION/MONTHLY/BLOCKS`
(`dummyindex/usage/enums.py:13-24`); `SYNTHETIC_MODEL = "<synthetic>"` (`:29`);
`UsageError(message, *, path=None)` (`dummyindex/usage/errors.py:10-17`).

## Examples

One happy-path trace — `dummyindex usage chat` in a live session (the
synthetic corpus in `tests/usage/conftest.py`, session `s1`):

1. `__main__.main` dispatches `cmd == "usage"` → `_run_usage([])`
   (`dummyindex/__main__.py:269-270`). No args → `kind = ReportKind.CHAT`.
2. `_run_usage` resolves `projects_root = default_projects_root()`,
   `now = datetime.now(utc)`, `session_id = resolve_session_id()` (= `"s1"`),
   `cwd = Path.cwd()`, and calls `build_report`
   (`dummyindex/__main__.py:86-93`).
3. `build_report` sees `kind is CHAT` → `_chat(...)`
   (`dummyindex/usage/report.py:33-34,57`).
4. `find_main_transcript` globs `*/s1.jsonl`, returns `proj-a/s1.jsonl`
   (session id is authoritative) (`transcripts.py:69-75`).
5. `load_session` streams `s1.jsonl`: skips the blank/non-assistant/`<synthetic>`
   lines, dedups the repeated `m2` turn via `message.id|requestId`, yielding 3
   main turns (m1, m2, m3); reads `s1/subagents/agent-1.jsonl` → 1 subagent
   turn; returns `(main(3), sub(1), 1)` (`transcripts.py:192-227`).
6. `chat_report` computes `window_now = window_tokens(m3) = 3+0+2000 = 2003`,
   `peak_window` over main turns, `infer_context_limit` → `200_000`,
   `by_model` over main+sub, `total = sum_totals(all)`, `subagents =
   sum_totals(sub)` (`aggregate.py:86-109`).
7. `render_chat` formats: `Context window now   2,003 tokens   (≈1% of 200K …)`,
   a per-model `claude-opus-4-8` row + `TOTAL`, and
   `subagents: 1 transcript(s) …` (`render.py:81-128`).
8. `_run_usage` prints the string, returns 0 (`__main__.py:97-98`). Asserted by
   `tests/usage/test_report.py:22-28`.
