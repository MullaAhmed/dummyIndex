# Evolution limits

- The external executor/evaluator is trusted to run the stated model, grade
  artifacts independently and reserve the requested token/cost allowance before
  paid calls. Identity, case coverage, controls and returned accounting are
  checked; provider billing cannot be independently inspected here.
- Process groups/trees are terminated on timeout or output overflow. Output
  growth is polled, so a short burst can exceed the receipt limit before exit.
- Host schemas vary. Unsupported SQLite schemas fail explicitly without moving
  cursors. JSONL-only discovery is not complete Codex database coverage.
- Text classification is conservative, not semantic proof. Human correction
  evidence gets one reflection; speculative audit prose never becomes a rule
  directly. Verified reflections still need review and checks.
- Lesson `confidence` and edit verdicts are author claims, not stored or measured.
  Legacy-shape reflections pass with a warning.
- Case identities and ancestry must be supplied honestly. Held-out fixture files
  are absent from development snapshots; undeclared prior exposure cannot be
  undone.
- Utility cannot prove that one rule
  caused a result. Suspect versions are repair signals, not deletion orders.
- Captured guidance bytes are only a size proxy. They break ties last.
- Native workspaces are not an OS sandbox. Hosts must deliver only the prepared
  task and guidance, keep evaluator/held-out content out of authoring, persist
  dispatch IDs and interrupt workers at the fixed deadline. Numeric resource caps
  cannot be promised without host telemetry/reservation; missing capped usage
  stops continuation. Snapshot limits are 64 MB and 10,000 files.
