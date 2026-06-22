# Feature: Context freshness statusline

confidence: INFERRED

Surfaces `.context/` drift — already computed by the SessionStart hook (`community-8`) — as a persistent shell **statusline badge** (`[ctx ✓]` / `[ctx: N drift]`). Ported from ponytail's activate-hook → flag-file → statusline pattern.

## Intent

The drift report scrolls past at session start. This feature makes staleness *persistently* visible for near-zero cost by caching a one-line badge and reading it off the per-prompt hot path, plus an opt-in nudge to wire it.

## User-visible behavior

- A `statusLine` wired to the shipped wrapper renders a persistent badge on every prompt: `[ctx ✓]` when `.context/` is fresh, `[ctx: N drift]` when N items have drifted (`compute_badge`, `context/drift.py:91-109`).
- The badge refreshes once per session: the SessionStart `plan-update` path recomputes drift and rewrites the cache (`cli/plan_update.py:66-74`); the per-prompt render only echoes that cache, never recomputing.
- `dummyindex context statusline` prints the cached badge to stdout and exits 0 — the portable cold-path equivalent of `cat`ing the file (`cli/statusline.py:37-66`).
- No badge yet, no `.context/`, or any read error ⇒ empty output, exit 0; a user's shell never sees a crash (`cli/statusline.py:49-66`, `skills/statusline/statusline.sh:16`).
- On install, when *neither* local nor global `settings.json` defines a `statusLine`, the install result surfaces a one-line nudge with the snippet to add — emit-only, written nowhere (`context/hooks.py:225-241`, `:396-403`).

## Contracts

- **`compute_badge(report: DriftReport) -> str`** (`context/drift.py:91-109`, owned by `community-8`) — pure, no I/O: `[ctx ✓]` when no drift, else `[ctx: N drift]` where N = distinct drifted files (`len({r.rel_path for r in report.rows})`) + `unassigned_new_files` + `awaiting_enrichment`.
- **Badge write at the CLI boundary** (`cli/plan_update.py`) — `badge_cache_path(context_dir: Path) -> Path` → `.context/cache/freshness-badge` (gitignored scratch; `BADGE_CACHE_NAME = "freshness-badge"`, `cli/plan_update.py:31-36`). `_write_badge(context_dir, report)` `mkdir`s the cache dir and writes `compute_badge(...)` via `write_text_atomic` (tmp+rename, concurrency-safe — `cli/plan_update.py:39-50`). The SessionStart `plan-update` path wraps the call in a `try/except` that **never** fails the hook or perturbs the drift report (best-effort, spec §5 — `cli/plan_update.py:71-74`).
- **CLI `dummyindex context statusline`** (`cli/statusline.py`, `run(argv)`, `ContextSubcommand.STATUSLINE`) — reads the cached badge via the single `badge_cache_path` source of truth and prints it verbatim with no trailing newline; a missing `.context/`, missing/malformed/unreadable cache, or any exception ⇒ empty stdout, `exit 0` (`cli/statusline.py:37-66`). Never recomputes drift.
- **Shell wrappers** `skills/statusline/statusline.sh` / `.ps1` (under `SCRIPT_DIR`, `cli/statusline.py:34`) — read the cache file **directly** (`cat .context/cache/freshness-badge 2>/dev/null || true`, `statusline.sh:16`); no Python on the per-prompt hot path. The Python command is the portable cold-path fallback.
- **`statusline_nudge(project_root: Path) -> str | None`** (`context/hooks.py:225-241`, owned by the hooks feature) — emit-only: returns `_STATUSLINE_NUDGE` only when *neither* local nor global `settings.json` defines a `statusLine` (`_status_line_configured`, `context/hooks.py:208-222`); swallows `MalformedSettingsError`/`OSError`; **writes nothing** to settings (a scalar has no sentinel, so no idempotent write is possible). Surfaced via `HookResult.nudges` at install time (`context/hooks.py:396-411`).

## Key symbols

- `run`, `SCRIPT_DIR` — `cli/statusline.py`
- `badge_cache_path`, `BADGE_CACHE_NAME`, `_write_badge` — `cli/plan_update.py`
- `compute_badge` — `context/drift.py`; `statusline_nudge`, `_status_line_configured`, `_STATUSLINE_NUDGE` — `context/hooks.py`

## Examples

- Fresh repo, statusLine renders: `[ctx ✓]`.
- Two source files edited after their feature docs plus one unassigned new file: `[ctx: 3 drift]`.
- Repo without `.context/`, or cache not yet written: wrapper and `dummyindex context statusline` both emit nothing and exit 0.
- Fresh clone, no `statusLine` in either settings scope: install output carries the nudge — ``"statusLine": {"type": "command", "command": "dummyindex context statusline"}`` — but neither settings file is modified.

## Tests

`tests/cli/test_statusline.py` (read/degrade-to-silent paths), `tests/cli/test_plan_update_badge.py` (atomic write, mkdir, best-effort isolation), `tests/cli/test_debt_statusline_dispatch.py` (CLI registration), and the statusline-nudge block in `tests/context/test_hooks.py` (both-scope check, settings bytes unchanged).
