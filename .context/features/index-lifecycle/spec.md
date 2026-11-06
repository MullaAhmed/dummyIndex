# Index lifecycle and coverage

Build portable navigation from source and repair it without discarding authored context.

- The saved scan scope is distinct from the output root. Refresh and reconciliation honor it; disjoint roots and linked managed destinations fail before writes.
- Maps and tree topology reflect current source. Authored annotations survive, with `source-stale` labels when source hashes change. Mechanical PROJECT/architecture sections refresh; other notes survive.
- Naming Markdown summarizes rules and exception counts; the linked `naming.json` retains complete exception evidence instead of repeating it in the reading path.
- `coverage.json` lists each detected source file, symbol count, owners, file-only reasons and excluded paths. Pending/unowned work remains visible.
- Graph paths and filename-derived IDs are repository-relative. Large symbol graphs use a validated manifest and content-addressed shards, each at most 1,000,000 bytes. The shared reader also accepts legacy JSON.
- Reconciliation retains the old anchor until ownership and review are complete. An absent anchor requires a full scoped inventory and an explicit reviewed replacement commit.

Sources: `dummyindex/context/build/`, `dummyindex/export/storage.py`, `dummyindex/pipeline/io/detect.py`.
