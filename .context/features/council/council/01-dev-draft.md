# Multi-agent council — plan

confidence: INFERRED

## Where it lives

The domain logic is three modules under `dummyindex/context/domains/`: `council.py` (the per-feature audit log + resumption predicates), `council_batch.py` (stage frontier + dispatch-unit expansion), and `dev_pick.py` (the stack-specialist author picker). The thin CLI wrappers are `dummyindex/cli/council_batch.py` (the `council-batch --next` verb) and `dummyindex/cli/council.py` (the `council-log` verb + `backfill` subverb). A ported twin of the audit-debate resumption log lives at `dummyindex/context/domains/audit/log.py` with its alphabet in `audit/enums.py` and error in `audit/errors.py`. Tests sit under `tests/context/domains/` (`test_council_batch.py`, `test_council_cli.py`, `test_dev_pick.py`, `audit/test_audit_domain.py`). Per-feature logs are written to `.context/features/<id>/council/_council-log.json`.

## Architecture in three sentences

The pipeline is **stateless between calls**: the orchestrating LLM skill repeatedly calls `council-batch --next`, which recomputes the entire frontier from scratch each time by reading the per-feature `_council-log.json` files — there is no in-memory run state. `next_batch` asks `earliest_incomplete_stage` for the lowest active stage not yet complete for *every* pipeline feature (`council_batch.py:91-111`), then gathers the features ready for that stage (their prior active stage complete, `council_batch.py:149-163`), expands each into role-specific `DispatchUnit`s, and returns up to `cap` of them without ever splitting a single feature's units (`council_batch.py:249-289`). The skill dispatches those units as parallel Task agents, each agent appends `started`/`complete` log entries via `council-log`, and the loop re-runs `--next` against the now-larger log until `complete` is true.

## Data model

`_council-log.json` (`council.py:11-33`):
```
{ "schema_version": 1, "feature_id": "<id>",
  "entries": [ { "timestamp", "stage", "agent", "status", "note" }, ... ] }
```
Entries are append-only; writes are atomic (`tmp` write + `replace`, `council.py:157-159`).

- **stage** — `CouncilStage` int: `SPECIFY=1, PLAN=2, CRITIQUE=3, FLOW=4, TREE=5` (`council_batch.py:31-38`). Stage 0 is reserved for sentinel markers (recouncil / standalone).
- **status** — one of `started | complete | failed | skipped` (`council.py:45`). A stage is *complete* iff every agent that started it reached `complete`/`skipped` (`council.py:186-203`).
- **agent / note sentinels** — `recouncil` + note `force-recouncil` is the stage-0 reset marker; `backfill` + `backfilled-from-artifacts` is a synthetic completion; a stage-0 `complete` entry with note prefixed `standalone` exempts an Outcome-C feature from the pipeline entirely (`council.py:52-63`, `council.py:230-248`).

**Mode → active stages**: `light` = specify + flow; `standard`/`deep` = + plan + critique; `tree` appended only when `--tree-enrich` (`council_batch.py:64-77`). **Critic roster by mode**: light none, standard one (security), deep three (`council_batch.py:53-61`). **DispatchUnit** carries `(feature_id, stage, role, subagent_type, framework)` — `role` doubles as the `council-log --agent` value and persona-file selector (`council_batch.py:166-183`).

## Key decisions

- **Stateless frontier recomputed from logs.** No run state persists between `--next` calls; the log files are the single source of truth, so a crash, a manual edit, or a parallel partial dispatch all converge on the next call. This is why `is_stage_complete` is a pure function of the log (`council.py:186-203`).
- **Resumption via "every started agent completed".** A stage counts as done only when all its agents reached `complete`/`skipped`; a lone `started`/`failed` re-surfaces the stage so a re-run targets only the unfinished agents (`council.py:186-203`, `council_batch.py:149-163`).
- **Forced re-council via append-only reset marker.** Rather than deleting log history, `force_recouncil` appends a stage-0 `recouncil` marker, and the completion predicates only count entries *after* the latest marker (`council.py:206-227`, `is_stage_complete` reset-handling `council.py:194-200`). `force_recouncil` only resets features with no incomplete stage, so kicking it off mid-run is idempotent (`council_batch.py:114-137`).
- **Artifact backfill guards the plan.md-clobber hazard.** Pre-v0.20 indexes have curated docs but empty logs; the frontier would reschedule and overwrite them. `backfill_log_from_artifacts` synthesises `complete` entries for stages whose enriched (non-stub) artifacts exist, never touching a stage that already has any entry (`council.py:251-292`); the CLI warns when most features need it (`cli/council_batch.py:27-51`).
- **Cap honoured at feature granularity.** A single feature's units are never split across batches, even when that overshoots `cap` for the first feature (`council_batch.py:286-288`).
- **Wire-safe enum serialization.** `subagent_type` is emitted as `.value`, never `str(member)` — on Python 3.11+ `str()` on a `(str, Enum)` member returns the `SubagentType.FRONTEND` repr, not the agent name (`council_batch.py:208-212`, `dev_pick.py:111-120`).
- **Audit log is a deliberate port.** `audit/log.py` mirrors the council log's atomic-append + resumption shape for the on-demand audit panel, keyed by `round`/`persona` instead of `stage`/`agent` (`audit/log.py:1-25`).

## Open questions

- Stage 5 (`TREE`) is dev-authored in `_units_for_feature` (`council_batch.py:223-224`) but `_ARTIFACT_STAGE_DOCS` backfill only covers stages 1–4 (`council.py:73-78`); whether tree-enrich is ever backfillable is unclear from this module alone.
- `next_batch` honours `cap` by breaking on the first feature that would overshoot but keeps scanning no further — features after an over-cap feature in a single stage wait for the next call; this is intentional per the comment but the ordering of `pipeline_ids` (INDEX.json order) is what determines fairness.
