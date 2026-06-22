# Council — architect notes (stage 2)

## What I changed

- Replaced the loose "Where it lives" + "Architecture in three sentences" prose with a tight **Bounded context** section that states what the feature owns (the deterministic frontier) and explicitly what it does *not* do (no agents, no doc writes, no run state). Listed the three domain modules by responsibility rather than by file dump.
- Folded the prose architecture paragraph into a numbered **Frontier algorithm (stateless, log-derived)** section so the recompute-from-logs loop reads as steps with `path:range` anchors, not a run-on sentence.
- Consolidated the stage/mode/roster/expansion facts under a single **stage machine** paragraph in Data model, each pattern named at `path:range`.
- Reframed every bullet in Key decisions as "decided X because Y".
- Trimmed citation noise: kept one canonical anchor per claim (function-definition line) instead of multi-range spans, since the section-write target is a navigational doc, not a diff.
- Left `spec.md` untouched; wrote no source.

## Patterns named

- **Stateless frontier recomputed from per-feature logs** — `earliest_incomplete_stage` (`council_batch.py:91`) → `next_batch` (`council_batch.py:249`); completion predicate `is_stage_complete` (`council.py:186`).
- **Stage state machine** — `CouncilStage(IntEnum)` (`council_batch.py:31`); mode→stages `active_stages` (`council_batch.py:64`); `CRITIC_ROSTER` (`council_batch.py:53`); per-stage expansion `_units_for_feature` (`council_batch.py:215`); readiness gate `_feature_ready_for` (`council_batch.py:149`).
- **Dev-pick resolution** — `pick_dev` (`dev_pick.py:255`) first-match over the `_RULES` precedence table (`dev_pick.py:243`), with a guaranteeing constant-true fallback and a `fallbacks` ladder.
- **Append-only sentinels** — reset marker `force_recouncil`/`append_reset_marker` (`council_batch.py:114`, `council.py:206`); standalone exemption `is_standalone_complete` (`council.py:230`); artifact backfill `backfill_log_from_artifacts` (`council.py:251`).

## Dependencies surfaced

- **cli-dispatch wraps it** — `cli/council_batch.py:run` (`cli/council_batch.py:65`) is the sole I/O + stdout owner; the domain stays pure and the skill drives the loop.
- **feature-taxonomy provides the units** — `next_batch` reads `features/INDEX.json` (pipeline id set) and per-feature `feature.json` (file list `dev_pick` routes on); taxonomy is upstream of every frontier call.
- **Internal port** — `audit/log.py` is a deliberate structural copy of `council.py`'s log, keyed `round`/`persona`.

## Decisions promoted

- Why stateless/log-derived: logs must survive crash / manual edit / partial parallel dispatch, so no in-memory state → every `--next` converges.
- Why "complete = every started agent finished": lets a `started`/`failed` re-surface the stage and re-run only the unfinished agents.
- Why marker-append over delete for re-council: the log is the audit trail; predicates count only post-marker entries, and the reset is idempotent mid-run.
- Why backfill: pre-v0.20 curated docs + empty logs would be rescheduled and clobbered.
- Why cap at feature granularity: a feature's critic units must not straddle batches.
- Why `.value` serialization: `str()` on a `(str, Enum)` member returns the repr, not the agent name, on Python 3.11+.
- Why port the log rather than share a base: same resumption shape, different key; a copy keeps council and audit pipelines decoupled.
