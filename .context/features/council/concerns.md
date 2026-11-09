## Data integrity

- **Concurrent appends to one feature's log can lose entries.** The read-modify-write is not inter-process atomic. `append_log` reads the JSON, mutates `entries` in memory, then `tmp.replace`s (`council.py:124-159`). Only the final rename is atomic.
- Deep mode dispatches 3 critic units per feature as **parallel Task agents** (`CRITIC_ROSTER`, `council_batch.py:53-58`; `_units_for_feature` critique branch, `council_batch.py:236-245`). Each appends `started`, then `complete`, to the same `features/<id>/council/_council-log.json`.
- Interleaved read-modify-writes drop entries. Last writer wins on the in-memory list. A dropped `complete` leaves a phantom `started`. So `is_stage_complete` (`council.py:186-203`) returns False forever, and the stage never converges.
- **Fixed `.tmp` path makes the atomic write itself racy under concurrency.** Every append writes to one shared name, `log_path.suffix + ".tmp"` (`council.py:156-158`). It is not a per-process unique temp. Two concurrent appenders write the same `_council-log.json.tmp`, and both `replace` it. The second clobbers the first's payload, before or after rename. That compounds the lost update above.
- The data-access convention mandates tmp+replace (`data-access.md:5-9`). It assumes a single writer. The council's parallel dispatch (`plan.md:30`, `plan.md:45`) breaks that assumption for same-feature critic fan-out.
- **Frontier recomputation is idempotent and monotone for partial and failed logs. No concern here.** `earliest_incomplete_stage` (`council_batch.py:91-112`) and `is_stage_complete` (`council.py:186-203`) are pure log-derived functions. A lone `started` or `failed` re-surfaces the stage. `_feature_ready_for` (`council_batch.py:149`) re-dispatches only unfinished agents. Re-running `--next` against a larger log converges (`plan.md:51-52`).
- This holds **as long as** appends are not concurrent on the same feature. The bug is the write path, not the read or frontier path.
- **`force_recouncil` mid-run idempotency holds, but shares the concurrent-append exposure.** `force_recouncil` resets only features whose `earliest_incomplete_stage` is None (`council_batch.py:114-124`). So firing it mid-run is a no-op for in-flight features. It is monotone and idempotent by design (`plan.md:53`).
- However, `append_reset_marker` (`council.py:209-227`) uses the same unlocked `append_log`. A reset marker written during a critic's `complete` write can be lost, or can clobber that write. That corrupts the post-marker window `is_stage_complete` counts (`council.py:194-202`).
- **Corrupt or partial log silently degrades to empty.** Both `read_log` and `append_log` swallow `json.JSONDecodeError`. They treat the payload as `{}` (`council.py:163-170`, `council.py:146-150`). A truncated write does this, from the `.tmp` race or a crash during `write_text`.
- The feature then reads as empty. The frontier reschedules it from stage 1 (`earliest_incomplete_stage`, `council_batch.py:106-111`). That clobbers completed work. It is the exact failure `backfill_log_from_artifacts` was built to prevent (`council.py:251-292`). Corruption makes it reachable, not only pre-v0.20 absence.
- The council log validates `status`, `stage`, and `agent` on write (`council.py:138-145`). But it never validates `schema_version` on read. Other artifacts enforce a schema-version guard (`data-access.md:11-13`). So a future-version or malformed log is indistinguishable from an empty one.
- **Stage monotonicity is sound. Backfill never regresses a stage with any entry.** `backfill_log_from_artifacts` skips any stage that already has an entry, even pre-reset (`council.py:264-271`; docstring `council.py:251-262`). So it cannot overwrite real progress.
- It covers stages 1–4 only (`_ARTIFACT_STAGE_DOCS`, `council.py:73-77`, plus `_FLOW_STAGE`). Stage 5 TREE is dev-authored but not backfillable (open question, `plan.md:61`). That is not a data-integrity defect. A tree-enrich run resumed against a v0.20-backfilled log correctly re-dispatches stage 5. It never silently skips it.

## Security

- **Feature-id path traversal in `write_section`.** The agent-supplied `--feature` joins into a filesystem path with no slug validation. Only an `is_dir()` gate applies. `run_section_write` reads `--feature` raw (`cli/features.py:260`) and passes it to `write_section`.
- That does `feat_dir = features_dir / feature_id` and guards only on `feat_dir.is_dir()` (`context/domains/features/ops.py:472-477`). It then writes the section file via tmp+rename (`ops.py:489-490`).
- `section` arg is hardened. It rejects `/` and leading `.` (`ops.py:479-481`; CLI `_validate_section_name`, `cli/features.py:223-239`). But `feature_id` never goes through `_validate_feature_id` (`features/helpers.py:18-30`), the strict `[a-z0-9_-]` slug validator.
- `merge_feature` (`ops.py:206`), `rename_feature` (`ops.py:48`), and placement (`placement.py:295,397`) all apply it.
- Attack path: a critic Task agent, or any caller of `dummyindex context section-write`, passes `--feature ../../../../etc/skel/x`. Or it passes any existing dir reachable from `.context/features/`. `is_dir()` succeeds for a real directory. So `concerns.md` is written outside the feature tree.
- Council agents are untrusted-prompt-shaped and call this exact verb, so input is attacker-influenceable. Severity HIGH: arbitrary in-tree-relative file write or overwrite of `<dir>/<section>.md`.
- Fix: call `_validate_feature_id(feature_id)` at the top of `write_section` and at the `section-write` CLI boundary, mirroring `merge_feature`. Reject any id that is not a bare slug.
- **Same traversal class in `append_log`, the `council-log` verb.** `--feature` reaches a path join with no slug check. `run_council_log` (`cli/council.py:29`) forwards `--feature` straight to `append_log`.
- That builds `feat_dir = features_dir / feature_id` and checks only `feat_dir.is_dir()` (`context/domains/council.py:118-121`). It then runs `mkdir(parents=True)` on `<feat_dir>/council/` and writes `_council-log.json` (`council.py:132-159`).
- `agent` is guarded against `/` (`council.py:129-130`). `feature_id` is not. Contrast `council-log backfill`, which checks membership: `feature_id not in indexed` against `features/INDEX.json` (`cli/council.py:116-124`). Plain `council-log` skips that check.
- Attack path: `dummyindex context council-log --feature ../../../tmp/evil --stage 1 --agent x --status started` creates `../../../tmp/evil/council/_council-log.json` if `../../../tmp/evil` exists. It plants a JSON file and a `council/` dir outside `.context/features/`.
- Severity MEDIUM. The leaf is fixed at `council/_council-log.json`, but the directory is attacker-controlled.
- Fix: validate `feature_id` as a slug, reusing `_validate_feature_id`. Or assert `feat_dir.resolve()` is `relative_to(features_dir)` before any write.
- **`remove_flow` is an unbounded `unlink()` keyed on unvalidated ids.** It is a deletion primitive, not only a write. `remove_flow` joins both ids raw. It builds `feat_dir = features_dir / feature_id`, guarded only by `is_dir()` (`ops.py:372-376`).
- It then builds `flow_json = feat_dir / "flows" / f"{flow_id}.json"`, plus the `.md` form. It calls `p.unlink()` on any path that `.exists()` (`ops.py:381-388`). Neither id is slug-validated.
- `flow_id="../../<target>"` resolves the unlink outside `flows/`. No extension control is needed if the file already ends in `.json` or `.md`. For example, `--flow ../../authentication/concerns` deletes another feature's `concerns.md` or `.json`.
- The CLI `run_flow_remove` passes both straight through (`cli/features.py:179,196`). Severity HIGH: out-of-tree file deletion and cross-feature artifact destruction. An idempotent no-op masks it as benign.
- Fix: `_validate_feature_id(feature_id)`, a matching slug guard on `flow_id`, and a `relative_to(feat_dir)` containment assert before `unlink`.
- **`from-file` source is read with no containment check.** `section-write` is also an arbitrary-file READ into `.context`. `write_section` does `content = source_file.read_text()` on the raw `--from-file` path (`ops.py:486-489`). The CLI wraps it as `Path(from_file)` with no bound (`cli/features.py:262,290`).
- A caller can point `--from-file /etc/passwd`, or any readable file. Its contents then land in a committed `concerns.md` inside `.context/`. The next agent reads that as trusted context.
- Severity MEDIUM. It matters because downstream agents trust `.context/`, which may be committed.
- By design for a local CLI, but worth a note. The source is unbounded. The destination is access-controlled by section name only.
- Mitigation: acceptable for a single-user local tool. If council agents are ever sandboxed, bound `--from-file` to the repo or workspace root.
- **Agent-supplied `note` is persisted, not an injection vector. Flagged NON-issue.** `note` flows from `--note` into `LogEntry.note`. `json.dumps(payload, indent=2)` serializes it (`council.py:158`).
- Control characters are JSON-escaped, so there is no line forging and no JSON breakout. `status`, `stage`, and `agent` are validated on write (`council.py:123-130`).
- The only soft concern: `note` has no length bound. It is read back and matched with `.startswith(STANDALONE_NOTE_PREFIX)` (`council.py:245`).
- An agent that sets `--note standalone...` on a stage-0 `complete` entry can self-exempt a feature from rescheduling (`is_standalone_complete`, `council.py:230-248`).
- That is a trust-the-agent integrity quirk, not a memory-safety or injection bug. Severity LOW or INFORMATIONAL. No fix needed. `note` semantics are load-bearing, and agents are trusted to use the `standalone` prefix honestly.
- **Corrupt-log swallowing has a security framing too.** Silent `{}` on `JSONDecodeError` makes a planted or truncated `_council-log.json` look like a fresh feature. `read_log` and `append_log` both treat any `JSONDecodeError` as empty (`council.py:139-140`, `council.py:168-171`). They never check `schema_version` on read.
- With the traversal write, an attacker who can drop a log file has two options.
- First, truncate the log. It then reads as empty. The frontier reschedules from stage 1, clobbering completed council work.
- Second, plant valid JSON with forged `complete` or `standalone` entries. That short-circuits `is_stage_complete` or `is_standalone_complete`.
- Severity MEDIUM. It overlaps the Data-integrity finding, but the trigger is adversarial, not a crash.
- Fix: validate `schema_version` on read. Fail loud, or quarantine, on decode error. Do not substitute `{}` silently.

## Product surface

- **`--force` on a mid-run feature is a silent no-op.** No feedback says the reset was refused. `force_recouncil` appends a reset marker only to features whose `earliest_incomplete_stage` is None (`council_batch.py:131-136`). An in-flight feature is skipped, and its id is absent from the returned tuple.
- The CLI prints the "forced re-council for: …" line only when `forced` is non-empty (`cli/council_batch.py:175-176`).
- So `dummyindex context council-batch --next --feature X --force` against a half-completed X prints the ordinary next batch. It says nothing about X. Observed: the operator believes they forced a fresh run. Nothing happened.
- The gap: no notice that feature X is mid-run and not reset, with "finish or let it converge first". Neither text nor JSON `forced: []` says so (`cli/council_batch.py:170`).
- **Frontier is a hard global barrier.** One slow or stuck feature freezes every other feature's progress. `earliest_incomplete_stage` returns the single lowest incomplete stage for any pipeline feature (`council_batch.py:104-111`). `next_batch` dispatches only that stage (`council_batch.py:268-272`).
- A feature still at SPECIFY pins the whole batch to stage 1. Features whose plan or critique is ready cannot advance until it clears.
- The text output says `stage N — K parallel units` (`cli/council_batch.py:181-187`). It never says "M other features are blocked waiting on this stage". An operator watching a 20-feature run stall has no surfaced reason.
- The gap: no per-feature frontier or blocked-on visibility.
- **`failed` is invisible in the dispatch surface.** A retry looks the same as a first attempt. A `failed` entry makes `is_stage_complete` return False (`council.py:201-203`). So `_feature_ready_for` re-surfaces the stage (`council_batch.py:158-163`).
- The feature re-emits as a plain `DispatchUnit`, with no failure flag (`DispatchUnit` fields, `council_batch.py:166-183`). Neither text nor JSON marks a unit as a retry, or carries the prior `failed` note.
- Observed: after a crash, a re-run shows the same `feature: role → subagent` line for attempt 1 and attempt 5.
- The gap: no retry count and no "previously failed: <note>" signal. So a persistently failing agent loops with no escalation.
- **Cap silently overshoots on the first oversized feature.** The cap guard is `if collected and len(collected)+len(feature_units) > cap` (`council_batch.py:286`). When the first ready feature alone exceeds cap, `collected` is empty. The guard is skipped, and all units ship.
- Example: `--cap 2` in deep mode, where one feature expands to 3 critic units (`CRITIC_ROSTER[DEEP]`, `council_batch.py:56-61`). This is intended. A feature is never split (`plan.md:55`, `plan.md:62`).
- But the output prints `K parallel units` (`cli/council_batch.py:180-184`) with no "exceeds your --cap of N" note. An operator who set a cap gets more agents than requested.
- The gap: no overshoot disclosure.
- **Fairness across features follows `INDEX.json` order, with no operator lever and no disclosure.** When ready features at a stage exceed cap, `next_batch` walks `pipeline_ids` in INDEX.json order. It `break`s at the first overflow (`council_batch.py:276-288`).
- So the same low-INDEX features win every batch. A high-INDEX feature can starve across many `--next` calls.
- The output never says features were deferred for cap. It offers no way to prioritise.
- The gap: the deferred set is invisible. An operator cannot tell "3 more features are ready but capped out" from "only these 3 are ready".
- **A corrupt or truncated `_council-log.json` mid-council reschedules silently to stage 1.** With no enriched docs yet, it happens with no warning. `read_log` swallows `JSONDecodeError` and returns `[]` (`council.py:168-171`). The frontier treats the feature as fresh and re-dispatches from SPECIFY.
- Its only guard, `_warn_if_backfill_needed`, fires when `needs_artifact_backfill` is true: an empty log AND enriched artifacts on disk (`cli/council_batch.py:41-51`; `council.py:295-306`).
- A feature corrupted at stage 1 or 2, with no enriched spec or plan yet, trips no warning. It restarts silently.
- Even the artifact case warns only about backfill. It never says "this log failed to parse". Observed: an operator sees a feature back at stage 1 with no explanation.
- The gap: a malformed log looks the same as a fresh feature in operator output.
- **The `--next` text output has no "what's left" summary.** Completion is the only terminal signal. Output is either `all features complete for this mode.` (`cli/council_batch.py:177-178`) or the current stage's units. It has no count of remaining stages or features, and no progress fraction.
- From one `--next` call, an operator cannot tell if the run is near done or at its start.
- The gap: no progress or remaining-work surface across the multi-call loop.
- **(reconcile 2026-06-23) The dev-pick `fallbacks` ladder never reaches the dispatch-unit JSON.** `pick_dev` resolves an ordered `fallbacks` list of alternate `subagent_type`s (`dev_pick.py`). The wire `DispatchUnit` and `to_dict` expose only the single `subagent_type` (`council_batch.py:176-183`).
- The orchestrator gets the primary agent but not the alternates to try when it is not installed. The fallback ladder is invisible at the CLI boundary. The skill must re-derive availability itself. Gap: emit `fallbacks` in the unit JSON.
- **(reconcile 2026-06-23) Depth and `--mode` error clarity fix verified.** `council_batch` validates the flag against `CouncilMode` up front (`cli/council_batch.py:114-119`). So the remaining `except ConfigError` (`cli/council_batch.py:131-134`) surfaces a malformed `config.json` verbatim.
- The old `--depth/--mode must be light|standard|deep` message no longer appears there. This matches `spec.md` and `plan.md`. No gap.

## Cross-review notes

- The two Security path-traversal findings (`write_section` feature-id, `council.py:118-121`; `append_log` feature-id, `cli/council.py:29`) have a product-surface tail. The `council-log` success line echoes the raw `feature_id` verbatim (`cli/council.py:69-72`). `--json` re-emits unvalidated ids.
- So a traversal id (`../../tmp/evil`) reads to the operator as a legitimate feature.
- The Security fix (`_validate_feature_id` at the CLI boundary) also fixes this UX gap. Rejecting the id at parse time beats writing out of tree and printing a misleading success row.
- I concur with the Security severity. The missing validation also erodes trust in success output, not only containment.
