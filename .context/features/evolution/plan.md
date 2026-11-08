# Evolution implementation

- `context/domains/evolve.py` harvests evidence and validates at most five candidates of at most five targets. Python, evaluator state and feature specs stay outside mutation scope.
- `evolve_gate.py` runs project tests on baseline and candidate copies, binding receipts to exact bytes. `evolve_promotion.py` owns locks (`evolve.lock`, `replay.lock`, `observe.lock`), backups, recovery and rollback.
- `evidence.py` keeps committed exposure in `.context/gc/evidence.json`. Host import, ledger and scans live in `observe/` (see `observe` feature).
- `living_rules.py` plans protected rule replacement and reports source-digest staleness.
- `evolve_learning.py` validates reflections with `lesson/`, stages one convention candidate per reflection and derives `learning_status`. `chat:` runs stage under `.context/cache/evolution/runs/`; a passing gate calls `probation.actions.enter` and writes no `evolution.jsonl` event.
- `probation/` holds `enums` (states, route tiers) and `constants` (uncalibrated thresholds).
- `models`: frozen `Item`, append-only history. `store` keeps cache JSON, locked.
- `rules` routes items, checks followed rules and eligibility. `sync` runs counters, harm, drift, expiry and seeding.
- `render` builds session and yield blocks. `actions` enters, promotes and demotes through the gate.
- `evolve_experiments.py` runs the fixed external command, validates per-case controls, guidance loads, keeps receipts with per-version utility. Defaults: six stages, 120 seconds, 20,000 tokens, $2 reserved, two non-improving probes, zero infrastructure retries. Unknown spending stops.
- `cli/evolve.py` exposes evidence, learning, rules, experiment, utility, attribute and probation beside harvest, diagnose, apply, promote, rollback and discard. `cli/evolve_probation.py` implements `attribute` and `probation`.
- `cli/memory.py` `session-start` prints the probation block.
- `evolve_native.py` fixes native phase order. `evolve_native_snapshot.py` and `evolve_native_response.py` pin inputs and validate responses before writes.

Domain tests use constructed host stores, real SQLite reads and isolated pytest arms. Native replay uses the active host and `native-protocol.md`; no paid daemon.
