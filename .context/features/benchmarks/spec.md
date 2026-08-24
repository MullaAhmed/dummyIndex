# Benchmark harness — spec

`confidence: INFERRED`

## Intent

The harness answers one question with numbers: does handing an agent a prebuilt, council-curated `.context/` index beat leaving it alone with grep in a raw checkout? It pits two configurations ("arms") against each other on byte-identical prompts over identical tasks drawn from two public suites — RepoQA Searching-Needle-Function and a stratified SWE-bench Lite subset — records per-run token, tool-call, cost, and wall-time telemetry, grades outputs with the official rules (or the official harness, for SWE-bench), and renders an arm-vs-arm markdown report judged against acceptance thresholds fixed before any measurement. Everything that could spend tokens is gated behind an explicit CLI flag plus an environment opt-in, so planning, reporting, enrichment previews, and the entire unit-test suite are free by default.

## User-visible behavior

### CLI: `python -m benchmarks`

Seven subcommands wired in `build_parser` (benchmarks/\_\_main\_\_.py:585-672), dispatched through `main` (benchmarks/\_\_main\_\_.py:691-712):

| Command | What it does | Spends tokens |
|---|---|---|
| `plan` | prints model, gate state, one sample argv, and matrix counts (tasks × arms × repeats) | never (benchmarks/\_\_main\_\_.py:58-79) |
| `run-repoqa` | dry-runs or executes RepoQA SNF cells; grades per `--protocol name\|function`; writes REPORT.md on execute | only with gates (benchmarks/\_\_main\_\_.py:250-343) |
| `run-swebench` | same shape for SWE-bench Lite; extracts patches into a predictions JSONL for the official harness | only with gates (benchmarks/\_\_main\_\_.py:346-440) |
| `enrich` | phase 0: drives the council loop over every unique `(repo, commit)`; separate cost ledger | only with gates (benchmarks/\_\_main\_\_.py:443-512) |
| `reset-cells` | drops rows matching `--arm`/`--index-state` from a suite log (backup first) to force re-measurement | never (benchmarks/\_\_main\_\_.py:515-543) |
| `grade-swebench` | invokes `scoring/swegrade.sh` on a predictions file (docker required) | external harness, not LLM tokens (benchmarks/\_\_main\_\_.py:546-550) |
| `report` | aggregates existing JSONL into stdout or `--out` markdown; merges optional `--resolved` map | never (benchmarks/\_\_main\_\_.py:553-573) |

Common flags: `--model`, `--opencode-bin`, `--timeout-s` (default 1800), `--repeats` (3), `--seed` (20260823), `--limit`, `--workers` (1 = sequential) (benchmarks/\_\_main\_\_.py:587-600). Suite-specific: `run-repoqa --per-cell/--protocol/--execute`; `run-swebench --size/--execute/--run-id` (`--run-id` defaults to `swe-{seed}`, benchmarks/\_\_main\_\_.py:699-700); `enrich --suite/--mode light|standard|deep/--cap/--max-rounds/--execute`. `--version` prints `BENCHMARKS_VERSION` `"0.1.0"` (benchmarks/\_\_init\_\_.py:33, benchmarks/\_\_main\_\_.py:607).

**Pay gate.** Any spending run requires BOTH `--execute` and `DUMMYINDEX_BENCH_ALLOW_PAY=1` (benchmarks/\_\_init\_\_.py:35; checked in `pay_gate_open` benchmarks/runner.py:54-55, `_execute_gate_or_die` benchmarks/\_\_main\_\_.py:142-144, and again inside `run_one_task` benchmarks/runner.py:224-229). Violation raises `PayGateError` → exit code 3.

**Environment knobs.** `DUMMYINDEX_BENCH_KEEP_STREAMS=1` persists raw event streams (dir overridable via `DUMMYINDEX_BENCH_STREAM_DIR`) for debugging (benchmarks/runner.py:293-315); `DUMMYINDEX_BENCH_SANDBOX` relocates per-run sandbox roots (benchmarks/runner.py:133-139); `REPOQA_BENCH_DATA_VERSION` / `REPOQA_BENCH_DATA_OVERRIDE_PATH` pin or locally override the RepoQA release artifact (benchmarks/suites/repoqa.py:50-52).

**Exit codes.** 0 success; 1 when `report` finds no rows (benchmarks/\_\_main\_\_.py:565-567); 2 argparse usage; 3 `PayGateError|RunnerError`; 4 `SuiteDataError` (benchmarks/\_\_main\_\_.py:701-708).

**pytest.** The `benchmark_smoke` marker is registered in pyproject.toml:82-87 with `--strict-markers`, described as the opt-in smoke stage. Note: no test under tests/benchmarks/ currently applies it — see Open questions in plan.md.

## Contracts

### Runner — transport, gating, ledger

- `pay_gate_open() -> bool` — true iff `DUMMYINDEX_BENCH_ALLOW_PAY == "1"` (benchmarks/runner.py:54-55).
- `RunnerConfig(model, opencode_bin, timeout_s, results_dir, real_data_home)` frozen dataclass; `argv(prompt=..., workspace=..., title=...)` builds the exact invocation `opencode run --format json --auto --pure -m <model> --dir <ws> --title <title> <prompt>` (benchmarks/runner.py:58-82).
- `run_one_task(*, suite, arm_value, task_id, repeat_index, prompt, workspace, config, execute=False, stream_fn=None) -> RunOutcome` — with `execute=False` returns a planned outcome carrying argv and spends nothing; with `execute=True` requires the gate, runs opencode under a fresh sandbox, treats nonzero exit OR a zero-parseable-event stream as `RunnerError` (a broken transport never reads as an arm result) (benchmarks/runner.py:188-290).
- `sandbox_env(real_data_home) -> (env, root)` — per-call unique root under `$TMPDIR/bi-bench-sandbox/run-{pid}-{uuid}` (or `DUMMYINDEX_BENCH_SANDBOX`); sets empty `XDG_CONFIG_HOME`/`XDG_DATA_HOME`, copying only `opencode/auth.json` across; caller deletes the root (benchmarks/runner.py:124-154).
- `RunOutcome.to_row()` — planned rows carry identity + `prompt_sha256` + `argv`; executed rows instead carry merged `RunMetrics` fields and a 500-char `stderr_tail` (benchmarks/runner.py:85-115).
- `append_row(row, results_dir, suite) -> Path` — appends one sorted-key JSON line to `<results_dir>/<suite>/runs.jsonl` (benchmarks/runner.py:318-325).

### Arms — two-configuration discipline

- `Arm(str, Enum)`: `BASELINE = "baseline"`, `CONTEXT = "context"`; `ARMS` tuple (benchmarks/arms.py:39-48).
- `render_agents_md(arm) -> str`: baseline gets exactly `NEUTRAL_BASE`; context gets `NEUTRAL_BASE + CONTEXT_SECTION` — the shared-base/single-delta contract; the baseline file is a strict prefix of the context file (benchmarks/arms.py:58-105).
- `prepare_arm_workspace(arm, repo, commit, workspace_root, *, cache_root, repeat=None, indexer=None, run_setup=None, copy_fn=None) -> PreparedWorkspace` — idempotent, race-tolerant pipeline: ensure shared pinned clone → materialize arm-local copy (atomic tmp+rename) → context arm inherits an enriched index verbatim or ingests a backbone (`dummyindex ingest --platform agents --no-hooks ... --force`); baseline always has `.context/` stripped → write `AGENTS.md` last → write `.bi_bench_ready` marker `"{arm}:{commit}:indexed={0|1}:mode={none|backbone|enriched}"` (benchmarks/arms.py:250-332).
- `PreparedWorkspace(arm, path, agents_md, indexed, index_mode)` with `index_mode ∈ {"none","backbone","enriched"}` (benchmarks/arms.py:203-211).
- `ensure_pinned_clone(repo, commit, *, cache_root, url_for=None, run_fn=None) -> Path` — full clone at `https://github.com/{repo}.git` detached to `commit`, idempotent via `.git/BI_BENCH_PINNED` marker (benchmarks/arms.py:127-157).
- `is_enriched(root) / mark_enriched(root, *, mode, units)` — completion marker `.bi_bench_enriched` holding `{"mode","units"}` JSON (benchmarks/arms.py:214-226).

### Suites — task loading, subsets, prompts

- `SnfTask(task_id, language, repo, commit, func, description, path, start_line, end_line)` normalized from the official release schema (benchmarks/suites/repoqa.py:73-89); `load_repoqa_records` downloads-and-caches `repoqa-{version}.json.gz` from `evalplus/repoqa_release` (default version `2024-06-23`) with override env support (benchmarks/suites/repoqa.py:119-139); `tasks_from_records` fails loudly on malformed records (benchmarks/suites/repoqa.py:142-186); `select_subset(tasks, *, per_lang_per_repo, seed)` is deterministic-stratified per `(language, repo)` regardless of input order (benchmarks/suites/repoqa.py:202-222); `build_prompt(task, *, protocol)` picks `NAME_INSTRUCTION` or `FUNCTION_INSTRUCTION` (benchmarks/suites/repoqa.py:59-70, 225-233).
- `SweTask(instance_id, repo, base_commit, problem_statement)` (benchmarks/suites/swebench.py:43-52); `load_swebench_lite()` needs the optional `datasets` package, raising `SuiteDataError` otherwise (benchmarks/suites/swebench.py:55-86); `select_subset(tasks, *, size, seed)` round-robins sorted, pre-shuffled per-repo pools (benchmarks/suites/swebench.py:89-112); `build_prompt` embeds repo, short commit, issue text, and anti-cheat rules (benchmarks/suites/swebench.py:32-40, 115-117); `write_predictions(rows, path)` emits `{"instance_id","model_patch"}` JSONL (benchmarks/suites/swebench.py:141-147).

### Scoring — verdicts

- `grade_snf(response, needle_func) -> SnfVerdict` — passes iff the needle appears case-insensitively anywhere in the response (benchmarks/scoring/snf.py:17-28).
- `grade_snf_official(model_output, ground_truth, repo_info, lang, ignore_comments=False) -> SnfOfficialVerdict` — fence sanitization → tree-sitter extraction → NLTK smoothed-BLEU best-match against every needle in the repo; `passed_at(threshold=0.8)` passes iff best target equals ground truth AND similarity ≥ threshold; `ladder()` reports all upstream thresholds (benchmarks/scoring/snf_official.py:37-38, 197-238, 241-255). Missing nltk or grammar wheels raise `GraderError` before any scoring (benchmarks/scoring/snf_official.py:75-104, 165-187).
- `extract_model_patch(workspace, base_commit) -> str` — `git add -A` then `git diff --cached <base>`, resetting the index afterwards; empty string means "changed nothing"; non-git dirs raise `PatchError` (benchmarks/scoring/swebench_patch.py:36-54).
- `swegrade.sh <predictions.jsonl> <run_id> [dataset]` — fronts `python -m swebench.harness.run_evaluation`; refuses without docker; writes reports under `results/benchmarks/swebench/{run_id}/` (benchmarks/scoring/swegrade.sh:20-51).

### Gates — pre-registered acceptance

- Constants fixed before measurement: `SNF_NONINFERIORITY_MARGIN = 0.02`, `SWE_NONINFERIORITY_MARGIN = 0.05`, `TOOL_CALL_RATIO_FLOOR = 1.15` (benchmarks/gates.py:32-34).
- `evaluate_gates(summaries: Sequence[SuiteSummary]) -> GateReport` — per suite: accuracy non-inferiority (`ctx.pass_rate − base.pass_rate ≥ −margin`, with 1e-9 float slack) and tool-call ratio floor (`base.mean_tool_calls / ctx.mean_tool_calls ≥ 1.15`); a missing/empty arm summary fails closed; `GateReport.all_passed` and `render()` produce `[PASS]/[FAIL]` lines (benchmarks/gates.py:37-129).

### Report — aggregation and rendering

- `load_rows(results_dir, suite)` keeps only the LAST row per `(arm, task_id, repeat_index)` so resume-after-reset reads deterministically (benchmarks/report.py:99-116).
- `aggregate(rows, arm_value) -> Aggregates` — counts only `executed` rows: n, graded_n, pass_rate, mean input/output/cache-read tokens, σ of output, mean tool calls, per-tool breakdown, total wall time, tokens-per-correct (benchmarks/report.py:47-96).
- `render_report(rows_by_suite, *, title)` — suite key `"__enrichment__"` renders the amortized-cost section and never touches gates; other suites render an index-condition breakdown line, one arm table row each, top-8 tool breakdowns, then the gate block and a bold verdict (benchmarks/report.py:167-246). `write_report` writes it to a path (benchmarks/report.py:249-255).
- `enrichment_totals(rows)` sums agent calls/tokens/cost/wall for the phase-0 ledger (benchmarks/report.py:119-136).

### Telemetry — one metric shape, two ingestion paths

- `metrics_from_stream(lines) -> RunMetrics` for `opencode run --format json` stdout; `metrics_from_export(document) -> RunMetrics` for `opencode export` (raises `TelemetryError` on invalid JSON) (benchmarks/telemetry.py:211-230).
- Harvesting rules: usage deduped per message id (last observation wins); anonymous observations keep the largest single one, never summed; cost takes the cumulative max; tool calls counted once per named tool node; text parts concatenated in arrival order (benchmarks/telemetry.py:14-24, 109-176).
- `RunMetrics.to_row()` is JSONL-safe with sorted `tool_calls` plus `total_tool_calls` (benchmarks/telemetry.py:52-66).

### Enrichment — phase-0 council driver

- `Enricher(config, cache_root, results_dir, execute=False, mode="standard", max_rounds=200, cap=4, ...)`.`enrich_repo(repo, commit) -> EnrichResult` — skips enriched caches (`status "already"`); ingests if `.context/` missing; ships council procedure markdowns into `.context/council/procedures/`; loops `dummyindex context council-batch --next --json` dispatching one opencode run per unit (suite `"enrichment"`, arm `"council"`); returns `"stalled"` past `max_rounds`; closes with per-feature `reality-check` + `mark-enriched`, then writes the repo-level marker (benchmarks/enrich.py:53-72, 90-106, 156-206, 242-285).
- `EnrichResult.status ∈ {"already","done","stalled","failed"}` with `to_row()` (benchmarks/enrich.py:53-72).
- `unique_repos_from_tasks(tasks) -> list[(repo, commit)]` — order-preserving dedupe accepting both task shapes (`SnfTask.commit` / `SweTask.base_commit`) (benchmarks/enrich.py:288-298).

### Row format (the interchange contract)

One JSON object per cell in `results/benchmarks/<suite>/runs.jsonl`: identity keys from `RunOutcome.to_row()` (benchmarks/runner.py:99-115), plus per-suite extras — `protocol`, `index_state`, `passed`, and `best_similarity` for graded repoqa cells (benchmarks/\_\_main\_\_.py:299-316); `index_state` for swebench cells (benchmarks/\_\_main\_\_.py:393-395); explicit `error` rows with `executed: false` when a cell exhausts retries (benchmarks/\_\_main\_\_.py:185-194). SWE-bench prediction rows pair `instance_id` formatted `{task}-{arm}-r{repeat}` with `model_patch` (benchmarks/\_\_main\_\_.py:397-406).

## Examples

Happy path — a paid RepoQA sweep cell:

```bash
DUMMYINDEX_BENCH_ALLOW_PAY=1 python -m benchmarks run-repoqa --execute \
    --per-cell 2 --repeats 3 --protocol name
```

1. `main` registers the fatal-signal recorder, parses args, defaults the model (benchmarks/\_\_main\_\_.py:675-698). The gate is open, so `_execute_gate_or_die` passes (benchmarks/\_\_main\_\_.py:142-144).
2. `load_repoqa_tasks` downloads-or-caches the release JSON and flattens it into `SnfTask`s; `select_subset` picks 2 needles per (language, repo) with the seed (benchmarks/suites/repoqa.py:189-191, 202-222).
3. `_done_cells("repoqa")` reports already-recorded `(arm, task, repeat)` triples; those cells are skipped (benchmarks/\_\_main\_\_.py:124-139, 320-336).
4. For cell `(context, task, r0)`: `prepare_arm_workspace` finds the shared pinned clone (cloning once if absent), materializes the arm-local tree, inherits the enriched `.context/` (marker `index_state=enriched`) or ingests a backbone, writes the neutral-base-plus-navigation-section `AGENTS.md`, drops `.bi_bench_ready` (benchmarks/arms.py:250-332).
5. `build_prompt` emits the NAME_INSTRUCTION plus the function description (benchmarks/suites/repoqa.py:225-233); `run_one_task` spawns opencode with `--auto --pure` under a private XDG sandbox carrying only provider auth, streams stdout through `metrics_from_stream`, and enforces nonzero-exit/zero-event = `RunnerError` (benchmarks/runner.py:206-290).
6. Grading: `grade_snf(response_text, task.func)` sets `passed`; the row gains `protocol` and `index_state` and is appended to `results/benchmarks/repoqa/runs.jsonl` (benchmarks/\_\_main\_\_.py:303-316; benchmarks/scoring/snf.py:23-28).
7. Cells run sequentially (dots) or on a `ThreadPoolExecutor` with 10%-milestone progress; transient `RunnerError`/`WorkspaceError`/`OSError` retry 3× at 20 s backoff, then land as an explicit error row (benchmarks/\_\_main\_\_.py:150-238).
8. On finish, `write_report({"repoqa": rows}, results/benchmarks/REPORT.md)` renders arm tables, index-condition breakdown, and the pre-registered gate block with PASS/FAIL verdicts (benchmarks/\_\_main\_\_.py:338-343; benchmarks/report.py:167-246; benchmarks/gates.py:78-129).

Failure shapes for the same command: forgetting the env var exits 3 with `error: --execute requires DUMMYINDEX_BENCH_ALLOW_PAY=1…` before any spend; a corrupt download raises `SuiteDataError` → exit 4; a dead transport retries then writes an error row, leaving a visible hole instead of a fake result.
