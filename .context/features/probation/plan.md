# Probation: implementation map

`confidence: INFERRED`

1. States and routing enums: `dummyindex/context/domains/probation/enums.py:8-18` (`State`), `enums.py:21-27` (`Route`), `enums.py:30-35` (`Followed`), `enums.py:38` (`LIVE`).
2. Thresholds, all marked uncalibrated: `constants.py:3-12`.
3. Item record: `models.py:12` (`SCHEMA_VERSION`), `models.py:22-44` (fields), `models.py:46-68` (`to_dict`), `models.py:70-105` (`from_dict`), `models.py:107-118` (`with_state`, `note`).
4. Store: `store.py:17-18` (paths), `store.py:49-54` (`item_path`), `store.py:57-71` (`load_items`, `load_item`), `store.py:74-88` (save and load), `store.py:91-96` (`locked`).
5. Pure rules: `rules.py:20-22` (constants), `rules.py:31-52` (`route`), `rules.py:55-73` (`followed`), `rules.py:76-88` (`harm_reached`, `exposed_sessions`), `rules.py:91-116` (`eligible`), `rules.py:119-123` (`upper_bound`), `rules.py:126-135` (`content_reasons`), `rules.py:138-154` (`compile_probe`).
6. Enter from a gate-passed chat event: `actions.py:57-116`.
7. Sync: `sync.py:46-63` (`eligible_ids`), `sync.py:66-75` (`sync`, kill switch and lock).
   - `sync.py:78-114` (`_sync_held`), `sync.py:117-141` (`_apply`, routing).
   - `sync.py:145-168` (`_count`), `sync.py:171-191` (`_retract`, `_tally`).
   - `sync.py:194-206` (`_window_start`), `sync.py:209-222` (`_live_in_session`), `sync.py:225-240` (`_seed`).
   - `sync.py:249-298` (`_settle`, `_harmed`, `_drift`, `_expire`).
8. Promote and gate: `actions.py:119-138` (`promote`), `actions.py:141-152` (`_promote_one`, quarantine), `actions.py:155-245` (`_gate_and_promote`).
9. Demote: `actions.py:274-295` (`demote`), `actions.py:298-367` (`_demote_promoted`, gate and rollback record).
10. Session block: `render.py:48-104` (`session_block`, `_block`), `render.py:107-128` (`_fit`, `_item_line`), `render.py:131-154` (`_next_line` priority).
11. Report: `render.py:157-223` (`report`), `render.py:226-241` (`format_report`).
12. CLI: `dummyindex/cli/evolve_probation.py:16-78` (`run_attribute`), `evolve_probation.py:81-153` (`run_probation`). Wiring at `dummyindex/cli/evolve.py:40`, `evolve.py:67`. Help at `dummyindex/cli/help.py:639`.
13. Callers: `dummyindex/context/domains/evolve_learning.py:238-245` (`compile_probe`, `content_reasons`), `evolve_learning.py:351-363` (`enter`). Hook: `dummyindex/cli/memory.py:59-70`, `memory.py:169`.
14. Agent protocol: `dummyindex/skills/evolve/probation-protocol.md:1-45`.

## Flow

Chat event passes gate: `enter` saves a `probation` item. Each session start: `session_block` syncs without probes, lists live items, records exposure. `attribute` verdicts feed `sync` counters. `probation promote` runs `sync(probes=True)`, then gates eligible items. `probation demote` removes the managed block through the gate.

## Tests

- `tests/context/domains/test_probation.py`
- `tests/context/domains/test_probation_actions.py`
- `tests/cli/test_evolve_probation_cli.py`
