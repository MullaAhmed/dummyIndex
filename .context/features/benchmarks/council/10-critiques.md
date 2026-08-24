# Raw critic findings — benchmarks (stage 3, first pass)

## critic-security

- `benchmarks/runner.py:66-82,151-153` — agent runs `--auto` over untrusted cloned repos with full inherited env; prompt injection can exfiltrate keys / exec commands — no env scrubbing or egress control.
- `benchmarks/runner.py:133-150,289-290` — real `auth.json` copied into `/tmp/bi-bench-sandbox/run-*` under 1777 `/tmp`, cleanup best-effort — co-located credential read window; crash-persistent residue.
- `benchmarks/arms.py:127-130,147-156` — dataset-controlled `commit`/slug flow unvalidated into `git checkout --detach` and cache paths; unpinned gzip download, override path — path escape / git option injection.
- `benchmarks/scoring/swegrade.sh:40-49` — `RUN_ID` interpolated into `OUT_DIR` unvalidated; wrapper feeds model patches to official harness on host Docker socket with zero gating.
- `benchmarks/runner.py:240-258` — timeout only bounds post-EOF wait; hung child blocks worker forever; stderr=PIPE deadlock risk pins credential-bearing sandbox.
- `benchmarks/enrich.py:208-235` + `arms.py:218-220,309-325` — enrichment agents write shared cache clone; `.context/` inherited verbatim on marker existence — cache poisoning propagates to measured workspaces.
- `pyproject.toml:81-86` vs tests — `benchmark_smoke` marker claimed but unused; spend safety rests solely on the double pay-gate (verified fail-closed).
- `benchmarks/__main__.py:126-139,299-316,407` — dry-run rows enter runs.jsonl; `_done_cells` ignores `executed`; paid sweep silently skips them; REPORT.md presents holes as measurements.

Top 3 threats: (1) `--auto` + full env over untrusted repos; (2) auth.json staged under world-traversable /tmp; (3) unvalidated repo/commit reaching git argv + cache paths from unpinned supply chain.

## critic-product

- Two needles share one workspace keyed by arm+commit (`arms.py:276-295`) — cells not independent despite docstring claim (`__main__.py:202-204`); `--workers>1` rmtree race on live workspaces.
- Ctrl-C during parallel sweep still executes queued cells (up to 1800s each) — interrupt keeps spending (`__main__.py:236-237`).
- `--timeout-s` does not bound wall time for silent child hangs (`runner.py:242-250`).
- Interrupted swebench sweep loses completed cells' patches; re-run overwrites good preds with empty file (`__main__.py:361-436`; `swebench.py:141-147`).
- Error rows counted as done by `_done_cells` — transient failures permanently skipped by resume (`__main__.py:126-139,185-193`); reset-cells can't target error rows alone.
- Re-invoking completed `--execute` clobbers REPORT.md with n=0 tables + spurious GATE FAILURE, exit 0 (`__main__.py:337-340`).
- RUN_LATER promises amortized-enrichment section in final report; cmd_report never reads enrichment ledger (`__main__.py:554-555`) — code wins.
- README/module docstring promise dry-run argv printing; argv lands only in runs.jsonl (`__main__.py:9-10`, README.md:113) — code wins.
- `plan` subcommand hardcodes matrix, ignores parsed flags; dataset-load failure demoted to stderr while stdout prints confident total (`__main__.py:592-612,97-100`).
- Predictions named `{instance_id}-{arm}-r{repeat}` fed verbatim to official harness expecting raw ids — undefined grading path (`__main__.py:400-403`, swegrade.sh:43-49).
- Gates render PASS/FAIL verdicts over partial matrices with no completeness marker (`report.py:235-244`).
- Unmapped exceptions escape main()'s exit-code mapping as raw tracebacks (`__main__.py:576-582,701-708`).
- `_staggered_start` serializes every cell start behind one lock at 1/3s — undocumented throughput cap (`__main__.py:229,241-247`).
- Near-zero progress output for multi-hour sweeps; dots only (`__main__.py:216-234`).
- Unbounded disk growth: per-cell checkouts + ~72 clones + KEEP_STREAMS accrual, no GC tooling (`arms.py:276-304`, RUN_LATER.md:25).
- `reset-cells` without filters drops everything; single overwritten .bak — one typo erases history (`__main__.py:531-540`).
- `swebench.workspace_for_task` guaranteed AttributeError on first call; zero callers/tests (`swebench.py:138,150-167`).
- `enrich --execute` full build has no cost pre-flight; skipped-DONE agents silently re-dispatched up to rounds cap (`__main__.py:484-500`, enrich.py:171-240).

(critic-database pruned by deep-mode manual-rerun relevance rules: no sql/migrations/models/schema files)
