# Freshness statusline — plan

confidence: INFERRED

## Bounded context

This feature owns the **badge cache file and the two readers of it** — nothing more. It deliberately does *not* own drift computation (that's `community-8`/drift) nor settings mutation (it only reads). Its surface is three thin seams bolted onto existing code:

1. a **pure renderer** it consumes but does not own (`compute_badge`);
2. a **best-effort cache write** wedged into the existing `plan-update` CLI boundary;
3. a **cold-path CLI reader** plus the shipped **shell wrappers** that are the real per-prompt hot path;
4. an **emit-only install nudge** that advises wiring and writes nothing.

The unifying contract across all four: **every path degrades to silence, never to a crash.** A missing cache, an unwritable dir, a malformed settings file — each yields an empty badge or a skipped nudge, never an exception out of the SessionStart hook or the user's shell.

## Where it lives

- `dummyindex/context/drift.py:91-109` — `compute_badge`, the pure badge renderer. Owned by `community-8`/drift; this feature only consumes it.
- `dummyindex/cli/plan_update.py:31-50,71-74` — `BADGE_CACHE_NAME` (`:31`), `badge_cache_path` (`:34-36`), `_write_badge` (`:39-50`), and the best-effort `try/except` at the `plan-update` boundary (`:71-74`).
- `dummyindex/cli/statusline.py:24-66` — imports (`badge_cache_path` from `plan_update`, `:28`), `SCRIPT_DIR` (`:34`), `run` (`:37-66`); the cold-path reader behind `ContextSubcommand.STATUSLINE`.
- `dummyindex/skills/statusline/statusline.sh:16` / `statusline.ps1` — the hot-path shell wrappers shipped via `pyproject` package-data; they `cat` the cache directly.
- `dummyindex/context/hooks.py:201-241,400-411` — `_STATUSLINE_NUDGE` (`:201-205`), `_status_line_configured` (`:208-222`), `statusline_nudge` (`:225-241`), and its surfacing on `HookResult.nudges` (`:400-411`).
- Tests: `tests/cli/test_statusline.py`, `tests/cli/test_plan_update_badge.py`, `tests/cli/test_debt_statusline_dispatch.py`, and the statusline-nudge block in `tests/context/test_hooks.py`.

## Patterns

- **Pure renderer + best-effort side-effect** — `compute_badge` (`context/drift.py:91-109`) is total and I/O-free: `DriftReport → str`. The only I/O, `_write_badge` (`cli/plan_update.py:39-50`), is a *separable* side effect: the caller wraps it in a bare `try/except: pass` (`cli/plan_update.py:71-74`) so the cache write is severed from the drift report it decorates. The renderer can be unit-tested with no filesystem; the writer's failure mode is "no badge," tested in isolation (`test_badge_write_failure_is_swallowed`).
- **Single source of truth for the cache path** — the cache name is a constant once (`BADGE_CACHE_NAME`, `cli/plan_update.py:31`); both writer and the Python reader resolve through `badge_cache_path` (the reader *imports* it rather than re-deriving — `cli/statusline.py:28,53`). Writer and reader cannot diverge. The one place this single-source rule is *not* enforced is the shell wrapper, which hard-codes the relative literal (see Decisions).
- **Hot path / cold path split** — per-prompt rendering is a one-line `cat` in the shipped wrapper (`statusline.sh:16`), zero Python import cost. The `dummyindex context statusline` command (`cli/statusline.py:37-66`) is the portable cold-path equivalent for hosts that prefer invoking a single tool; it reads the *same* `badge_cache_path`.
- **Emit-only hook** — `statusline_nudge` (`context/hooks.py:225-241`) is a pure decision helper: it reads both settings scopes and returns advice or `None`, never writing. Install surfaces the return value on `HookResult.nudges` (`context/hooks.py:400-411`); the decision lives in exactly one place.
- **Atomic write, verbatim read** — `write_text_atomic` (tmp+rename, `cli/plan_update.py:21,50`) guarantees a concurrent reader never sees a half-written badge. Readers echo the file's exact bytes with no trailing newline (`cli/statusline.py:58-63`, `statusline.sh:16`) so the host renders precisely what was cached.

## Dependencies surfaced

- **Reads the drift cache from `community-8`/drift.** `_write_badge` receives the already-computed `DriftReport` and calls `compute_badge` on it (`cli/plan_update.py:50`). This feature never recomputes drift; it is a *projection* of drift onto a one-line string, refreshed only when `plan-update` runs.
- **Wedged into the `plan-update` CLI boundary.** The write fires inside the existing SessionStart `plan-update` path (`cli/plan_update.py:71-74`) — it adds a side effect to a boundary the drift feature already owns. The badge is only as fresh as the last `plan-update` invocation.
- **Imports `badge_cache_path` across the CLI layer.** `cli/statusline.py:28` depends on `cli/plan_update.py` for the path — a deliberate intra-layer coupling to preserve the single source of truth.
- **Reads `settings.json` in both scopes** via `_status_line_configured` → `load_settings`/`_settings_path_for` (`context/hooks.py:208-222`). It is a *reader* of settings; it never participates in the install's settings mutation.
- **Ships shell scripts as package-data.** `SCRIPT_DIR` (`cli/statusline.py:34`) and `pyproject` package-data are what put `statusline.sh`/`.ps1` on disk after install; the wrappers are the deliverable, the Python command the fallback.

## Data model

- **Cached badge file** — `.context/cache/freshness-badge`, resolved by `badge_cache_path(context_dir)` (`cli/plan_update.py:34-36`). A single text file holding the verbatim badge string (`[ctx ✓]` or `[ctx: N drift]`), no trailing newline. Gitignored scratch (`.gitignore:19` → `.context/cache/`), written atomically by `_write_badge`, read verbatim by both the wrapper and the CLI. Never a second hard-coded literal on the Python side — only the shell wrapper duplicates the relative path (Decisions).

## Decisions promoted

- **The badge write never fails the hook.** This is the load-bearing decision. `_write_badge` is fully isolated from the drift report; the caller's bare `try/except: pass` (`cli/plan_update.py:71-74`) means an unwritable cache dir, a read-only filesystem, or any other error degrades to "no badge" rather than crashing SessionStart or perturbing stdout. The writer documents this best-effort contract in its docstring (`cli/plan_update.py:42-47`).
- **The existing `statusLine` is left untouched in both scopes.** A `statusLine` is a *scalar with no sentinel*, so an idempotent re-write is impossible — re-running install couldn't tell "we wrote this" from "the user wrote this." `statusline_nudge` therefore only *reads* local and global settings and returns advice (`context/hooks.py:225-241`); if *either* scope already defines a truthy `statusLine` it returns `None` and stays silent. This is why the feature is emit-only by construction, not by choice.
- **Hot path carries zero Python cost.** The per-prompt render is a one-line `cat`; the Python `run` command exists only as a portable fallback and reads the identical `badge_cache_path`. The cost asymmetry justifies shipping two readers instead of one.
- **The wrapper hard-codes the relative cache path** (`statusline.sh:16`), the lone deliberate violation of single-source. Rationale: the wrapper must run with no Python and no argument plumbing, so it assumes the host invokes `statusLine` from the project root. A non-root cwd silently yields the empty (degraded) badge — acceptable under the degrade-to-silent contract, but a known constraint, not a bug.
- **The badge refreshes only at SessionStart `plan-update`.** Drift recompute is intentionally off the per-prompt path, so a mid-session edit leaves the badge stale (e.g. `[ctx ✓]` after a source edit) until the next session. Intentional; called out so a stale badge mid-session isn't mistaken for a defect.

## Open questions

- Non-root `cwd` for the wrapper silently degrades to an empty badge (`statusline.sh:16`) — acceptable, but unstated for users in any shipped doc.
- A mid-session stale badge is by design (refresh is per-session, not per-prompt); worth a user-facing note so it reads as "expected," not "broken."
