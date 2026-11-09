# Evolution limits

- The external executor/evaluator is trusted to run the stated model, grade independently and reserve token/cost allowance first. Identity, coverage, controls and accounting are checked; provider billing is not.
- Timeouts and output overflow kill process trees. Polled output: short bursts can exceed receipt limit.
- Unsupported SQLite schemas fail without moving cursors. JSONL-only discovery misses Codex database rows.
- Scans stop at 20 s, reporting `complete: false`; retry resumes.
- Captured guidance bytes are a size proxy that breaks ties last.
- Correction capture is a regex prefilter; it only records. Attribution needs the host LLM resolver. Codex corrections stay unattributable.
- Exposure covers only `Read`/`Skill` calls and loader injections. Hostile-text scan covers tool results (`observe/importer.py:322`).
- Local evidence in `.context/cache/evolution/` expires with host transcripts and retention. Human-correction learning waits for probation; closeout continues.
- Lesson `confidence` and verdicts are unmeasured claims. Legacy-shape reflections pass with a warning.
- Case identities and ancestry must be honest. Held-out fixtures are absent from development snapshots; undeclared prior exposure cannot be undone.
- Utility cannot prove one rule caused a result. Suspect versions are repair signals, not deletion orders.
- Native workspaces are no OS sandbox. Hosts deliver only prepared tasks and guidance. They keep evaluator and held-out content out of authoring. They persist dispatch IDs and interrupt workers at the deadline.
- Resource caps need host telemetry; missing usage stops continuation. Snapshots cap: 64 MB, 10,000 files.
</content>
