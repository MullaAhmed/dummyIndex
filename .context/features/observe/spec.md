# Feature: Evolution observation ledger

`confidence: INFERRED`

Local evidence plane for the evolution loop. It records what the agent read, invoked or was injected with. It records when a human corrected the agent. It stores keyed IDs, not raw session IDs. Public API: `dummyindex/evolve/observe/__init__.py:28-49`.

## Behavior

- Ledger file: `.context/cache/evolution/ledger.json`, schema 1 (`ledger.py:17`, `ledger.py:21`).
- Corrupt ledger raises. `load` never resets it silently (`ledger.py:57-75`).
- Exposure log: append-only JSONL at `.context/cache/evolution/exposure.jsonl` (`ledger.py:18`).
- Exposure rows dedupe by `call` (`ledger.py:144-153`). Unparseable lines are skipped on read (`ledger.py:134-140`).
- Retention: `save` prunes rows whose `day` is older than the cutoff (`ledger.py:116-125`).
- Retention window is `cleanupPeriodDays` from `~/.claude/settings.json`, capped at 30 days (`keys.py:67-76`).
- Keys: identifiers are HMAC-SHA256 over canonical JSON (`keys.py:45-48`).
- HMAC key: 32 bytes at `~/.dummyindex/evidence.key`, created once with mode 0600 (`keys.py:10-11`, `keys.py:22-42`).
- Raw session IDs become `session_key` (`keys.py:51-53`). Claude sessions use the transcript file stem (`importer.py:122`).
- Correction IDs use the transcript `uuid`, else timestamp plus text (`importer.py:266-269`).
- Tool-call IDs use the `tool_use` block ID (`importer.py:220`).
- Hostile-text scan: `scan_text` returns `invisible-unicode` or `injection-marker` (`security.py:14-21`).
- The scan is not secret or credential detection. No redaction exists in this package.
- Tool results feed the scan, capped at 64 KiB per turn (`importer.py:23`, `importer.py:314-323`).
- Quarantined corrections never enter a resolution packet (`attribution.py:178-183`).
- Quarantined corrections cannot be attributed (`attribution.py:223-224`).
- Import: `scan_hosts` runs under `observe_lock`, gated by `evolution_enabled` (`evidence.py:372-375`).
- `scan_hosts` budget is 20 s. Overrun sets `complete: false` (`evidence.py:367`, `evidence.py:387-389`). A busy lock returns `skipped: locked` (`evidence.py:377`).
- Claude transcripts use `import_claude`. Codex JSONL uses generic `_jsonl`. Codex SQLite import runs only when complete (`evidence.py:339-354`, `evidence.py:397-398`).
- Import resumes from a cursor. The cursor fingerprints the first 4096 bytes (`importer.py:398-408`, `importer.py:139-144`).
- A partial last line is not consumed (`importer.py:424-426`).
- Sidechain rows are skipped (`importer.py:180`).
- Sessions with another project `cwd`, or origin `learning` or `evolve`, are skipped (`importer.py:411-417`).
- Correction: human text matching the correction regex outside quoted spans (`importer.py:35-39`, `importer.py:59-61`).
- Correction candidates: items exposed earlier in the same session (`importer.py:302-312`).
- Exposure: `Read` on a convention, feature, playbook or equipment file, or a `Skill` call (`importer.py:40`, `importer.py:339-350`).
- `resolution_packet` returns the oldest open, unquarantined correction with candidates (`attribution.py:186-191`).
- Packet text is truncated to 1000 characters (`attribution.py:21`).
- Verdicts: `attributed`, `unrelated`, `unknown` (`attribution.py:24`).
- Only `attributed` takes an item. The item must be a candidate (`attribution.py:210-226`).
- Each recorded verdict resolves its correction (`attribution.py:259`).
- A correction whose transcript is gone becomes `expired` (`attribution.py:168`).
- `observe_lock` yields True when held, re-entrant in process. It yields False when busy (`ledger.py:191-215`).
- Busy writers raise `LOCK_BUSY` (`attribution.py:277`) or return 0 (`attribution.py:391-392`).
- Kill switch: `DUMMYINDEX_EVOLUTION` set to `0`, `off` or `false` disables (`keys.py:12-13`, `keys.py:56-61`).
- `evolution_enabled` also returns False when the evidence key is unusable (`keys.py:60-63`).
- Evidence stub: `commit_evidence_stub` writes `.context/gc/evidence/<id>.json` (`attribution.py:22`, `attribution.py:335-352`).
- The stub holds only `schema_version`, `id`, `host`, `kind`, `day` and `detector` (`STUB_SCHEMA = 2`, `attribution.py:23`, `attribution.py:343-350`).

## Boundaries

- `evolution` feature: owns `evidence.py`, which drives import and `expose_case`. It imports this package (`evidence.py:24-41`).
- `evolution` also owns the `observe.lock` name in `project_lock` (`shared/guard.py:42`).
- `probation` feature: reads `corrections` and `exposures` (`probation/sync.py:87-88`, `probation/actions.py:21`).
- `probation` writes under `observe_lock` (`probation/store.py:95`, `probation/sync.py:74`).
- `probation` records exposures and checks the switch (`probation/render.py:52`, `probation/render.py:86`).
- `probation` reuses `scan_text` (`probation/rules.py:11`).
- CLI: `evolve attribute` calls `resolution_packet` and `record_attribution` (`evolve/cli/evolve_probation.py:45`, `evolve/cli/evolve_probation.py:65`).
- CLI: disabled output is `DISABLED` and exit 0 (`evolve/cli/evolve_probation.py:10`, `evolve/cli/evolve_probation.py:36-38`).

## Tests

- `tests/evolve/test_observe_units.py`: keys, kill switch, ledger, retention, lock.
- `tests/evolve/test_observe_import.py`: cursor, sidechain, skipped sessions, correction capture.
- `tests/evolve/test_observe_attribution.py`: packets, verdict rules, expiry, stubs.
