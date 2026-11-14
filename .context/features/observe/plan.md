# Observe: implementation map

`confidence: INFERRED`

1. Public exports: `observe/__init__.py:28-49`. Module docstring at `__init__.py:1`.
2. Closed enums: `CorrectionStatus` (`enums.py:8-13`), `Verdict` (`enums.py:16-21`), `ExposureVia` (`enums.py:24-29`).
3. Frozen records: `Exposure` (`models.py:20-53`), `Correction` (`models.py:56-95`), `Attribution` (`models.py:98-125`).
4. Keys and switches: `evidence_key` (`keys.py:22-42`), `keyed_id` (`keys.py:45-48`), `session_key` (`keys.py:51-53`).
5. Kill switch and retention: `evolution_enabled` (`keys.py:56-64`), `retention_days` (`keys.py:67-76`).
6. Hostile-text scan: `scan_text` and patterns (`security.py:5-21`).
7. Ledger I/O: paths (`ledger.py:17-19`), `load` (`ledger.py:57-75`), `save` with pruning (`ledger.py:116-125`).
8. Exposure log: `prune_exposures` (`ledger.py:104-113`), `append_exposures` dedupe (`ledger.py:144-168`), `read_exposures` (`ledger.py:128-141`).
9. Sources map: `read_sources` and `write_sources` (`ledger.py:171-188`).
10. Lock: `observe_lock` wraps `project_lock` (`ledger.py:191-215`).
11. Transcript import: `import_claude` (`importer.py:107-145`). Cursor resume and legacy path at `importer.py:118-136`.
12. Row routing: `_Walk.row` (`importer.py:178-187`), `_assistant` and `_tool_use` (`importer.py:199-239`).
13. Correction capture: `_human`, `_correction`, `_candidates` (`importer.py:254-312`).
14. Tool-result scan: `_tool_result` (`importer.py:314-323`).
15. Item mapping: `exposure_item` (`importer.py:64-87`), `item_version` (`importer.py:90-104`), `_tool_target` (`importer.py:339-350`).
16. Driver: `scan_hosts` (`evidence.py:360-410`) and per-file `_import_file` (`evidence.py:320-340`).
17. Packets: `_texts` (`attribution.py:113-132`), `_packet` (`attribution.py:135-151`), `_next_packet` (`attribution.py:154-175`), `resolution_packet` (`attribution.py:186-191`).
18. Verdicts: `_validate` (`attribution.py:210-226`), `_record` (`attribution.py:229-261`), `record_attribution` (`attribution.py:264-286`).
19. Exposure writes: `_inject_row` (`attribution.py:355-375`), `record_exposure` (`attribution.py:378-397`).
20. Tool-call read: `session_tool_calls` (`attribution.py:323-332`).
21. Evidence stub: `commit_evidence_stub` (`attribution.py:335-352`).
22. Callers: `probation/sync.py:68-77`, `probation/render.py:48-62`, `probation/store.py:94-96`, `evolve/cli/evolve_probation.py:16-78`.

## Tests

- `tests/evolve/test_observe_units.py`: keys, switch, retention, ledger and lock (21 tests).
- `tests/evolve/test_observe_import.py`: import, cursor, correction capture (16 tests).
- `tests/evolve/test_observe_attribution.py`: packets, verdicts, stubs (10 tests).
