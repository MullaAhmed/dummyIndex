# Multi-agent council — plan

`confidence: INFERRED`

## Bounded context

This feature is the **deterministic frontier engine** for the council pipeline. The key boundary is one computation: given the per-feature audit logs on disk, what fires next? Everything else (which persona, which mode, which error) hangs off that. The engine runs **no LLM**. It is the plumbing the council skill calls between LLM dispatches.

The boundary has two sides.
- **Inside (pure):** `council_batch.py` (frontier), `council.py` (log, predicate), `dev_pick.py` (author picker), `log_scan.py` (shared scan), and the audit twin under `audit/`. No process owns run state. The log on disk **is** the state.
- **Outside (I/O and orchestration):** the two CLI wrappers (`cli/council_batch.py`, `cli/council.py`) own all file I/O and stdout. The council skill orchestrator owns the dispatch loop. The frontier engine never reads argv, never prints, and never launches an agent.

## Where it lives

Three domain modules under `dummyindex/context/domains/`. All are LLM-free.
- `council.py` — per-feature audit log: append, read, completion predicate, and reset, standalone, and backfill sentinels.
- `council_batch.py` — stage frontier and dispatch-unit expansion. This answers "what fires next".
- `dev_pick.py` — stack-specialist author picker. It also holds the manifest and `feature.json` I/O it routes on.

CLI wrappers are the only I/O boundary: `cli/council_batch.py` (`council-batch --next`) and `cli/council.py` (`council-log` and `backfill`). Effort resolves through the shared seam `config.resolve_depth` (`config.py:323-342`). A ported twin of the resumption log serves the on-demand audit panel at `audit/log.py` (alphabet `audit/enums.py`, errors `audit/errors.py`). Per-feature logs persist at `.context/features/<id>/council/_council-log.json`. Tests: `tests/context/domains/{test_council_batch,test_council_cli,test_dev_pick,test_log_scan}.py` and `audit/test_audit_domain.py`.

## Architecture in three sentences

`cli/council_batch.py:run` (`cli/council_batch.py:65`) parses flags, validates the depth flag, and resolves effort with `resolve_depth`. `council_batch.next_batch` (`council_batch.py:249`) computes the frontier purely from the logs on disk, then expands ready features into `DispatchUnit`s. The dominant pattern is a stateless frontier, recomputed on every `--next` call from the log that agents append via `council-log`.

## Patterns (named, with where they live)

- **Frontier / work-queue.** The dispatchable set is never stored. It is recomputed each call: earliest incomplete active stage, paired with features ready for it. Lives in `next_batch` (`council_batch.py:249-289`) over `earliest_incomplete_stage` (`council_batch.py:91`). The work-queue is implicit. The queue **is** the diff between the active-stage sequence and the logs.
- **Per-feature log as state (event-sourced completion).** There is no run object. `_council-log.json` is an append-only event stream, and every predicate is a fold over it. Lives in `is_stage_complete` (`council.py:188`). It replays entries and derives completion. It does not read a stored flag.
- **Resume-by-recomputation.** An interrupted run resumes by re-running `--next`. The frontier converges on the same next move, because it is a pure function of the log. Lives in the chain from `next_batch` to `is_stage_complete`. Confirmed by the HIGH-confidence orchestration doc `dummyindex/skills/council/22-parallel-dispatch.md:52-56` ("`--next` is stateless beyond the per-feature `_council-log.json`").
- **Reset-by-marker, not by-delete.** A forced re-council appends a stage-0 sentinel. Predicates ignore everything before the **latest** marker. History is kept, but completion is cleared. Lives in `_is_reset_marker` and the truncation loop in `is_stage_complete` (`council.py:197-205`). `append_reset_marker` writes it (`council.py:210`).
- **First-match-wins precedence table.** The author persona is a deterministic table walk, not a heuristic score. Lives in `pick_dev` over `_RULES` (`dev_pick.py:255`). A constant-true terminal rule guarantees a persona.
- **Deliberate copy over shared base (audit twin).** The audit panel needs the same atomic-append and "every started finished" shape, but under a different key. So the log is ported verbatim (`audit/log.py`) rather than abstracted. Only the pure scan helper `log_scan.last_matching` is genuinely shared.

## Dependencies

**Upstream (this feature reads):**
- `features/INDEX.json` — the pipeline's feature universe. `run` loads every id from it (`cli/council_batch.py:136-144`). A missing INDEX is a hard usage error ("Run `dummyindex ingest` first").
- `config.resolve_depth` and `config.json` — the effort seam (`config.py:323-342`). It resolves mode under a fixed precedence (see Key decisions).
- Each feature's `feature.json` file list and the repo's harvested dependency tokens. These are the inputs `dev_pick.pick_dev` routes on (`dev_pick.harvest_dep_tokens`, `dev_pick.py:306`; `read_feature_files`, `dev_pick.py:328`).

**Downstream (this feature feeds):**
- The **council skill orchestrator**, the sole consumer of `Batch`. It loops `council-batch --next` until `Batch.complete`. It dispatches **one Task per unit in one message**: parallel, barrier, repeat. It inlines the persona body keyed on `role`. Each agent self-logs via `council-log` (HIGH-confidence contract: `dummyindex/skills/council/22-parallel-dispatch.md:9-23`). `subagent_type` and `framework` on each `DispatchUnit` are wire instructions for that orchestrator.
- The **SessionStart plan-update hook**, outside this feature. It reads the per-feature `.hash` resume signal alongside the log. It decides what is stale.

## Data model

`_council-log.json` (`council.py` log schema, append-only, atomic `tmp`+`replace` writes — `council.py:159-161`):
```
{ "schema_version": 1, "feature_id": "<id>",
  "entries": [ { "timestamp", "stage", "agent", "status", "note" }, ... ] }
```

- **stage** — `CouncilStage(IntEnum)` `SPECIFY=1, PLAN=2, CRITIQUE=3, FLOW=4, TREE=5` (`council_batch.py:31`). Stage 0 is reserved for sentinel markers.
- **status** — `started | complete | failed | skipped` (`council.py:47`). A stage is *complete* only if every agent that `started` it reached `complete` or `skipped` (`is_stage_complete`, `council.py:188`).
- **sentinels** — `recouncil` with note `force-recouncil` is the stage-0 reset marker (`council.py:54-55`). `backfill` with note `backfilled-from-artifacts` is a synthetic completion (`council.py:59-60`). A stage-0 `complete` note prefixed `standalone` exempts an Outcome-C feature entirely (`is_standalone_complete`, `council.py:230`). Completion predicates ignore everything before the latest reset marker, so a forced re-council starts a fresh run. The log stays the full audit trail (`council.py:197-205`).

**Resume state** is the log itself, plus a separate content `.hash` per feature. The SessionStart plan-update hook compares that hash, outside this feature. There is no in-memory run state. `latest_status` (`council.py:332`) reads the last entry for one `(stage, agent)` pair. It uses the shared `log_scan.last_matching` scan, which `audit/log.py` reuses byte-identically.

**Stage machine, mode to active stages** (`active_stages`, `council_batch.py:64`): `light` = specify + flow. `standard` and `deep` add plan + critique. `tree` is appended whenever `tree_enrich` is set. `cli/council_batch.py:104-108` sets it **on by default**. `--no-tree-enrich` opts out, and `--tree-enrich` is an accepted no-op. So stage 5 runs in every depth, `light` included. **Critic roster** (`CRITIC_ROSTER`, `council_batch.py:53`): light none, standard one (security), deep three (database, security, product). **Dispatch-unit expansion** (`_units_for_feature`, `council_batch.py:215`): specify, flow, and tree give one dev unit. Plan gives one architect unit (`SubagentType.BACKEND`). Critique gives one unit per roster critic.

**Dev-pick resolution** (`pick_dev`, `dev_pick.py:255`): first-match-wins over the `_RULES` precedence table (`dev_pick.py:243`). It keys on the file list and the repo's harvested dependency tokens. The constant-true fallback rule guarantees a persona. `DevPickError` is reserved for a malformed table, not a miss. Each pick carries an ordered `fallbacks` ladder for when the primary subagent is not installed (`dev_pick.py:52`).

## Key decisions

- **Decided the frontier is stateless because the log must survive a crash, manual edit, or partial dispatch.** With no in-memory run state, every `--next` call recomputes the same next move. So resumption needs no special handling. `is_stage_complete` is a pure fold over the log (`council.py:188`). `next_batch` takes only on-disk inputs (`council_batch.py:249`).
- **Decided "complete = every started agent finished" because partial batches must re-surface only unfinished work.** A lone `started` or `failed` keeps the stage on the frontier. The re-run targets only the unfinished agents. That gives resumption without redoing finished work (`is_stage_complete`, `council.py:188`; `_feature_ready_for`, `council_batch.py:149`).
- **Decided forced re-council appends a marker because the log is the audit trail.** `force_recouncil` (`council_batch.py:114`) appends a stage-0 `recouncil` marker via `append_reset_marker` (`council.py:210`). It resets **only** features with no incomplete active stage (`council_batch.py:130-136`). So firing it mid-run is idempotent, and the loop converges.
- **Decided `--force` requires `--feature` because a forced re-council is inherently scoped.** Re-running every feature is destructive to in-flight work. It is almost never the intent. `run` rejects `--force` with no `--feature` up front, as a usage error (`cli/council_batch.py:96-102`).
- **Decided to validate the depth flag before `resolve_depth`, then surface the real `ConfigError`, because the two failures have different causes.** The old single catch-all conflated them. `run` checks `depth_flag` against `CouncilMode` values first (`cli/council_batch.py:114-119`). The flag is now known good. So a `ConfigError` from `resolve_depth` can only mean a malformed `config.json`. The CLI prints that error verbatim: `error: <exc>`, return `2` (`cli/council_batch.py:131-134`). It no longer reprints the `--depth/--mode must be light|standard|deep` message. This is the recent behavioural change, and the misleading catch-all is gone.
- **Decided effort resolves through one shared seam because per-command depth must resolve identically everywhere.** `resolve_depth` (`config.py:323`) gives precedence: flag, then `command_depths[build]`, then `config.mode`, then `standard`. `audit/workspace.py` delegates to the same function. The flag is a one-run override, never written to config.
- **Decided to backfill from artifacts because pre-v0.20 indexes have curated docs but empty logs.** The frontier would reschedule and clobber them. `backfill_log_from_artifacts` (`council.py:251`) synthesises `complete` entries for stages whose enriched, non-stub artifacts exist. It never touches a stage that already has any entry. The CLI warns when **more than half** the scoped features need it (`cli/council_batch.py:27`, `council.needs_artifact_backfill`, `council.py:295`).
- **Decided to honour `cap` at feature granularity because a feature's critic units must never straddle two batches.** `next_batch` breaks before adding a feature that would overshoot `cap`. It never splits a feature's units, even when the first feature alone overshoots (`council_batch.py:286-287`).
- **Decided to serialize `subagent_type` as `.value`.** On Python 3.11+, `str()` on a `(str, Enum)` member returns the enum repr, not the agent name. That is wrong on the wire (`council_batch.py:208-211`, `dev_pick.py:111-119`).
- **Decided to port the council log into `audit/log.py` rather than abstract a shared base.** The audit panel needs the same shape but a different key (`round`/`persona`). A deliberate copy keeps the two pipelines decoupled. Only the pure scan helper (`log_scan.last_matching`) is genuinely shared.

## Open questions

- Stage 5 (`TREE`) is dev-authored in `_units_for_feature` (`council_batch.py:223`). But `_ARTIFACT_STAGE_DOCS` backfill covers only stages 1–4 (`council.py:75-80`). Whether tree-enrich is ever backfillable is unclear from this module alone.
- `next_batch` breaks on the first feature that would overshoot `cap`. It scans no further in that stage (`council_batch.py:286`). So fairness across features follows `INDEX.json` order. This is intentional, but ordering is the only lever.
- The `.hash` resume signal is consulted by the drift hook outside this feature. Whether a forced re-council should also touch it is not decidable from this module.
