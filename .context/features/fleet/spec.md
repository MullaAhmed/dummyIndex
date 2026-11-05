# Fleet orchestration

Checkpoint parallel proposal work and resumable feature maintenance.

`dummyindex/context/domains/fleetrun.py` owns multi-proposal runs: explicit units, path disjointness, bounded parallelism, checkpoints and budget halts. The host launches the work; the deterministic CLI stores its state. Corrupt run state fails with repair instructions rather than redispatching completed work.

`dummyindex/context/domains/fleet.py` owns feature-maintenance runs, using council stage order and persisted unit completion. Maintenance run names and proposal-run names occupy distinct namespaces under `.context/fleet/`.

`dummyindex/cli/fleet.py` is the proposal-run interface; `dummyindex/cli/maintain.py` drives maintenance. Budget/ETA counters are bookkeeping, not a guarantee of agent runtime or output quality.
