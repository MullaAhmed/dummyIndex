# Observe: concerns

`confidence: INFERRED`

- No secret redaction. `scan_text` flags only invisible unicode and injection markers (`security.py:14-21`). Credentials in transcript text pass through unredacted.
- Packet text goes to the resolver. `resolution_packet` returns up to 1000 characters of human and assistant text (`attribution.py:19`, `attribution.py:104-108`, `attribution.py:133-149`).
- Raw transcript paths are stored locally. `scan_hosts` writes absolute resolved paths to `.context/cache/evidence-sources.json` (`evidence.py:331`, `evidence.py:400`, `ledger.py:182-187`).
- IDs are not stable across machines. HMAC keys come from `~/.dummyindex/evidence.key` (`keys.py:10`, `keys.py:24`). A new key changes every `keyed_id` value (`keys.py:45-48`).
- Missing key is recreated silently. A deleted key yields a new key on next call (`keys.py:22-42`).
- Key race can disable the feature. A reader may see an empty key file during first creation. `evidence_key` then raises `ValueError`, and `evolution_enabled` returns False (`keys.py:33`, `keys.py:40-41`, `keys.py:60-63`).
- Disabled is silent. `record_exposure` returns 0 and the CLI prints `DISABLED` (`attribution.py:386-387`, `cli/evolve_probation.py:36-38`).
- Busy lock does not block reads. `resolution_packet` and `record_attribution` raise `LOCK_BUSY` (`attribution.py:23`, `attribution.py:186-188`). Lock-free readers such as `corrections` and `exposures` still run.
- Corrupt ledger blocks all callers. `load` raises on invalid JSON or wrong schema (`ledger.py:56-74`). The message says to preserve and repair it.
- Malformed exposure lines are kept on prune. `_expired_line` returns False for them (`ledger.py:95-100`). They are skipped on read (`ledger.py:133-139`) but never removed.
- Dedupe reads the whole exposure file. `append_exposures` loads every row to build `seen` (`ledger.py:145`). Cost grows with file size.
- Unreadable settings fall back to 30 days silently (`keys.py:74-76`).
- Rows without a string `day` never expire. `_kept` returns True for them (`ledger.py:90-92`).
- Cursor reset rescans. A changed prefix restarts at offset 0 (`importer.py:397-407`). Dedupe by `call` and correction ID limits duplicates (`ledger.py:143-152`, `importer.py:281-282`).
- Candidate set is broad. Every earlier item exposed in the session becomes a candidate (`importer.py:301-311`).
- Correction regex is liberal. Common words such as `instead` can flag a correction (`importer.py:34-37`).
- Tool-result scan has a cap. Only the first 64 KiB per turn is scanned (`importer.py:22`, `importer.py:317-321`).
- Coupling to probation. Probation imports `observe_lock` and `scan_text` directly (`probation/store.py:14`, `probation/rules.py:10`).
- Coupling to the evolve lock names. `project_lock` accepts `observe.lock` by name (`evolve_promotion.py:24`).
