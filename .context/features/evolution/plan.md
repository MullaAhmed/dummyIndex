# Evolution implementation

- `context/domains/evolve.py` harvests evidence and validates at most five
  candidates of at most five allowed targets. Python, evaluator state and feature
  specs stay outside its mutation scope.
- `evolve_gate.py` runs project tests on baseline/candidate copies and binds
  receipts to exact bytes. `evolve_promotion.py` owns locks, backups, recovery, rollback.
- `evidence.py` normalizes host records, persists cursors, keeps local-path lookup in cache.
- `living_rules.py` plans protected rule replacement and reports source-digest staleness.
- `evolve_learning.py` validates reflections with `lesson/`, stages one convention
  candidate per accepted reflection, and derives `learning_status`. `chat:` runs
  stage under `.context/cache/evolution/runs/`; a passing gate calls
  `probation.actions.enter` and writes no `evolution.jsonl` event.
- `probation/`: `enums` (states, route tiers), `constants` (uncalibrated thresholds),
  `models` (frozen `Item` with append-only history), `store` (cache JSON, locked),
  `rules` (pure route, followed-check, eligibility), `sync` (counters, harm, drift,
  expiry, seeding), `render` (session block, yield report), `actions` (enter, promote, demote via gate).
- `evolve_experiments.py` runs the fixed external command, validates per-case controls
  and guidance loads, keeps compact receipts and per-version utility. Quality leads;
  equal outcomes prefer lower cost, tokens, then guidance bytes. Defaults: six stages,
  120 seconds, 20,000 tokens, $2 reserved, two non-improving probes, zero
  infrastructure retries. Unknown spending stops. Valid terminal receipts stop
  identical failed trials from spending again.
- `cli/evolve.py` exposes evidence, learning, rules, experiment, utility, attribute and
  probation alongside harvest/diagnose/apply/promote/rollback/discard.
- `cli/memory.py` `session-start` prints the probation block after the memory block.
- `evolve_native.py` fixes native phase ordering; `evolve_native_snapshot.py` and
  `evolve_native_response.py` pin inputs and validate responses before writes.

Domain tests use constructed host stores, real SQLite reads and isolated pytest
arms. Native replay uses the active host and `native-protocol.md`; neither adds a
paid daemon to post-task learning.
