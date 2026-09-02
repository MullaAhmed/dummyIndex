# Benchmark harness — plan

`confidence: INFERRED`

## Where it lives

- `benchmarks/` — the package root:
  - `benchmarks/__init__.py` — version constant and `PAY_GATE_ENV` name (benchmarks/__init__.py:33-35).
  - `benchmarks/__main__.py` — CLI: parser, all six command functions, cell orchestration, retry/parallelism, exit-code mapping (benchmarks/__main__.py:585-712).
  - `benchmarks/arms.py` — arm enum, AGENTS.md rendering, pinned clones, workspace materialization, marker state (benchmarks/arms.py:39-343).
  - `benchmarks/runner.py` — opencode transport, pay gate, sandboxes, JSONL append (benchmarks/runner.py:41-325).
  - `benchmarks/telemetry.py` — tolerant stream/export parsers into `RunMetrics` (benchmarks/telemetry.py:33-234).
  - `benchmarks/enrich.py` — phase-0 council loop driver (benchmarks/enrich.py:41-298).
  - `benchmarks/gates.py` — pre-registered thresholds and evaluation (benchmarks/gates.py:32-129).
  - `benchmarks/report.py` — aggregation, dedupe, amortized-cost section, markdown rendering (benchmarks/report.py:28-255).
- `benchmarks/suites/` — task sources: `repoqa.py`, `swebench.py`; shared `SuiteDataError` in `suites/__init__.py` (benchmarks/suites/__init__.py:6-8).
- `benchmarks/scoring/` — graders: `snf.py`, `snf_official.py`, `swebench_patch.py`, plus the bash wrapper `swegrade.sh`.
- `tests/benchmarks/` — offline deterministic unit tests; `fixtures/opencode_stream.jsonl` pins the telemetry shape (tests/benchmarks/fixtures/opencode_stream.jsonl).
- Runtime artifacts live outside the package under gitignored `results/benchmarks/**`.

## Architecture in three sentences

`__main__.py` orchestrates everything: it converts CLI args into per-cell closures around `runner.run_one_task`, which shells out to `opencode run --format json --auto --pure` inside a per-run XDG sandbox, funnels stdout through `telemetry.metrics_from_stream`, and appends one row per cell via `append_row`. Suite adapters (`suites/repoqa.py`, `suites/swebench.py`) own dataset loading, seeded stratified subsets, prompt construction, and workspace preparation delegated to `arms.prepare_arm_workspace`; scoring modules grade finished work as pure functions (`snf.py`, `snf_official.py`) or by handing patches to the external dockerized harness (`swebench_patch.py` + `swegrade.sh`). Cross-cutting consumers stay leaf-level and pure — `report.aggregate/load_rows/render_report` derive summaries from rows and feed `gates.evaluate_gates`, while `enrich.Enricher` reuses the same runner and arms primitives to build enriched caches before any sweep.

## Data model

No database; the ledger is append-only JSONL plus markers on disk.

- `results/benchmarks/<suite>/runs.jsonl` — one sorted-key JSON object per cell (benchmarks/runner.py:318-325). Row identity: `suite, arm, task_id, repeat_index, workspace, prompt_sha256, wall_time_s, executed` (+ metrics or argv per executed flag) (benchmarks/runner.py:99-115); suite extras `protocol/index_state/passed/best_similarity` (benchmarks/__main__.py:299-316) and terminal `error` rows (benchmarks/__main__.py:185-194). Consumers keep only the latest row per `(arm, task_id, repeat_index)` (benchmarks/report.py:99-116); `reset-cells` rewrites this file with a `.jsonl.bak` backup (benchmarks/__main__.py:522-542).
- `results/benchmarks/enrichment/runs.jsonl` — cost ledger keyed `suite="enrichment"`, `arm="council"` with an `enrich_unit` payload (benchmarks/enrich.py:9-12, 213-235).
- `results/benchmarks/swebench/preds-{run_id}.jsonl` — official-harness predictions, `instance_id = "{task}-{arm}-r{repeat}"` + `model_patch` (benchmarks/suites/swebench.py:141-147; benchmarks/__main__.py:397-406, 430-436).
- Markers encoding workflow state: `.git/BI_BENCH_PINNED` (clone complete, holds commit), `.bi_bench_enriched` (JSON `{mode, units}`), `.bi_bench_ready` (`"{arm}:{commit}:indexed=N:mode=M"`) (benchmarks/arms.py:150-156, 214-215, 281-329).
- Cache/workspace trees: shared clones at `cache/repos/{slug}-{commit[:12]}` (benchmarks/arms.py:127-130); arm workspaces `{slug}-{commit}-{arm}[-r{repeat}]` under `results/benchmarks/workspaces/` (benchmarks/arms.py:276-279); optional raw stream dumps under `<suite>/streams/` (benchmarks/runner.py:293-315); RepoQA dataset cache `results/benchmarks/cache/repoqa/repoqa-{version}.json` (benchmarks/suites/repoqa.py:53, 136-138); rendered reports `REPORT.md` / `ENRICHMENT.md`; grading reports under `results/benchmarks/swebench/{run_id}/` (benchmarks/scoring/swegrade.sh:40-49).

## Key decisions

1. **Double pay gate** — spending requires `--execute` AND `DUMMYINDEX_BENCH_ALLOW_PAY=1`, enforced redundantly at CLI dispatch, in each command, and inside `run_one_task` itself so library callers cannot bypass it (benchmarks/__main__.py:142-144; benchmarks/runner.py:224-229). Rejected: env-var-only or flag-only gating (either alone admits accidental spend).
2. **Shared-base / single-delta AGENTS.md** — both arms share byte-identical `NEUTRAL_BASE`; the context arm appends exactly one navigation section; the file is written last so ingest bootstrap cannot contaminate the delta (benchmarks/arms.py:58-105, 327-329). Whole-file-per-arm replacement was explicitly rejected as a past mistake that turned measurement into ablation (benchmarks/arms.py:6-10).
3. **Enrich-once inheritance with stamped provenance** — the context arm inherits an enriched cache verbatim (never re-ingesting curated work); without enrichment it ingests a backbone; every row records `index_state` so backbone-era and enriched-era measurements stay separable, and `reset-cells` drops stale-condition rows (benchmarks/arms.py:309-325; benchmarks/__main__.py:515-543). The baseline arm always has `.context/` stripped post-copy.
4. **Cost accounting split** — enrichment calls flow through the standard runner under `suite="enrichment"` into their own ledger, surfaced by report only under the `"__enrichment__"` key as an amortized-cost section that gates never see (benchmarks/enrich.py:9-12, 230-235; benchmarks/report.py:174-180, 235).
5. **Never reimplement official grading where it matters** — RepoQA's function protocol is a faithful BLEU port with two documented divergences (modern grammar wheels instead of the legacy bundle; loud failure on query-compilation errors) (benchmarks/scoring/snf_official.py:17-27); SWE-bench grading is outsourced entirely to the dockerized harness behind a thin auditable wrapper (benchmarks/scoring/swegrade.sh:2-9). The `name` protocol keeps the substring rule unnormalized for leaderboard comparability (benchmarks/scoring/snf.py:3-10).
6. **Tolerant telemetry with anti-double-count rules** — unknown event shapes never crash parsing; usage dedupes per message id (last wins) and anonymous observations take the largest single value rather than a sum; cost takes the cumulative max; tool wrappers without names are not counted (benchmarks/telemetry.py:14-24, 133-176). Zero-event streams are hard `RunnerError`s so a broken transport can never masquerade as an arm result (benchmarks/runner.py:266-271).
7. **Determinism and resume everywhere** — seeded subsets are stable across input orderings (per-group sampling in repoqa, round-robin over pre-shuffled pools in swebench) (benchmarks/suites/repoqa.py:202-222; benchmarks/suites/swebench.py:89-112); sweeps skip cells already present in runs.jsonl; interrupted enrichment resumes from the council frontier or skips via markers; full (non-shallow) clones because arbitrary pinned commits and SWE grading need reachable history (benchmarks/arms.py:143-145).
8. **Concurrency hygiene** — every paid run gets its own sandbox root (shared opencode state databases deadlock with "database is locked") (benchmarks/runner.py:124-131); JSONL appends serialize under `_ROW_LOCK`; worker cold-starts stagger up to slot%8 × 3 s; workspaces materialize via tmp-dir+atomic-rename with explicit race-loss handling (benchmarks/__main__.py:147, 214-247; benchmarks/arms.py:160-185).
9. **Resilient cells, policy errors are not luck** — transport-class failures retry 3× with 20 s backoff and then write an explicit error row; `PayGateError` propagates immediately because gate violations are policy, not flakiness (benchmarks/__main__.py:150-196).

Load-bearing: the single-delta contract (#2) and index_state stamping (#3) carry the entire validity of the comparison; the telemetry dedup rules (#6) carry every efficiency number.

## Open questions

- **`benchmark_smoke` marker is registered but unused.** pyproject.toml:86 declares it and feature.json's summary cites it as the opt-in mechanism, but no test in tests/benchmarks/ applies `pytest.mark.benchmark_smoke` or a module-level `pytestmark`. Smoke validation currently happens manually per benchmarks/README.md:170-181. Doc-vs-code conflict: the summary overstates pytest integration.
- **Dry-run rows count toward resume-skip.** `run-repoqa`/`run-swebench` dry-runs append `executed: false` rows to the same runs.jsonl (benchmarks/__main__.py:316, 407), and `_done_cells` does not filter on `executed` (benchmarks/__main__.py:124-139) — a prior dry run marks cells done and a later `--execute` sweep skips them unless `reset-cells` clears the log first. Intent unclear: convenient resume or footgun.
- **Type annotation lie in repoqa adapter.** `prepared_for_task` is annotated `-> Path` but returns the `PreparedWorkspace` from `prepare_arm_workspace` (benchmarks/suites/repoqa.py:236-253); its swebench twin returns `.path` (benchmarks/suites/swebench.py:120-138). Callers use `prepared.path`/`prepared.index_mode` (benchmarks/__main__.py:272-302), so runtime behavior is consistent — but the annotation misleads any new caller.
- **Redundant double dedup in `cmd_enrich`.** `unique_repos_from_tasks` already deduplicates, then `cmd_enrich` dedupes again inline (benchmarks/__main__.py:462-471) — harmless, but suggests churn.
- **`supervise.sh` referenced, not owned.** RUN_LATER.md drives sweeps through `results/benchmarks/supervise.sh` (benchmarks/RUN_LATER.md:46-51), which belongs to none of this feature's files; its provenance cannot be verified from these sources.
