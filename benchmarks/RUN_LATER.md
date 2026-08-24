# Run the benchmark later — quick runbook

**Order matters: enrich first (phase 0), then sweep, then grade, then report.**
Everything is resume-safe — completed work is never repeated or re-paid.

Progress when paused: sweeps stopped mid-run; enrichment not yet started.

---

## 0. Prerequisites (once)

```bash
cd /mnt/windows-ssd/Projects/dummyindex
source .venv/bin/activate
uv pip install datasets nltk
```

Docker, needed only at grading time:

```bash
sudo usermod -aG docker ahmed && newgrp docker   # or log out/in
```

All paid commands require BOTH:
`export DUMMYINDEX_BENCH_ALLOW_PAY=1 DUMMYINDEX_BENCH_KEEP_STREAMS=1`
(omit the env var → every command is a free dry-run planner).

## 1. Phase 0 — enrich every target repo (paid, tracked separately)

```bash
python -m benchmarks enrich --suite both          # free plan: what's pending?
python -m benchmarks enrich --suite both --execute --limit 3   # smoke it
python -m benchmarks enrich --suite both --execute             # full build
```

- Builds the full council-curated `.context/` per unique `(repo, commit)`
  (~72 repos across both suites) via opencode running the real council loop.
- Cost ledger: `results/benchmarks/enrichment/runs.jsonl` — reported as a
  separate one-time "Amortized index-build cost" block, never in per-task metrics.
- Interrupt anytime; rerun resumes from the council frontier.
- Skip already-done repos automatically (`.bi_bench_enriched` marker).

## 2. Sweep both suites (paid)

```bash
setsid nohup bash results/benchmarks/supervise.sh \
  >> results/benchmarks/logs/supervisor.log 2>&1 < /dev/null & disown
```

Supervisor auto-(re)launches each suite until targets are met
(repoqa 720 rows · swebench 100) and exits itself when done.

**Important:** context-arm cells run against the enriched index only for repos
enriched in step 1. Rows record their condition (`index_state`). If you want a
clean all-enriched measurement, first drop stale backbone-era rows:

```bash
python -m benchmarks reset-cells --suite repoqa --arm context --index-state backbone
python -m benchmarks reset-cells --suite swebench --arm context
```

## 3. Monitor

```bash
watch -n30 'wc -l results/benchmarks/*/runs.jsonl 2>/dev/null;
            tail -2 results/benchmarks/logs/supervisor.log'
```

Detail logs: `results/benchmarks/logs/{repoqa,swebench}.log`.

## 4. Grade SWE-bench patches (after swebench hits 100)

```bash
python -m benchmarks grade-swebench \
  results/benchmarks/swebench/preds-swe-main.jsonl swe-main
```

Flatten the harness verdict to `resolved.json` (see §5 input format):
map `{instance_id-arm-rN: true|false}` into one JSON object.

## 5. Final report

```bash
python -m benchmarks report --suite all \
  --resolved results/benchmarks/swebench/resolved.json \
  --out results/benchmarks/REPORT.md
```

Includes per-arm tables, index-condition breakdown, amortized enrichment cost,
and pre-registered gate verdicts (`benchmarks/gates.py`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `--execute requires DUMMYINDEX_BENCH_ALLOW_PAY=1` | export the env vars (top of file) |
| `curated index detected` on ingest | shouldn't happen anymore — enrich flow skips ingest on enriched caches; if seen manually add `--force` |
| Two supervisors running | `pgrep -af supervise.sh`, kill extras **by PID**, keep one |
| Suite died mid-sweep | nothing to do — supervisor restarts + resume-skips |
| `database is locked` retry lines | absorbed by per-cell retries; persistent storms = disk contention from other agents |
