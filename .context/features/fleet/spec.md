# Fleet orchestration

Checkpoint parallel proposal work and resumable feature maintenance.

`dummyindex/context/domains/fleetrun.py` owns multi-proposal runs: explicit units, path disjointness, bounded parallelism, checkpoints and budget halts. In-flight units hold paths and slots (`fleetrun.py:860`). Host launches the work; CLI stores state. Corrupt run state fails with repair instructions rather than redispatching completed work.

`dummyindex/context/domains/fleet.py` owns feature-maintenance runs, using council stage order and persisted completion. Maintain (`maintain-<ts>`) and proposal (`run-<id>`) runs use distinct namespaces under `.context/fleet/`.

`dummyindex/cli/fleet.py` is the proposal-run interface; `dummyindex/cli/maintain.py` drives maintenance. Budget/ETA counters are bookkeeping, not guarantees of runtime or quality.
