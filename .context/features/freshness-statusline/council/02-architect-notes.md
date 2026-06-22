# Architect notes — freshness-statusline (stage 2)

## What I changed

- Replaced the loose "Architecture in three sentences" prose with an explicit **Bounded context** section that states what the feature owns (the cache file + its two readers) and, critically, what it does *not* own (drift computation, settings mutation). Named the unifying invariant once: every path degrades to silence, never a crash.
- Split the old flat "Key decisions" into separated **Patterns** / **Dependencies surfaced** / **Decisions promoted** sections so each concern is locatable.
- Tightened cited line ranges against source: nudge block is `_STATUSLINE_NUDGE` at `context/hooks.py:201-205` (was loosely `195-…`); surfacing is `:400-411` (was `:396-411`, the comment lead-in); `_status_line_configured` `:208-222`, `statusline_nudge` `:225-241` confirmed.
- Cut filler from Open questions down to the two genuinely-open items (non-root cwd, mid-session staleness), since the rest were restatements of promoted decisions.

## Patterns named

- **Pure renderer + best-effort side-effect** — `compute_badge` (`context/drift.py:91-109`, total/no-I/O) vs. `_write_badge` (`cli/plan_update.py:39-50`) severed by the caller's `try/except: pass` (`:71-74`).
- **Single source of truth for the cache path** — `BADGE_CACHE_NAME` (`cli/plan_update.py:31`) + `badge_cache_path` imported by the reader (`cli/statusline.py:28,53`); flagged the shell wrapper (`statusline.sh:16`) as the lone intentional exception.
- **Hot path / cold path split** — `cat` wrapper (`statusline.sh:16`) vs. portable `run` (`cli/statusline.py:37-66`) reading the same path.
- **Emit-only hook** — `statusline_nudge` (`context/hooks.py:225-241`) decides, install surfaces on `HookResult.nudges` (`:400-411`).
- **Atomic write, verbatim read** — `write_text_atomic` (`cli/plan_update.py:21,50`) + no-trailing-newline echo (`cli/statusline.py:58-63`).

## Dependencies surfaced

- Consumes the already-computed `DriftReport` from `community-8`/drift via `compute_badge` (`cli/plan_update.py:50`) — projection, never recompute.
- Side effect wedged into the existing `plan-update` SessionStart boundary (`cli/plan_update.py:71-74`); badge freshness == last `plan-update` run.
- Intra-CLI-layer import of `badge_cache_path` (`cli/statusline.py:28`) to keep writer/reader in lockstep.
- Reads both settings scopes via `_status_line_configured`/`load_settings` (`context/hooks.py:208-222`) — reader only, never mutates.
- Ships `statusline.sh`/`.ps1` as `pyproject` package-data resolved through `SCRIPT_DIR` (`cli/statusline.py:34`).

## Decisions promoted

- **Badge write never fails the hook** — promoted to the lead decision (`cli/plan_update.py:71-74`, docstring `:42-47`).
- **Existing `statusLine` left untouched** — grounded the *why*: a scalar has no sentinel, so idempotent re-write is impossible → emit-only by construction (`context/hooks.py:225-241`).
- **Zero-Python hot path** justifies shipping two readers.
- **Wrapper hard-codes the relative path** — promoted from open-question to a stated, rationalised constraint (`statusline.sh:16`).
- **Per-session-only refresh** — promoted so mid-session staleness reads as intended, not a defect.
