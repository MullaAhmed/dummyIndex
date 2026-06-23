# Multi-agent council — plan

`confidence: INFERRED`

## Bounded context

This feature is the **deterministic frontier engine** for the council documentation pipeline. The load-bearing boundary is one computation: *given the per-feature audit logs on disk, what fires next?* Everything else (which persona, which mode, which error) hangs off that. The engine runs **no LLM** — it is the pure plumbing the council skill calls between LLM dispatches.

The boundary has exactly two sides:
- **Inside (pure, in this feature):** `council_batch.py` (the frontier + dispatch-unit expansion), `council.py` (the per-feature log + completion predicate + sentinels), `dev_pick.py` (the stack-specialist author picker), `log_scan.py` (the shared last-matching scan), and the ported audit twin under `audit/`. No process owns run state; the log on disk *is* the state.
- **Outside (I/O + orchestration):** the two CLI wrappers (`cli/council_batch.py`, `cli/council.py`) own all file I/O and stdout; the council skill orchestrator owns the dispatch loop. The frontier engine never reads argv, never prints, never launches an agent.

## Where it lives

Three domain modules under `dummyindex/context/domains/`, all LLM-free:
- `council.py` — the per-feature audit log: append/read, the completion predicate, and the reset / standalone / backfill sentinels.
- `council_batch.py` — the stage frontier + dispatch-unit expansion (the "what fires next" computation).
- `dev_pick.py` — the stack-specialist author picker (which persona writes a feature's docs), plus the manifest/feature.json I/O it routes on.

CLI wrappers are the only I/O boundary: `cli/council_batch.py` (`council-batch --next`) and `cli/council.py` (`council-log` + `backfill`). Effort is resolved through the shared `config.resolve_depth` seam (`config.py:323-342`). A ported twin of the resumption log serves the on-demand audit panel at `audit/log.py` (alphabet `audit/enums.py`, errors `audit/errors.py`). Per-feature logs persist at `.context/features/<id>/council/_council-log.json`. Tests: `tests/context/domains/{test_council_batch,test_council_cli,test_dev_pick,test_log_scan}.py` + `audit/test_audit_domain.py`.

## Architecture in three sentences

`cli/council_batch.py:run` (`cli/council_batch.py:65`) parses flags, validates the depth flag, resolves effort via `resolve_depth`, loads ids from `features/INDEX.json`, and is the sole owner of file I/O + stdout; the three domain modules stay pure. `council_batch.next_batch` (`council_batch.py:249`) computes the frontier purely from the logs on disk — `earliest_incomplete_stage` (`council_batch.py:91`) finds the lowest active stage incomplete for any feature, then each ready feature (`_feature_ready_for`, `council_batch.py:149`) is expanded into role-specific `DispatchUnit`s (dev units routed by `dev_pick.pick_dev`, `dev_pick.py:255`). The dominant pattern is a **stateless, log-derived frontier recomputed from scratch on every `--next` call**: the council skill dispatches the units as parallel Task agents, each appends `started`/`complete` via `council-log`, and the loop re-runs `--next` against the now-larger log until `Batch.complete`.

## Patterns (named, with where they live)

- **Frontier / work-queue.** The dispatchable set is never stored; it is recomputed each call as "earliest incomplete active stage × features ready for it." Lives in `next_batch` (`council_batch.py:249-289`) over `earliest_incomplete_stage` (`council_batch.py:91`). The work-queue is implicit — the queue *is* the diff between the active-stage sequence and the logs.
- **Per-feature log as state (event-sourced completion).** There is no run object; `_council-log.json` is an append-only event stream and every predicate is a fold over it. Lives in `is_stage_complete` (`council.py:188`), which replays entries and derives completion rather than reading a stored flag.
- **Resume-by-recomputation.** An interrupted run resumes by re-running `--next`; the frontier converges on the same next move because it is a pure function of the log. Lives in the `next_batch` → `is_stage_complete` chain; confirmed by the HIGH-confidence orchestration doc `dummyindex/skills/council/22-parallel-dispatch.md:52-56` ("`--next` is stateless beyond the per-feature `_council-log.json`").
- **Reset-by-marker, not by-delete.** A forced re-council appends a stage-0 sentinel; predicates ignore everything before the *latest* marker, so history is preserved while completion is cleared. Lives in `_is_reset_marker` + the truncation loop in `is_stage_complete` (`council.py:197-205`), written by `append_reset_marker` (`council.py:210`).
- **First-match-wins precedence table.** The author persona is a deterministic table walk, not a heuristic score. Lives in `pick_dev` over `_RULES` (`dev_pick.py:255`), with a constant-true terminal rule guaranteeing a persona.
- **Deliberate copy over shared base (audit twin).** The audit panel needs the same atomic-append + "every started finished" shape under a different key, so the log is ported verbatim (`audit/log.py`) rather than abstracted — only the pure scan helper `log_scan.last_matching` is genuinely shared.

## Dependencies

**Upstream (this feature reads):**
- `features/INDEX.json` — the pipeline's feature universe; `run` loads every id from it (`cli/council_batch.py:136-144`). A missing INDEX is a hard usage error ("Run `dummyindex ingest` first").
- `config.resolve_depth` + `config.json` — the effort seam (`config.py:323-342`); resolves mode under a fixed precedence (see Key decisions).
- Each feature's `feature.json` file list + the repo's harvested dependency tokens — the inputs `dev_pick.pick_dev` routes on (`dev_pick.harvest_dep_tokens`, `dev_pick.py:306`; `read_feature_files`, `dev_pick.py:328`).

**Downstream (this feature feeds):**
- The **council skill orchestrator** — the sole consumer of `Batch`. It loops `council-batch --next`, dispatches **one Task per unit in one message** (parallel, barrier, repeat), inlines the persona body keyed on `role`, and each agent self-logs via `council-log` (HIGH-confidence contract: `dummyindex/skills/council/22-parallel-dispatch.md:9-23`). `subagent_type` and `framework` on each `DispatchUnit` are wire instructions *for* that orchestrator.
- The **SessionStart drift hook** (outside this feature) — consumes the per-feature `.hash` resume signal alongside the log to decide what is stale.

## Data model

`_council-log.json` (the `council.py` log schema, append-only, atomic `tmp`+`replace` writes — `council.py:159-161`):
```
{ "schema_version": 1, "feature_id": "<id>",
  "entries": [ { "timestamp", "stage", "agent", "status", "note" }, ... ] }
```

- **stage** — `CouncilStage(IntEnum)` `SPECIFY=1, PLAN=2, CRITIQUE=3, FLOW=4, TREE=5` (`council_batch.py:31`). Stage 0 is reserved for sentinel markers.
- **status** — `started | complete | failed | skipped` (`council.py:47`). A stage is *complete* iff every agent that `started` it reached `complete`/`skipped` (`is_stage_complete`, `council.py:188`).
- **sentinels** — `recouncil` + note `force-recouncil` is the stage-0 reset marker (`council.py:54-55`); `backfill` + `backfilled-from-artifacts` is a synthetic completion (`council.py:59-60`); a stage-0 `complete` note prefixed `standalone` exempts an Outcome-C feature entirely (`is_standalone_complete`, `council.py:230`). The completion predicates ignore everything *before* the latest reset marker, so a forced re-council starts a fresh run while the log stays the full audit trail (`council.py:197-205`).

**Resume state** is the log itself plus a separate content `.hash` per feature (compared by the SessionStart drift hook, outside this feature) — there is no in-memory run state. `latest_status` (`council.py:332`) reads the last entry for one `(stage, agent)` pair via the shared `log_scan.last_matching` scan, which `audit/log.py` reuses byte-identically.

**Stage machine — mode → active stages** (`active_stages`, `council_batch.py:64`): `light` = specify + flow; `standard`/`deep` add plan + critique; `tree` appended only under `--tree-enrich`. **Critic roster** (`CRITIC_ROSTER`, `council_batch.py:53`): light none, standard one (security), deep three (database, security, product). **Dispatch-unit expansion** (`_units_for_feature`, `council_batch.py:215`): specify/flow/tree → one dev unit; plan → one architect unit (`SubagentType.BACKEND`); critique → one unit per roster critic.

**Dev-pick resolution** (`pick_dev`, `dev_pick.py:255`): first-match-wins over the `_RULES` precedence table (`dev_pick.py:243`), keyed on a feature's file list + the repo's harvested dependency tokens. The constant-true fallback rule guarantees a persona; `DevPickError` is reserved for a malformed table, not a miss. Each pick carries an ordered `fallbacks` ladder for when the primary subagent isn't installed (`dev_pick.py:52`).

## Key decisions

- **Decided the frontier is stateless / recomputed because the log must survive a crash, a manual edit, or a partial parallel dispatch.** With no in-memory run state, every `--next` call converges on the same next move, so resumption needs no special handling. This is why `is_stage_complete` is a pure fold over the log (`council.py:188`) and `next_batch` takes only on-disk inputs (`council_batch.py:249`).
- **Decided "complete = every started agent finished" because partial parallel batches must re-surface only the unfinished work.** A lone `started`/`failed` keeps the stage on the frontier and the re-run targets only the unfinished agents — resumption without redoing finished work (`is_stage_complete`, `council.py:188`; `_feature_ready_for`, `council_batch.py:149`).
- **Decided forced re-council appends a marker rather than deleting history because the log is the audit trail.** `force_recouncil` (`council_batch.py:114`) appends a stage-0 `recouncil` marker via `append_reset_marker` (`council.py:210`) and resets *only* features with no incomplete active stage (`council_batch.py:130-136`), so firing it mid-run is idempotent and the loop converges.
- **Decided `--force` requires `--feature` because a forced re-council is inherently scoped.** Re-running every feature is destructive of in-flight work and almost never the intent; `run` rejects `--force` with no `--feature` as a usage error up front (`cli/council_batch.py:96-102`).
- **Decided to validate the depth flag *before* `resolve_depth`, then surface the real `ConfigError`, because the two failures have different causes and the old single catch-all conflated them.** `run` checks `depth_flag` against `CouncilMode` values first (`cli/council_batch.py:114-119`); because the flag is then known-good, a `ConfigError` from `resolve_depth` can only mean a malformed `config.json`, so the CLI prints that real error verbatim (`error: <exc>`, return `2`) instead of always reprinting the `--depth/--mode must be light|standard|deep` message (`cli/council_batch.py:131-134`). This is the recent behavioural change — the misleading catch-all is gone.
- **Decided effort resolves through one shared seam because per-command depth must resolve identically everywhere.** `resolve_depth` (`config.py:323`) gives precedence flag → `command_depths[build]` → `config.mode` → `standard`; `audit/workspace.py` delegates to the same function. The flag is a one-run override, never written to config.
- **Decided to backfill from artifacts because pre-v0.20 indexes have curated docs but empty logs, which the frontier would reschedule and clobber.** `backfill_log_from_artifacts` (`council.py:251`) synthesises `complete` entries for stages whose enriched (non-stub) artifacts exist, never touching a stage that already has any entry; the CLI warns when **more than half** the scoped features need it (`cli/council_batch.py:27`, `council.needs_artifact_backfill`, `council.py:295`).
- **Decided to honour `cap` at feature granularity because a feature's critic units must never straddle two batches.** `next_batch` breaks before adding a feature that would overshoot `cap`, never splitting a feature's units — even when the first feature alone overshoots (`council_batch.py:286-287`).
- **Decided to serialize `subagent_type` as `.value` because on Python 3.11+ `str()` on a `(str, Enum)` member returns the enum repr, not the agent name** — wrong on the wire (`council_batch.py:208-211`, `dev_pick.py:111-119`).
- **Decided to port the council log into `audit/log.py` rather than abstract a shared base because the audit panel needs the same shape but a different key** (`round`/`persona`); a deliberate copy keeps the two pipelines decoupled while the pure scan helper (`log_scan.last_matching`) is genuinely shared.

## Open questions

- Stage 5 (`TREE`) is dev-authored in `_units_for_feature` (`council_batch.py:223`) but `_ARTIFACT_STAGE_DOCS` backfill covers only stages 1–4 (`council.py:75-80`) — whether tree-enrich is ever backfillable is unclear from this module alone.
- `next_batch` breaks on the first feature that would overshoot `cap` and scans no further in that stage (`council_batch.py:286`), so fairness across features is determined by `INDEX.json` order — intentional, but ordering is the only lever.
- The `.hash` resume signal is consulted by the drift hook outside this feature; whether a forced re-council should also touch it is not decidable from this module.
