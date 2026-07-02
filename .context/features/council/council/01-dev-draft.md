# Multi-agent council — plan

`confidence: INFERRED`

## Where it lives

Three domain modules under `dummyindex/context/domains/`, all LLM-free:
- `council.py` — the per-feature audit log: append/read, the completion predicate, and the reset / standalone / backfill sentinels.
- `council_batch.py` — the stage frontier + dispatch-unit expansion (the "what fires next" computation).
- `dev_pick.py` — the stack-specialist author picker (which persona writes a feature's docs), plus the manifest/feature.json I/O it routes on.

CLI wrappers are the only I/O boundary: `cli/council_batch.py` (`council-batch --next`) and `cli/council.py` (`council-log` + `backfill`). Effort is resolved through the shared `config.resolve_depth` seam (`config.py:323-342`). A ported twin of the resumption log serves the on-demand audit panel at `audit/log.py` (alphabet `audit/enums.py`, errors `audit/errors.py`). Per-feature logs persist at `.context/features/<id>/council/_council-log.json`. Tests: `tests/context/domains/{test_council_batch,test_council_cli,test_dev_pick,test_log_scan}.py` + `audit/test_audit_domain.py`.

## Architecture in three sentences

`cli/council_batch.py:run` (`cli/council_batch.py:65`) parses flags, validates the depth flag, resolves effort via `resolve_depth`, loads ids from `features/INDEX.json`, and is the sole owner of file I/O + stdout; the three domain modules stay pure. `council_batch.next_batch` (`council_batch.py:249`) computes the frontier purely from the logs on disk — `earliest_incomplete_stage` finds the lowest active stage incomplete for any feature, then each ready feature is expanded into role-specific `DispatchUnit`s (dev units routed by `dev_pick.pick_dev`). The dominant pattern is a **stateless, log-derived frontier recomputed from scratch on every `--next` call**: the council skill dispatches the units as parallel Task agents, each appends `started`/`complete` via `council-log`, and the loop re-runs `--next` against the now-larger log until `Batch.complete`.

## Data model

`_council-log.json` (the `council.py` log schema, append-only, atomic `tmp`+`replace` writes — `council.py:159-161`):
```
{ "schema_version": 1, "feature_id": "<id>",
  "entries": [ { "timestamp", "stage", "agent", "status", "note" }, ... ] }
```

- **stage** — `CouncilStage(IntEnum)` `SPECIFY=1, PLAN=2, CRITIQUE=3, FLOW=4, TREE=5` (`council_batch.py:31`). Stage 0 is reserved for sentinel markers.
- **status** — `started | complete | failed | skipped` (`council.py:47`). A stage is *complete* iff every agent that `started` it reached `complete`/`skipped` (`is_stage_complete`, `council.py:188`).
- **sentinels** — `recouncil` + note `force-recouncil` is the stage-0 reset marker (`council.py:54-55`); `backfill` + `backfilled-from-artifacts` is a synthetic completion (`council.py:59-60`); a stage-0 `complete` note prefixed `standalone` exempts an Outcome-C feature entirely (`is_standalone_complete`, `council.py:232`). The completion predicates ignore everything *before* the latest reset marker, so a forced re-council starts a fresh run while the log stays the full audit trail (`council.py:195-205`).

**Resume state** is the log itself plus a separate content `.hash` per feature (compared by the SessionStart plan-update hook, outside this feature) — there is no in-memory run state. `latest_status` (`council.py:334`) reads the last entry for one `(stage, agent)` pair via the shared `log_scan.last_matching` scan, which `audit/log.py` reuses byte-identically.

**Stage machine — mode -> active stages** (`active_stages`, `council_batch.py:64`): `light` = specify + flow; `standard`/`deep` add plan + critique; `tree` appended only under `--tree-enrich`. **Critic roster** (`CRITIC_ROSTER`, `council_batch.py:53`): light none, standard one (security), deep three (database, security, product). **Dispatch-unit expansion** (`_units_for_feature`, `council_batch.py:215`): specify/flow/tree -> one dev unit; plan -> one architect unit (`SubagentType.BACKEND`); critique -> one unit per roster critic.

**Dev-pick resolution** (`pick_dev`, `dev_pick.py:255`): first-match-wins over the `_RULES` precedence table (`dev_pick.py:243`), keyed on a feature's file list + the repo's harvested dependency tokens. The constant-true fallback rule guarantees a persona; `DevPickError` is reserved for a malformed table, not a miss. Each pick carries an ordered `fallbacks` ladder for when the primary subagent isn't installed (`dev_pick.py:52`).

## Key decisions

- **Stateless, log-derived frontier.** The logs must survive a crash, a manual edit, or a partial parallel dispatch — with no in-memory run state, every `--next` call converges on the same next move. This is why `is_stage_complete` is a pure function of the log (`council.py:188`).
- **"Complete = every started agent finished."** A lone `started`/`failed` re-surfaces the stage and the re-run targets only the unfinished agents — resumption without redoing finished work (`council.py:188`, `council_batch.py:149`).
- **Forced re-council appends a marker rather than deleting history**, because the log is the audit trail. `force_recouncil` (`council_batch.py:114`) appends a stage-0 `recouncil` marker and resets only features with no incomplete stage, so firing it mid-run is idempotent and the loop converges.
- **Validate the depth flag up front, then surface the real `ConfigError`.** `run` checks `depth_flag` against `CouncilMode` values before calling `resolve_depth` (`cli/council_batch.py:113-119`); because the flag is then known-good, a `ConfigError` from `resolve_depth` can only be a malformed `config.json`, so the CLI prints that real error verbatim instead of always reprinting the `--depth/--mode must be light|standard|deep` message (`cli/council_batch.py:131-134`). This is the recent behavioural change — the misleading catch-all error is gone.
- **Effort resolved through one shared seam.** `resolve_depth` (`config.py:323`) gives precedence flag -> `command_depths[build]` -> `config.mode` -> `standard`; `audit/workspace.py` delegates to the same function, so per-command depth resolves one way everywhere. The flag is a one-run override, never written to config.
- **Backfill from artifacts** because pre-v0.20 indexes have curated docs but empty logs, and the frontier would reschedule and clobber them. `backfill_log_from_artifacts` (`council.py:253`) synthesises `complete` entries for stages whose enriched (non-stub) artifacts exist, never touching a stage that already has any entry; the CLI warns when most features need it (`cli/council_batch.py:27`).
- **Honour `cap` at feature granularity** so a feature's critic units never straddle two batches — even when the first feature overshoots `cap` (`council_batch.py:286`).
- **Serialize `subagent_type` as `.value`** because on Python 3.11+ `str()` on a `(str, Enum)` member returns the `SubagentType.FRONTEND` repr, not the agent name — wrong on the wire (`council_batch.py:208-211`, `dev_pick.py:111-119`).
- **Port the council log into `audit/log.py`** rather than abstract a shared base, because the audit panel needs the same atomic-append + "every started finished" shape but a different key (`round`/`persona`); a deliberate copy keeps the two pipelines decoupled while the pure scan helper (`log_scan.last_matching`) is genuinely shared.

## Open questions

- Stage 5 (`TREE`) is dev-authored in `_units_for_feature` (`council_batch.py:223`) but `_ARTIFACT_STAGE_DOCS` backfill covers only stages 1–4 (`council.py:75-80`) — whether tree-enrich is ever backfillable is unclear from this module alone.
- `next_batch` breaks on the first feature that would overshoot `cap` and scans no further in that stage (`council_batch.py:286`), so fairness across features is determined by `INDEX.json` order — intentional, but ordering is the lever.
- The `.hash` resume signal is consulted by the drift hook outside this feature; whether a forced re-council should also touch it is not decidable from this module.
