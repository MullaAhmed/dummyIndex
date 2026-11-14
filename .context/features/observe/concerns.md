# Observe: concerns

`confidence: INFERRED`

- No secret redaction. `scan_text` flags only invisible unicode and injection markers (`security.py:14-21`). Credentials in transcript text pass through unredacted.
- Packet text goes to the resolver. `resolution_packet` returns up to 1000 characters of human and assistant text (`attribution.py:21`, `attribution.py:106-110`, `attribution.py:135-151`).
- Raw transcript paths are stored locally. `scan_hosts` writes absolute resolved paths to `.context/cache/evidence-sources.json` (`evidence.py:331`, `evidence.py:400`, `ledger.py:183-188`).
- IDs are not stable across machines. HMAC keys come from `~/.dummyindex/evidence.key` (`keys.py:10`, `keys.py:24`). A new key changes every `keyed_id` value (`keys.py:45-48`).
- Missing key is recreated silently. A deleted key yields a new key on next call (`keys.py:22-42`).
- Key race can disable the feature. A reader may see an empty key file during first creation. `evidence_key` then raises `ValueError`, and `evolution_enabled` returns False (`keys.py:33`, `keys.py:40-41`, `keys.py:60-63`).
- Disabled is silent. `record_exposure` returns 0 and the CLI prints `DISABLED` (`attribution.py:388-389`, `evolve/cli/evolve_probation.py:36-38`).
- Busy lock does not block reads. `resolution_packet` and `record_attribution` raise `LOCK_BUSY` (`attribution.py:25`, `attribution.py:188-190`). Lock-free readers such as `corrections` and `exposures` still run.
- Corrupt ledger blocks all callers. `load` raises on invalid JSON or wrong schema (`ledger.py:57-75`). The message says to preserve and repair it.
- Malformed exposure lines are kept on prune. `_expired_line` returns False for them (`ledger.py:96-101`). They are skipped on read (`ledger.py:134-140`) but never removed.
- Dedupe reads the whole exposure file. `append_exposures` loads every row to build `seen` (`ledger.py:146`). Cost grows with file size.
- Unreadable settings fall back to 30 days silently (`keys.py:74-76`).
- Rows without a string `day` never expire. `_kept` returns True for them (`ledger.py:91-93`).
- Cursor reset rescans. A changed prefix restarts at offset 0 (`importer.py:398-408`). Dedupe by `call` and correction ID limits duplicates (`ledger.py:144-153`, `importer.py:282-283`).
- Candidate set is broad. Every earlier item exposed in the session becomes a candidate (`importer.py:302-312`).
- Correction regex is liberal. Common words such as `instead` can flag a correction (`importer.py:35-38`).
- Tool-result scan has a cap. Only the first 64 KiB per turn is scanned (`importer.py:23`, `importer.py:318-322`).
- Coupling to probation. Probation imports `observe_lock` and `scan_text` directly (`probation/store.py:16`, `probation/rules.py:11`).
- Coupling to the evolve lock names. `project_lock` accepts `observe.lock` by name (`shared/guard.py:42`).
