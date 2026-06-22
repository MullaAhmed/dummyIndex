# Multi-agent council — plan

confidence: INFERRED

## Bounded context

This feature owns the **deterministic frontier** of dummyindex's per-feature doc pipeline — the LLM-free plumbing the council skill calls between dispatches. It does *not* run agents, write docs, or hold run state. Its job: given the append-only per-feature logs, answer "what should fire next, for whom, in which role" and "did each invocation finish".

Three domain modules under `dummyindex/context/domains/`:
- `council.py` — the per-feature audit log: append/read, the completion predicate, and the reset/standalone/backfill sentinels.
- `council_batch.py` — the stage frontier + dispatch-unit expansion (the "what fires next" computation).
- `dev_pick.py` — the stack-specialist author picker (which persona writes a feature's docs).

CLI wrappers (the only I/O boundary): `cli/council_batch.py` (`council-batch --next`) and `cli/council.py` (`council-log` + `backfill`). A ported twin of the resumption log lives at `audit/log.py` (alphabet `audit/enums.py`, error `audit/errors.py`) serving the on-demand audit panel. Per-feature logs persist at `.context/features/<id>/council/_council-log.json`. Tests: `tests/context/domains/{test_council_batch,test_council_cli,test_dev_pick}.py` + `audit/test_audit_domain.py`.

## Dependencies

- **cli-dispatch wraps this.** `cli/council_batch.py:run` (`cli/council_batch.py:65`) parses flags, loads ids, and is the sole owner of file I/O + stdout; the domain stays pure. The skill drives the loop, not this code.
- **feature-taxonomy provides the units.** `next_batch` reads `features/INDEX.json` for the pipeline id set and `features/<id>/feature.json` for the file list `dev_pick` routes on — the taxonomy feature is upstream of every frontier call.
- **Internal port:** `audit/log.py` is a structural copy of `council.py`'s log (see "decided to port", below), keyed `round`/`persona` not `stage`/`agent`.

## Frontier algorithm (stateless, log-derived)

The pipeline holds **no run state**. Each `council-batch --next` recomputes the whole frontier from the logs on disk:

1. `earliest_incomplete_stage` (`council_batch.py:91`) scans every pipeline feature and returns the lowest active stage not yet complete for *all* of them.
2. `next_batch` (`council_batch.py:249`) gathers features ready for that stage — prior active stage complete, `_feature_ready_for` at `council_batch.py:149` — and expands each via `_units_for_feature` (`council_batch.py:215`) into role-specific `DispatchUnit`s.
3. It returns up to `cap` units, **never splitting a single feature** (`council_batch.py:286`).

The skill dispatches those units as parallel Task agents; each appends `started`/`complete` via `council-log`; the loop re-runs `--next` against the now-larger log until `Batch.complete` is true.

## Data model

`_council-log.json` (`council.py` log schema):
```
{ "schema_version": 1, "feature_id": "<id>",
  "entries": [ { "timestamp", "stage", "agent", "status", "note" }, ... ] }
```
Append-only; atomic writes (`tmp` + `replace`).

- **stage** — `CouncilStage(IntEnum)` `SPECIFY=1, PLAN=2, CRITIQUE=3, FLOW=4, TREE=5` (`council_batch.py:31`). Stage 0 is reserved for sentinel markers.
- **status** — `started | complete | failed | skipped`. A stage is *complete* iff every agent that `started` it reached `complete`/`skipped` (`is_stage_complete`, `council.py:186`).
- **sentinels** — `recouncil` + note `force-recouncil` is the stage-0 reset marker (`council.py:206`); `backfill` + `backfilled-from-artifacts` is a synthetic completion; a stage-0 `complete` note prefixed `standalone` exempts an Outcome-C feature entirely (`is_standalone_complete`, `council.py:230`).

**Stage machine — mode → active stages** (`active_stages`, `council_batch.py:64`): `light` = specify + flow; `standard`/`deep` add plan + critique; `tree` appends only under `--tree-enrich`. **Critic roster** (`CRITIC_ROSTER`, `council_batch.py:53`): light none, standard one (security), deep three. **Dispatch-unit expansion** (`_units_for_feature`, `council_batch.py:215`): specify/flow/tree → one dev unit; plan → one architect unit; critique → one unit per roster critic. `DispatchUnit` carries `(feature_id, stage, role, subagent_type, framework)`; `role` doubles as the `council-log --agent` value and persona-file selector.

**Dev-pick resolution** (`pick_dev`, `dev_pick.py:255`): first-match-wins over the `_RULES` precedence table (`dev_pick.py:243`), keyed on a feature's file list + the repo's harvested dependency tokens. The constant-true fallback rule guarantees a persona; `DevPickError` is reserved for a malformed table, not a miss. Each pick carries an ordered `fallbacks` ladder for when the primary subagent isn't installed.

## Key decisions

- **Decided the frontier is stateless and log-derived** because the logs must survive a crash, a manual edit, or a partial parallel dispatch — with no in-memory run state, every `--next` call converges on the same next move. This is why `is_stage_complete` is a pure function of the log (`council.py:186`).
- **Decided "complete = every started agent finished"** so a lone `started`/`failed` re-surfaces the stage and the re-run targets only the unfinished agents — resumption without redoing finished work (`council.py:186`, `council_batch.py:149`).
- **Decided forced re-council appends a marker rather than deleting history** because the log is the audit trail: `force_recouncil` (`council_batch.py:114`) appends a stage-0 `recouncil` marker and the completion predicates count only entries *after* the latest marker (`council.py:194`). It resets only features with no incomplete stage, so firing it mid-run is idempotent.
- **Decided to backfill from artifacts** because pre-v0.20 indexes have curated docs but empty logs, and the frontier would reschedule and clobber them. `backfill_log_from_artifacts` (`council.py:251`) synthesises `complete` entries for stages whose enriched (non-stub) artifacts exist, never touching a stage that already has any entry; the CLI warns when most features need it (`cli/council_batch.py:27`).
- **Decided to honour `cap` at feature granularity** so a feature's critic units never straddle two batches — even when the first feature overshoots `cap` (`council_batch.py:286`).
- **Decided to serialize `subagent_type` as `.value`** because on Python 3.11+ `str()` on a `(str, Enum)` member returns the `SubagentType.FRONTEND` repr, not the agent name — wrong on the wire (`council_batch.py:215` expansion, `dev_pick.py:255` pick).
- **Decided to port the council log into `audit/log.py`** rather than abstract a shared base, because the audit panel's resumption needs the same atomic-append + "every started finished" shape but a different key (`round`/`persona`); a deliberate copy keeps the two pipelines decoupled.

## Open questions

- Stage 5 (`TREE`) is dev-authored in `_units_for_feature` (`council_batch.py:215`) but `_ARTIFACT_STAGE_DOCS` backfill covers only stages 1–4 (`council.py:73`) — whether tree-enrich is ever backfillable is unclear from this module alone.
- `next_batch` breaks on the first feature that would overshoot `cap` and scans no further in that stage (`council_batch.py:286`), so fairness across features is determined by `INDEX.json` order — intentional, but ordering is the lever.
