# Architect notes — stage 2 (plan reorganisation)

The dev draft was accurate and well-cited; this was a sharpening pass, not a rewrite. No claim was removed for being wrong — only reframed, relocated, or promoted.

## What I changed

- Added a **Bounded context** section at the top. The draft scattered "LLM-free", "domain modules stay pure", "CLI is the only I/O boundary" across three later sections. Pulled them into one frontier-engine boundary statement with an explicit inside/outside split, because the whole feature is one load-bearing computation — *given the logs, what fires next?* — and that was implicit before.
- Promoted the **Architecture in three sentences** cites to point at the helper functions, not just the entrypoints: added `earliest_incomplete_stage` (`council_batch.py:91`), `_feature_ready_for` (`council_batch.py:149`), `dev_pick.pick_dev` (`dev_pick.py:255`) inline so the frontier chain is traceable in one read.
- Replaced the implicit "dominant pattern" sentence with a dedicated **Patterns (named, with where they live)** section — each pattern now carries its symbol + line, per the no-pattern-without-a-location rule.
- Added an explicit **Dependencies** section (upstream / downstream) that the draft never had — dependencies were only inferable from prose.
- Rewrote **Key decisions** bullets into "Decided X because Y" form and added two decisions the draft stated as behaviour but never as a decision (`--force` requires `--feature`; the two-failure split behind the depth-flag validation).
- Corrected drifted line cites against `map/symbols.json` (def-line vs body-line offsets): `is_standalone_complete` 232→230, `latest_status` 334→332, `backfill_log_from_artifacts` 253→251, `append_reset_marker` 212→210, `needs_artifact_backfill` 297→295. The reset-marker truncation cite moved `council.py:195-205`→`197-205` to match the actual loop (verified at `council.py:197-205`).

## Patterns named

- **Frontier / work-queue** — `next_batch` (`council_batch.py:249-289`) over `earliest_incomplete_stage` (`council_batch.py:91`). The queue is the diff between the active-stage sequence and the logs; never stored.
- **Per-feature log as state (event-sourced completion)** — `is_stage_complete` (`council.py:188`) folds the append-only stream rather than reading a flag. Verified: the function rebuilds `by_agent` from `read_log` on every call (`council.py:195-205`).
- **Resume-by-recomputation** — the `next_batch → is_stage_complete` chain; the stateless claim is corroborated by the HIGH-confidence orchestration doc `dummyindex/skills/council/22-parallel-dispatch.md:52-56` (spot-checked: cites `_council-log.json`, resolves).
- **Reset-by-marker, not by-delete** — `_is_reset_marker` + truncation in `is_stage_complete` (`council.py:197-205`); written by `append_reset_marker` (`council.py:210`).
- **First-match-wins precedence table** — `pick_dev` over `_RULES` (`dev_pick.py:255`), constant-true terminal rule.
- **Deliberate copy over shared base** — `audit/log.py` ports the log; only `log_scan.last_matching` is shared.

## Dependencies surfaced

- **Upstream:** `features/INDEX.json` (`cli/council_batch.py:136-144`, missing → hard usage error); `config.resolve_depth` + `config.json` (`config.py:323-342`); per-feature `feature.json` file list + harvested dep tokens (`dev_pick.harvest_dep_tokens`, `dev_pick.py:306`; `read_feature_files`, `dev_pick.py:328`).
- **Downstream:** the council skill orchestrator — sole consumer of `Batch`, dispatches one Task per unit in one message, barrier, repeat (HIGH-confidence contract `dummyindex/skills/council/22-parallel-dispatch.md:9-23`, spot-checked clean); the SessionStart drift hook consuming the `.hash` signal (outside this feature).

## Decisions promoted

- **Frontier is stateless / recomputed** because the log must survive crash / manual edit / partial dispatch — `is_stage_complete` is a pure fold (`council.py:188`), `next_batch` takes only on-disk inputs (`council_batch.py:249`).
- **`--force` requires `--feature`** because a forced re-council is inherently scoped and a global re-run is destructive of in-flight work — rejected up front (`cli/council_batch.py:96-102`). (New: the draft listed this only as behaviour.)
- **Depth flag validated before `resolve_depth`, then the real `ConfigError` surfaced** because the two failures have different causes and the old catch-all conflated them — validate first (`cli/council_batch.py:114-119`), so a later `ConfigError` can only be a malformed `config.json` and is printed verbatim (`cli/council_batch.py:131-134`). Verified against source: the two-layer guard is present exactly as described.
- **Forced re-council appends a marker, not a delete** because the log is the audit trail — `force_recouncil` resets only features with no incomplete active stage (`council_batch.py:130-136`), making mid-run firing idempotent.
- **Cap honoured at feature granularity** because a feature's critic units must never straddle two batches — `next_batch` breaks before overshoot (`council_batch.py:286-287`, verified).

## Audit trail / conflicts

- No code-vs-doc conflict found. The two HIGH-confidence orchestration docs (`22-parallel-dispatch.md`, `19-resume.md`) agree with the source on the stateless frontier and resume-by-log model; their cited identifiers resolve against `map/symbols.json`.
- Only drift was cosmetic: several plan line-cites were one-to-two lines high (decorator/docstring offset). Code wins — corrected in place. Spec.md was not touched.
- Did not touch the Open questions section — all three are genuine module-boundary unknowns, not resolvable from this feature's source alone.
