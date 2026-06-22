# Freshness statusline — plan

confidence: INFERRED

## Where it lives

- `dummyindex/context/drift.py:91-109` — `compute_badge`, the pure badge renderer (owned by `community-8`/drift; consumed here).
- `dummyindex/cli/plan_update.py:31-74` — `BADGE_CACHE_NAME`, `badge_cache_path`, `_write_badge`, and the best-effort write at the SessionStart `plan-update` boundary.
- `dummyindex/cli/statusline.py:34-66` — `SCRIPT_DIR` and `run`, the cold-path CLI reader (`ContextSubcommand.STATUSLINE`).
- `dummyindex/skills/statusline/statusline.sh` / `statusline.ps1` — the hot-path shell wrappers shipped via `pyproject` package-data.
- `dummyindex/context/hooks.py:195-241,396-411` — `_STATUSLINE_NUDGE`, `_status_line_configured`, `statusline_nudge`, and its surfacing on `HookResult.nudges`.
- Tests: `tests/cli/test_statusline.py`, `tests/cli/test_plan_update_badge.py`, `tests/cli/test_debt_statusline_dispatch.py`, `tests/context/test_hooks.py`.

## Architecture in three sentences

A pure renderer (`compute_badge`, `context/drift.py:91-109`) maps the already-computed `DriftReport` to a one-line badge, and a best-effort writer at the `plan-update` CLI boundary (`_write_badge`, `cli/plan_update.py:39-50`) caches that badge once per session under `.context/cache/freshness-badge` via an atomic tmp+rename, wrapped in a `try/except` so it never fails the hook (`cli/plan_update.py:71-74`). On every prompt the shipped shell/PowerShell wrappers `cat` that cache directly — no Python — with `dummyindex context statusline` (`cli/statusline.py:37-66`) as the portable cold-path fallback reading the same `badge_cache_path`. Install surfaces an emit-only nudge (`statusline_nudge`, `context/hooks.py:225-241`) advising the wiring only when no `statusLine` exists in either settings scope, and writes nothing.

## Data model

- **Cached badge file** — `.context/cache/freshness-badge` (`badge_cache_path(context_dir)`, `cli/plan_update.py:34-36`). A single text file holding the verbatim badge string (`[ctx ✓]` or `[ctx: N drift]`), no trailing newline. It is gitignored scratch (`.gitignore:19`, `.context/cache/`), written atomically by `_write_badge` and read verbatim by both the wrapper and the CLI. Its name lives once in `BADGE_CACHE_NAME` (`cli/plan_update.py:31`); both reader and writer resolve through `badge_cache_path` — never a second hard-coded literal.

## Key decisions

- **The badge write never fails the hook.** `_write_badge` is a side effect fully isolated from the drift report: the `plan-update` caller wraps it in a bare `try/except: pass` (`cli/plan_update.py:71-74`), and the writer itself documents the best-effort contract (`cli/plan_update.py:42-47`). An unwritable cache dir, a read-only filesystem, or any other error degrades to "no badge" rather than crashing the SessionStart hook or perturbing stdout.
- **Atomic write, verbatim read.** `write_text_atomic` (tmp+rename) guarantees a concurrent statusline reader never sees a half-written badge; the readers echo the file's exact bytes with no trailing newline so the host renders precisely what was cached (`cli/statusline.py:58-63`, `statusline.sh:16`).
- **The existing `statusLine` is left untouched in both scopes.** The nudge is emit-only — a `statusLine` is a scalar with no sentinel, so an idempotent re-write is impossible; `statusline_nudge` therefore only *reads* both local and global settings and returns advice, writing nothing (`context/hooks.py:225-241`). If either scope already defines a `statusLine`, it stays silent.
- **Hot path carries zero Python cost.** The per-prompt render is a one-line `cat` in the shipped wrapper; the Python `run` command exists only as a portable fallback for shells that prefer calling one tool, and it reads the identical `badge_cache_path` (`cli/statusline.py:8-10,53`).
- **Single source of truth for the cache path.** The CLI reader imports `badge_cache_path` from `plan_update` rather than re-deriving the path, so writer and reader can never diverge (`cli/statusline.py:28,53`).

## Open questions

- The shell wrappers hard-code the relative path `.context/cache/freshness-badge` (`statusline.sh:16`), so the hot path assumes the host invokes `statusLine` from the project root; a non-root cwd silently yields the empty (degraded) badge. Acceptable by the degrade-to-silent contract, but undocumented for users.
- The badge refreshes only at SessionStart `plan-update`; mid-session edits do not update the badge until the next session. Intentional (drift recompute is not on the per-prompt path), but worth stating so a stale `[ctx ✓]` mid-session isn't read as a bug.
