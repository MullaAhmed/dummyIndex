# Observe: implementation map

`confidence: INFERRED`

1. Public exports: `observe/__init__.py:28-49`. Module docstring at `__init__.py:1`.
2. Closed enums: `CorrectionStatus` (`enums.py:8-13`), `Verdict` (`enums.py:16-21`), `ExposureVia` (`enums.py:24-29`).
3. Frozen records: `Exposure` (`models.py:20-53`), `Correction` (`models.py:56-95`), `Attribution` (`models.py:98-125`).
4. Keys and switches: `evidence_key` (`keys.py:22-42`), `keyed_id` (`keys.py:45-48`), `session_key` (`keys.py:51-53`).
5. Kill switch and retention: `evolution_enabled` (`keys.py:56-64`), `retention_days` (`keys.py:67-76`).
6. Hostile-text scan: `scan_text` and patterns (`security.py:5-21`).
7. Ledger I/O: paths (`ledger.py:16-18`), `load` (`ledger.py:56-74`), `save` with pruning (`ledger.py:115-124`).
8. Exposure log: `prune_exposures` (`ledger.py:103-112`), `append_exposures` dedupe (`ledger.py:143-167`), `read_exposures` (`ledger.py:127-140`).
9. Sources map: `read_sources` and `write_sources` (`ledger.py:170-187`).
10. Lock: `observe_lock` wraps `project_lock` (`ledger.py:190-214`).
11. Transcript import: `import_claude` (`importer.py:106-144`). Cursor resume and legacy path at `importer.py:117-135`.
12. Row routing: `_Walk.row` (`importer.py:177-186`), `_assistant` and `_tool_use` (`importer.py:198-238`).
13. Correction capture: `_human`, `_correction`, `_candidates` (`importer.py:253-311`).
14. Tool-result scan: `_tool_result` (`importer.py:313-322`).
15. Item mapping: `exposure_item` (`importer.py:63-86`), `item_version` (`importer.py:89-103`), `_tool_target` (`importer.py:338-349`).
16. Driver: `scan_hosts` (`evidence.py:360-410`) and per-file `_import_file` (`evidence.py:320-340`).
17. Packets: `_texts` (`attribution.py:111-130`), `_packet` (`attribution.py:133-149`), `_next_packet` (`attribution.py:152-173`), `resolution_packet` (`attribution.py:184-189`).
18. Verdicts: `_validate` (`attribution.py:208-224`), `_record` (`attribution.py:227-259`), `record_attribution` (`attribution.py:262-284`).
19. Exposure writes: `_inject_row` (`attribution.py:353-373`), `record_exposure` (`attribution.py:376-395`).
20. Tool-call read: `session_tool_calls` (`attribution.py:321-330`).
21. Evidence stub: `commit_evidence_stub` (`attribution.py:333-350`).
22. Callers: `probation/sync.py:66-75`, `probation/render.py:48-62`, `probation/store.py:92-94`, `cli/evolve_probation.py:16-78`.

## Tests

- `tests/context/domains/test_observe_units.py`: keys, switch, retention, ledger and lock (21 tests).
- `tests/context/domains/test_observe_import.py`: import, cursor, correction capture (16 tests).
- `tests/context/domains/test_observe_attribution.py`: packets, verdicts, stubs (10 tests).
