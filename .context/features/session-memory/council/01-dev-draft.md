# Session memory & drift signal — plan

confidence: INFERRED

## Where it lives

- `dummyindex/context/domains/memory/` — the handoff store domain, split by
  concern per the folder-organization convention: `enums.py` (closed alphabet —
  `MemoryTier`, `MemoryVerb`, `AUTO_BREADCRUMB_TAG`, `TIER_HEADINGS`), `models.py`
  (frozen `Section` / `RollReport` / `BreadcrumbFacts`), `store.py`
  (create/locate), `parse.py` (markdown section split/join), `roll.py` (tier
  cascade), `emit.py` (SessionStart render), `breadcrumb.py` (PreCompact entry),
  `nudge.py` (Stop CTA), `transcript.py` (stdlib session-signal reader),
  `detect.py` (remember-plugin stand-down), `__init__.py` (public re-export
  surface) (`memory/__init__.py:1-52`).
- `dummyindex/context/domains/atomic_io.py` — shared byte-faithful atomic writer
  used by every tier/state write (`atomic_io.py:11-24`).
- `dummyindex/context/drift.py` — the SessionStart drift engine
  (`drift.py:112-205`).
- `dummyindex/context/reconcile_gate.py` — the Stop reconcile gate
  (`reconcile_gate.py:298-346`).
- `dummyindex/cli/memory.py` + `dummyindex/cli/plan_update.py` — wire-only CLI
  dispatchers (`cli/memory.py:54-134`, `cli/plan_update.py:53-79`).
- `dummyindex/context/domains/memory/__init__.py` re-exports the public surface;
  `MemoryVerb` lives in `enums.py` while `dummyindex/pipeline/enums.py` is an
  unrelated member listed by the feature map.

## Architecture in three sentences

The memory tiers are plain markdown (`now/recent/archive/core`) that the CLI
mechanically maintains — `roll_tiers` cascades dated sections downward and
`run_breadcrumb` prepends a tagged factual entry — while the prose stays the
agent's job, so the deterministic layer only ever decides *whether* to act and
renders fixed payloads. The drift report and the reconcile gate are two
consumers of the same staleness model: `compute_drift` augments per-feature
mtime rows with two commit-anchored signals (unassigned new files, awaiting
enrichment), `plan-update` renders it advisory at SessionStart, and the Stop
gate blocks once when it is gate-relevant and the session did real source work.
All three drift/memory mechanisms read the live session through one stdlib-only
parser, `read_session_signal` (`transcript.py:84-121`) — the breadcrumb and
nudge read turn/subagent/token counts, the gate additionally reads
`edited_paths` for source-drift attribution.

## Data model

On-disk tiers under `.context/session-memory/` (one H1 title + zero-or-more
`## …` sections; `MemoryTier` enum maps each to a filename)
(`memory/enums.py:7-13,31-36`):

- `now.md` — current session, newest first; holds agent handoffs and tagged
  `(auto-breadcrumb)` entries (`breadcrumb.py:26-54`).
- `recent.md` — sections dated < today rolled out of `now`; kept ≤7 days
  (`roll.py:67-77`).
- `archive.md` — sections older than `recent_keep_days` (`roll.py:71-78`).
- `core-memories.md` — durable promoted facts (agent-curated; emitted whole at
  SessionStart) (`emit.py:41-51`).

Section shape: `Section(heading, body)`; a date is the first `YYYY-MM-DD` in the
heading (`models.py:7-12`, `parse.py:19,50-53`). Roll result:
`RollReport(now_to_recent, recent_to_archive, moved_dates)` (`models.py:15-21`).

Gitignored cache/state under `.context/cache/`:
`nudge-state.json` (per-session nudge memo, pruned to 100)
(`nudge.py:33-65`), `reconcile-gate-state.json` (per-session block memo, pruned
to 100) (`reconcile_gate.py:185-226`), `freshness-badge` (statusline badge)
(`plan_update.py:31-50`).

Manifest tie-in: `compute_drift` cross-checks each source file's current sha256
against `cache/manifest.json` to suppress mtime false-positives from git ops
(`drift.py:146-160,338-369`); the commit anchor (`meta.indexed_commit`) drives
the unassigned/awaiting signals and gates whether mtime alone can block
(`reconcile_gate.py:229-238,284-295`).

## Key decisions

- **Markdown-first, mechanics-only CLI.** Tier files are human/agent-editable
  markdown; the CLI never writes prose, so the store stays legible and the
  `/dummyindex-remember` skill owns summarization (`memory/__init__.py:1-5`).
- **Stand down for `remember`.** Every emit/nudge/breadcrumb path checks
  `remember_plugin_present` and goes silent to avoid two competing injections
  (`detect.py:7-14`, `emit.py:33`, `nudge.py:113`, `breadcrumb.py:125`).
- **Hooks must never fail.** Every hook verb returns 0 regardless
  (`cli/memory.py:94,101,107`; `plan_update.py:79`); writes go through
  byte-faithful `write_text_atomic` so concurrent readers never see a partial
  file (`atomic_io.py:11-24`, data-access convention).
- **Stdlib-only transcript reader.** `transcript.py` deliberately does not import
  the `usage` domain (CONVENTIONS §2 layering) and skips cross-transcript dedup —
  a per-file sum suffices for a heuristic gate (`transcript.py:1-9`).
- **Three-oracle staleness reconciliation.** mtime is a decaying advisory; the
  commit anchor + manifest sha are authoritative. With a live anchor the gate
  ignores mtime-only drift and lets SessionStart surface it; anchor-less repos
  keep mtime-blocking as their only signal (`reconcile_gate.py:229-238,284-295`).
- **Block-once, opt-out, submodule-aware gate.** Keyed on `stop_hook_active` +
  persisted memo; `auto_council: false` opt-out per root; walks submodule
  `.context/` indexes a mono-repo root would otherwise miss
  (`reconcile_gate.py:58-76,315-329`).
- **Source-drift attribution.** The gate only traps sessions that dispatched
  file-working subagents or edited a main-thread file outside
  `.context/`/`.claude/`/`.claude-design/`, so planning/git-only sessions escape
  and inherited drift surfaces via SessionStart instead
  (`reconcile_gate.py:241-270`).

## Open questions

- `LONG_OUTPUT_TOKENS = 40_000` and `recent_keep_days = 7` are hardcoded,
  "calibrated by observation, not user-configurable in v1" — whether to expose
  them via `config.json` is open (`nudge.py:21-23`, `roll.py:47`).
- `read_session_signal` skips usage-style cross-transcript dedup by design;
  multi-transcript sessions could over- or under-count output tokens at the
  nudge/gate threshold (`transcript.py:6-9`).
- Catalogued docs (`docs/internal/plans/01-session-memory.md`,
  `docs/plans/2026-06-08-auto-handoff-nudge.md`,
  `docs/plans/2026-06-11-auto-council-drift-hook.md`) are MEDIUM confidence with
  broken refs (`SessionMemoryError`, `PreCompact`, `stop_hook_active`) — no
  `SessionMemoryError` exists in code; the typed-exception class the docs imply
  is absent, so error handling here is plain returns/`0`-exits, not a domain
  exception hierarchy. Code wins; flag the stale doc claim.
