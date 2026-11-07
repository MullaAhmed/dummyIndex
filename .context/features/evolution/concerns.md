# Evolution limits

- The external executor/evaluator is trusted to run the stated model, grade
  independently and reserve token/cost allowance first. Identity, coverage,
  controls and accounting are checked; provider billing is not visible here.
- Timeouts and output overflow kill process trees. Output is polled, so a short
  burst can exceed the receipt limit.
- Unsupported SQLite schemas fail without moving cursors. JSONL-only discovery
  misses Codex database rows.
- Correction capture is a regex prefilter; it records, never decides.
  Attribution needs the host LLM resolver. Codex corrections stay
  unattributable.
- Exposure covers only `Read`/`Skill` calls and loader injections. Their results
  skip the hostile-text scan.
- Local evidence in `.context/cache/evolution/` expires with host transcripts
  and retention. Human-correction learning waits for probation; closeout
  learning continues.
- Lesson `confidence` and verdicts are unmeasured author claims. Legacy-shape
  reflections pass with a warning.
- Case identities and ancestry must be honest. Held-out fixtures are absent from
  development snapshots; undeclared prior exposure cannot be undone.
- Utility cannot prove one rule caused a result. Suspect versions are repair
  signals, not deletion orders.
- Captured guidance bytes are a size proxy that breaks ties last.
- Native workspaces are not an OS sandbox. Hosts must deliver only the prepared
  task and guidance, keep evaluator and held-out content out of authoring,
  persist dispatch IDs and interrupt workers at the deadline. Resource caps need
  host telemetry; missing capped usage stops continuation. Snapshots cap at
  64 MB and 10,000 files.
