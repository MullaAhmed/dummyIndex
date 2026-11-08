# Evolution implementation

- `context/domains/evolve.py` harvests evidence and validates at most five
  candidates of at most five allowed guidance targets. Python, evaluator state
  and feature specs remain outside its mutation scope.
- `evolve_gate.py` captures current dirty inputs, runs the same project tests in
  baseline/candidate copies and binds receipts to exact bytes and check profile.
  `evolve_promotion.py` owns locks, backups, transaction recovery and rollback.
- `evidence.py` normalizes host records, persists incremental cursors, keeps
  local-path lookup in ignored cache and enforces durable split ancestry.
- `living_rules.py` plans protected rule replacement/supersession and reports
  source-digest staleness; it never adopts planned bytes directly.
- `evolve_learning.py` validates reflections with `lesson/`, maps them through
  `lesson_to_delta`, and stages one convention candidate per accepted reflection.
  It uses the existing gate/promotion path. `learning_status` derives the stored
  status; `mark_failed` persists errors. Processing is idempotent.
- `evolve_experiments.py` executes the fixed external command, validates per-case
  controls and exact guidance loads, retains compact receipts and per-version
  utility, and keeps current/best pointers. Quality leads selection; equal
  outcomes prefer lower cost, tokens, then controller-measured guidance bytes.
  Valid terminal receipts prevent identical failed trials from spending again.
  Defaults: six stages, 120 seconds, 20,000 reported tokens, $2 reserved cost,
  two non-improving probes and zero infrastructure retries. Unknown spending stops.
- `cli/evolve.py` exposes evidence, learning (one status line on stderr), rule
  status, experiment and utility alongside harvest/diagnose/apply/promote/rollback/discard.
- `evolve_native.py` fixes native phase ordering and recommendations;
  `evolve_native_snapshot.py` captures bounded immutable inputs/artifacts and
  runtime identity, while `evolve_native_response.py` validates responses before
  writes. Host agents perform each action once; interrupted writes need inspection.

Domain tests use constructed host stores, real SQLite reads, isolated pytest
arms and an external fixture process. External replay uses an explicit trusted
executor command. Native replay uses the active host and installed
`native-protocol.md`; neither adds a paid daemon to ordinary post-task learning.
