# Session memory & drift signal — plan

confidence: INFERRED

## Bounded context

One deterministic substrate — "decide *whether* to act, render a fixed
payload, never write prose" — serving three hook-driven consumers that share a
single transcript reader. The boundary is *mechanics vs. prose*: every tier file
is agent/human-editable markdown and the CLI only relocates, prepends, or emits
fixed strings; summarization belongs to the `/dummyindex-remember` skill, not
this domain (`memory/__init__.py:1-5`). Inside the boundary: the
`context/domains/memory/` store (roll, breadcrumb, nudge, emit) plus its two
staleness consumers, `context/drift.py` (SessionStart report) and
`context/reconcile_gate.py` (Stop gate). Outside: prose authoring, the `usage`
domain (deliberately not imported — see Decisions), and the
`/dummyindex-remember` skill.

## Where it lives

- `dummyindex/context/domains/memory/` — the handoff store, split by concern per
  the canonical-trio-then-by-concern rule (coding-practices §Layering):
  `enums.py` (`MemoryTier`, `MemoryVerb`, `AUTO_BREADCRUMB_TAG`, `TIER_HEADINGS`),
  `models.py` (frozen `Section`/`RollReport`/`BreadcrumbFacts`), `store.py`
  (create/locate), `parse.py` (section split/join), `roll.py` (tier cascade),
  `emit.py` (SessionStart render), `breadcrumb.py` (PreCompact entry), `nudge.py`
  (Stop CTA), `transcript.py` (stdlib session-signal reader), `detect.py`
  (remember-plugin stand-down), `__init__.py` (re-export = test surface)
  (`memory/__init__.py:1-52`).
- `dummyindex/context/domains/atomic_io.py` — shared byte-faithful atomic writer
  behind every tier/state write (`atomic_io.py:11-24`).
- `dummyindex/context/drift.py` — SessionStart drift engine
  (`drift.py:112-175`); `dummyindex/context/reconcile_gate.py` — Stop reconcile
  gate (`reconcile_gate.py:298-346`).
- `dummyindex/cli/memory.py` + `dummyindex/cli/plan_update.py` — wire-only
  dispatchers, <300 lines per the dispatcher-size rule (`cli/memory.py:54-134`,
  `cli/plan_update.py:53-79`).

Map noise to ignore: `dummyindex/pipeline/enums.py` is an unrelated member the
feature map sweeps in; the live `MemoryVerb` is `memory/enums.py`.

## Dependency direction (and where it bends)

The strict one-way import spine is `cli → context → analysis → pipeline`
(coding-practices §Layering). This feature sits in `context`, so:

- **Upstream (consumed):** `context/build/manifest.read_manifest` — the only
  cross-module import in `drift.py` (`drift.py:34,338-352`); `atomic_io` for all
  writes (`atomic_io.py:11-24`).
- **Downstream (consumers):** the SessionStart, PreCompact, and Stop hooks in
  `.claude/settings.json`, reached only through the two CLI dispatchers — the
  domain has no in-tree Python callers, so its blast radius is the hook wiring.
- **Deliberate non-edge — the layering cut that defines the boundary:**
  `transcript.py` re-reads the same JSONL the `usage` domain reads but refuses to
  import it, keeping `context` from depending on a sibling domain
  (`transcript.py:5-8`). This is the one place the design pays redundancy
  (no cross-transcript dedup) to preserve acyclic layering.
- **Shared-reader fan-out (one source, three sinks):** `read_session_signal`
  (`transcript.py:84-121`) is read by breadcrumb (turns/subagents), nudge
  (output-tokens/subagents), and the gate (additionally `edited_paths` for
  source-drift attribution) — a deliberate single point so the three mechanisms
  never disagree about "what happened this session."
- **No cycles.** drift ↔ reconcile_gate is one-directional: the gate imports
  `DriftReport`/`compute_drift` from drift (`reconcile_gate.py:284-295`); drift
  knows nothing of the gate.

## Architecture in three sentences

The four tiers are plain markdown (`now/recent/archive/core`) the CLI maintains
mechanically — `roll_tiers` cascades dated sections downward, `run_breadcrumb`
prepends one tagged factual entry — so the deterministic layer only ever decides
*whether* to act and emits fixed strings, never prose. The drift report and the
reconcile gate are two readers of one staleness model: `compute_drift` builds
per-feature mtime rows plus two commit-anchored signals (unplaced new files,
awaiting-enrichment), `plan-update` renders it advisory at SessionStart, and the
Stop gate blocks **once** when that model is gate-relevant *and* the session did
real source work. All three read the live session through the single stdlib-only
`read_session_signal` (`transcript.py:84-121`).

## Patterns named (at path:range)

- **Tiered-store roll (cascade-by-date).** `roll_tiers` partitions each tier on
  "first ISO date in the heading", relocating now→recent (dated < today) and
  recent→archive (older than `recent_keep_days`); undated sections pin in place;
  no-move ⇒ byte-identical files (idempotent) (`roll.py:43-106`, partition at
  `roll.py:21-36`, date key at `parse.py:50-53`).
- **Emit-only hook signal (decide → render → exit 0).** Every hook verb computes
  a decision then prints a fixed payload and returns 0 unconditionally — nudge
  CTA (`nudge.py:101-129`), SessionStart emit (`emit.py:32-60`), drift body
  (`plan_update.py:53-79`), breadcrumb (`breadcrumb.py:120-131`). Hooks must
  never fail the session.
- **Stand-down detection.** `remember_plugin_present` (presence of
  `<root>/.remember/`) short-circuits every emit/nudge/breadcrumb path to silence
  before any work (`detect.py:7-14`; gated at `emit.py:33`, `nudge.py:113`,
  `breadcrumb.py:125`).
- **Block-once via persisted memo.** Both nudge and gate key on
  `session_id` + a JSON state file pruned to 100 entries — nudge
  (`nudge.py:33-65`), gate (`reconcile_gate.py:185-226`) — so a re-entrant Stop
  hook (`stop_hook_active`) never double-fires.
- **Three-oracle staleness (mtime advisory, sha + anchor authoritative).**
  `compute_drift` cross-filters mtime rows against `cache/manifest.json` sha256
  to kill git-op false-positives (`drift.py:144-175,355-369`); the gate treats a
  live `meta.indexed_commit` anchor as authoritative and ignores mtime-only drift
  when present (`reconcile_gate.py:229-238,284-295`).
- **Source-drift attribution (escape hatch for non-coding sessions).** The gate
  traps only sessions that dispatched a file-working subagent or edited a
  main-thread path outside `.context/`/`.claude/`/`.claude-design/`
  (`_NON_SOURCE_PREFIXES`), so planning/git-only sessions pass and inherited
  drift surfaces via SessionStart instead (`reconcile_gate.py:39,241-270`).

## Data model

On-disk tiers under `.context/session-memory/` (one H1 + zero-or-more `## …`
sections; `MemoryTier` maps each to a filename) (`memory/enums.py:7-13,31-36`):

- `now.md` — current session, newest first; handoffs + tagged `(auto-breadcrumb)`
  entries (`breadcrumb.py:26-54`).
- `recent.md` — sections dated < today rolled out of `now`; kept ≤
  `recent_keep_days` (`roll.py:67-77`).
- `archive.md` — sections older than `recent_keep_days` (`roll.py:71-78`).
- `core-memories.md` — durable promoted facts, emitted whole at SessionStart
  (`emit.py:50-51`; agent-curated).

Carriers: `Section(heading, body)` (`models.py:7-12`),
`RollReport(now_to_recent, recent_to_archive, moved_dates)` (`models.py:15-21`),
`SessionSignal(output_tokens, subagent_file_count, main_turns, edited_paths=())`
(`transcript.py:28-40`),
`DriftRow(rel_path, feature_id)` / `DriftReport(rows, unassigned_new_files=(),
awaiting_enrichment=())` (`drift.py:57-88`).

Gitignored state under `.context/cache/`: `nudge-state.json`
(`nudge.py:33-65`), `reconcile-gate-state.json`
(`reconcile_gate.py:185-226`), `freshness-badge` statusline
(`plan_update.py:31-50`), and `manifest.json` (sha source for the mtime
cross-filter) (`drift.py:338-352`).

## Decisions (promoted)

1. **Markdown-first, mechanics-only CLI.** Tiers are editable markdown; the CLI
   never writes prose, so the store stays legible and `/dummyindex-remember` owns
   summarization (`memory/__init__.py:1-5`). *This is the boundary the whole
   feature is drawn around.*
2. **Stdlib-only transcript reader over the `usage` domain.** `transcript.py`
   re-implements JSONL reading rather than import `usage`, to keep the
   one-way `context → analysis` layering acyclic; the price paid is no
   cross-transcript dedup — accepted as a heuristic gate, not an accounting one
   (`transcript.py:5-8`, coding-practices §Layering).
3. **Three-oracle staleness reconciliation.** mtime is a decaying advisory; the
   manifest sha and the commit anchor are authoritative. With a live anchor the
   gate ignores mtime-only drift and lets SessionStart surface it; anchor-less
   repos keep mtime-blocking as their only signal
   (`reconcile_gate.py:229-238,284-295`).
4. **Hooks never fail; writes are atomic.** Every hook verb returns 0
   (`cli/memory.py:94,101,107`, `plan_update.py:79`); all writes go through
   `write_text_atomic` so a concurrent reader never sees a partial file
   (`atomic_io.py:11-24`, data-access convention).
5. **Stand down for `remember`.** A co-installed plugin owns injection; this
   domain goes silent rather than emit a second competing block (`detect.py:7-14`).
6. **Block-once, opt-out, submodule-aware gate.** Keyed on `stop_hook_active` +
   persisted memo; honours `auto_council: false` per root; walks submodule
   `.context/` indexes a mono-repo root would miss
   (`reconcile_gate.py:42-76,315-329`).
7. **Source-drift attribution gates the block.** Only file-editing sessions are
   trapped; planning/git-only sessions escape (Decision rationale at
   `reconcile_gate.py:241-270`).

## Open questions

- `LONG_OUTPUT_TOKENS = 40_000` (`nudge.py:23`) and `recent_keep_days = 7`
  (`roll.py:47`) are hardcoded — "calibrated by observation, not user-configurable
  in v1." Whether to surface them via `config.json` (the gate already reads it for
  `auto_council`) is open.
- The stdlib reader's missing cross-transcript dedup (Decision 2) can over- or
  under-count output tokens for a multi-transcript session right at the
  nudge/gate threshold (`transcript.py:6-8`).
- **Stale-doc flag (code wins).** Catalogued plans
  (`docs/internal/plans/01-session-memory.md`,
  `docs/plans/2026-06-08-auto-handoff-nudge.md`,
  `docs/plans/2026-06-11-auto-council-drift-hook.md`) reference a
  `SessionMemoryError` typed exception that does **not** exist in code — error
  handling here is plain returns / `0`-exits, no domain exception hierarchy.
  Treat the doc claim as stale.
