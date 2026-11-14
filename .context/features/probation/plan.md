# Probation: implementation map

`confidence: INFERRED`

1. States and routing enums: `dummyindex/evolve/probation/enums.py:8-18` (`State`), `enums.py:21-27` (`Route`), `enums.py:30-35` (`Followed`), `enums.py:38` (`LIVE`).
2. Thresholds, all marked uncalibrated: `constants.py:3-12`.
3. Item record: `models.py:13` (`SCHEMA_VERSION`), `models.py:23-45` (fields), `models.py:47-69` (`to_dict`), `models.py:71-106` (`from_dict`), `models.py:108-119` (`with_state`, `note`).
4. Store: `store.py:19-20` (paths), `store.py:51-56` (`item_path`), `store.py:59-73` (`load_items`, `load_item`), `store.py:76-90` (save and load), `store.py:93-98` (`locked`).
5. Pure rules: `rules.py:21-23` (constants), `rules.py:32-53` (`route`), `rules.py:56-74` (`followed`), `rules.py:77-89` (`harm_reached`, `exposed_sessions`), `rules.py:92-117` (`eligible`), `rules.py:120-124` (`upper_bound`), `rules.py:127-136` (`content_reasons`), `rules.py:139-155` (`compile_probe`).
6. Enter from a gate-passed chat event: `actions.py:61-120`.
7. Sync: `sync.py:48-65` (`eligible_ids`), `sync.py:68-77` (`sync`, kill switch and lock).
   - `sync.py:80-116` (`_sync_held`), `sync.py:119-143` (`_apply`, routing).
   - `sync.py:147-170` (`_count`), `sync.py:173-193` (`_retract`, `_tally`).
   - `sync.py:196-208` (`_window_start`), `sync.py:211-224` (`_live_in_session`), `sync.py:227-242` (`_seed`).
   - `sync.py:251-300` (`_settle`, `_harmed`, `_drift`, `_expire`).
8. Promote and gate: `actions.py:123-142` (`promote`), `actions.py:145-156` (`_promote_one`, quarantine), `actions.py:159-249` (`_gate_and_promote`).
9. Demote: `actions.py:278-299` (`demote`), `actions.py:302-371` (`_demote_promoted`, gate and rollback record).
10. Session block: `render.py:48-104` (`session_block`, `_block`), `render.py:107-128` (`_fit`, `_item_line`), `render.py:131-154` (`_next_line` priority).
11. Report: `render.py:157-223` (`report`), `render.py:226-241` (`format_report`).
12. CLI: `dummyindex/evolve/cli/evolve_probation.py:16-78` (`run_attribute`), `evolve_probation.py:81-153` (`run_probation`). Wiring at `dummyindex/evolve/cli/evolve.py:41`, `evolve.py:67`. Help at `dummyindex/cli/help.py:639`.
13. Callers: `dummyindex/evolve/evolve_learning.py:245-252` (`compile_probe`, `content_reasons`), `evolve_learning.py:358-370` (`enter`). Hook: `dummyindex/cli/memory.py:59-70`, `memory.py:169`.
14. Agent protocol: `dummyindex/skills/evolve/probation-protocol.md:1-45`.

## Flow

Chat event passes gate: `enter` saves a `probation` item. Each session start: `session_block` syncs without probes, lists live items, records exposure. `attribute` verdicts feed `sync` counters. `probation promote` runs `sync(probes=True)`, then gates eligible items. `probation demote` removes the managed block through the gate.

## Tests

- `tests/evolve/test_probation.py`
- `tests/evolve/test_probation_actions.py`
- `tests/evolve/cli/test_evolve_probation_cli.py`
