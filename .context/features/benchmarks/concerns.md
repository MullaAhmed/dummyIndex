# Concerns — benchmarks

## Security

- `benchmarks/runner.py:66-82,151-153` — `--auto` agent over untrusted cloned repos inherits full host env (`dict(os.environ)`): one shell command exfiltrates every provider key on the host — none. Mitigation is cheap: provider auth comes from the copied `auth.json` (`runner.py:144-150`), so scrubbing credential-shaped env keys breaks nothing and makes the "sandboxed" docstring (`runner.py:18-22`) true.
- `benchmarks/arms.py:276-295` — workspace reuse keyed arm+commit+repeat omits task identity and returns prior cells' agent-written artifacts untouched (planted hooks, edited sources); baseline strip removes only `.context/` (`arms.py:310-311`) — cross-cell injection persistence into measured runs — none.
- `benchmarks/enrich.py:208-235` + `benchmarks/arms.py:306-326` — `.bi_bench_enriched` marker existence alone flips enriched-context inheritance; no provenance/integrity gate before `materialize_workspace` copies the shared clone — one hallucinated council edit silently biases every context-arm cell, arm-asymmetrically, while REPORT.md presents it as measured treatment.
- `benchmarks/runner.py:133-150,289-290` — real `auth.json` staged under `/tmp/bi-bench-sandbox/run-*`; crash residue persists past SIGKILL/power loss — hygiene fix: `tempfile.mkdtemp()` (0700). Co-located-read window assessed theoretical on single-maintainer hardware.
- `benchmarks/arms.py:127-156` — dataset-controlled `repo`/`commit` reach git argv (list-form, no shell) and cache paths; needs `-`-leading commit or slash/dot metadata to escape — input-validation TODO, not live threat while inputs are hex shas from curated sets.
- `benchmarks/scoring/swegrade.sh:40-49` — `RUN_ID` interpolated into `OUT_DIR` unvalidated — developer-error class only (same-user CLI, sane default `__main__.py:699-700`); Docker-socket execution of model patches is the documented purpose of the official harness.
- `pyproject.toml:81-86` vs `tests/benchmarks/*` — `benchmark_smoke` strict marker registered but applied by zero tests; spend safety rests entirely on the fail-closed double pay-gate (`__main__.py:142-144,255`, `runner.py:224-229`, `PayGateError` non-retryable `__main__.py:171-175`) — those gates are load-bearing.
- `benchmarks/__main__.py:169-194` — `_resilient_cell` retries systematic config failures 3× across the matrix — errors triple spend instead of failing fast on first identical error.

## Product surface

- Silent child hang ⇒ unbounded wall time AND stranded credential-bearing sandbox: `for line in lines` has no timeout (`runner.py:242-244`), `--timeout-s` bounds only post-EOF wait (`runner.py:256-258`), undrained `stderr=PIPE` can deadlock at ~64KB (`runner.py:165-173`), and `proc.kill()` spares grandchildren — merges security+product first-pass findings; top severity.
- Any `executed=False` row (dry-run planned OR failed error row) permanently suppresses its cell on paid resume: `append_row` fires regardless of execute (`__main__.py:316`), `_done_cells` accepts any well-formed row ignoring `executed`/`error` (`__main__.py:126-139`); `reset-cells` cannot target error rows alone — published numbers present holes as measurements unless manual reset discipline is followed.
- Ctrl-C during `--workers>1` sweep still drains queued cells (up to 1800s each): KeyboardInterrupt hits main thread blocked in `pool.map`, `shutdown(wait=True)` with no cancellation (`__main__.py:236-237`) — voids pay-gate discipline exactly when a human intervenes to stop spend.
- Interrupted swebench sweep loses completed cells' patches (in-memory list written once at end, `__main__.py:361-436`); re-running finished sweep truncates good preds via `"w"`-mode `write_predictions([])` (`swebench.py:141-147`); suffixed `{instance_id}-{arm}-r{repeat}` ids fed verbatim to official harness expecting raw ids (`swegrade.sh:43-49`) — undefined grading path.
- Re-invoking completed `run-repoqa --execute` clobbers REPORT.md with n=0 tables + spurious GATE FAILURE verdict, exit code 0 (`__main__.py:337-340`).
- Gates attach PASS/FAIL labels to partial matrices with no completeness marker (`report.py:235-244`).
- RUN_LATER promises amortized-enrichment section in final report; `cmd_report` never reads the enrichment ledger (`__main__.py:554-555`) — code wins over doc.
- README/module docstring promise dry-run argv printing; argv lands only inside runs.jsonl rows (`__main__.py:9-10`, README.md:113) — code wins.
- `plan` subcommand fixes the matrix via `set_defaults`, exposes no override flags (`__main__.py:592-612`); repoqa dataset-load failure prints to stderr while stdout reports a confident swebench-only total (`__main__.py:97-100,114`).
- Unbounded disk growth: one checkout per (repo, commit, arm, repeat) plus ~72 full clones, never GC'd (`arms.py:276-304`); `DUMMYINDEX_BENCH_KEEP_STREAMS=1` accrues raw streams per paid cell with no prune tooling (RUN_LATER.md:25 vs `runner.py:303-304`).
- `reset-cells` without `--arm/--index-state` drops everything; single `.jsonl.bak` overwritten each invocation (`__main__.py:531-540`) — one typo erases both arms' history.
- `enrich --execute` full build: ~72 repos × up to 200 rounds × cap 4 paid calls with no cost pre-flight; skipped-DONE agents silently re-dispatched (`__main__.py:484-500`, `enrich.py:171-240`) — spend ceiling invisible until ledger fills.
- `_staggered_start` serializes every cell start behind one lock at 1/3s (~84s cumulative startup at workers≥8) — undocumented next to `--workers` (`__main__.py:229,241-247`).
- Progress output for multi-hour sweeps: anonymous dots sequential, one line per 10 completions parallel (`__main__.py:216-234`).
- `swebench.workspace_for_task` guaranteed AttributeError on first call; zero callers/tests (`swebench.py:138,150-167`).
- Backlog: unmapped exceptions escape exit-code mapping as tracebacks (`__main__.py:576-582,701-708`).

(critic-database pruned by deep-mode manual-rerun relevance rules: no sql/migrations/models/schema files)
