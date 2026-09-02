# Architect notes — benchmarks plan revision (round 02)

Audit trail for the architect pass over `01-dev-draft.md`. Spec untouched; skeleton and `confidence: INFERRED` preserved.

## Verification performed

- Spot-checked every `path:range` citation against source files and `.context/map/symbols.json` (`run_one_task`, `prepare_arm_workspace`, `evaluate_gates`, `load_rows`, `append_row`, `_resilient_cell`, `write_predictions`, `extract_model_patch`, both `select_subset`s — all align).
- Read in full: arms.py, runner.py, __main__.py, telemetry.py, gates.py, report.py, enrich.py, suites/{__init__,repoqa,swebench}.py, scoring/{snf,snf_official,swebench_patch}.py, swegrade.sh.
- Doc-evidence: `benchmarks/RUN_LATER.md` is catalogued **medium** → quoted only after spot-check (`supervise.sh` exists). `benchmarks/README.md` is **low** (9/18 broken refs) → treated as historical context; its smoke-stage claim was re-verified directly against the file before citing. No low-confidence doc used as authority.

## Factual errors fixed

- **"all six command functions" → seven subcommands.** `build_parser` registers plan, run-repoqa, run-swebench, enrich, reset-cells, grade-swebench, report (benchmarks/__main__.py:585-672); seven matching `cmd_*` functions. Now enumerated explicitly.
- **Decision #8 lock claim overstated.** `_ROW_LOCK` guards the *in-memory* rows/predictions list appends (__main__.py:147, 213-214, 398), not the JSONL writes; file integrity rests on each `append_row` being one fresh `open("a")` + single write. Reworded to what the code actually does.
- **Old open question #4 ("redundant double dedup") withdrawn.** The second pass in `cmd_enrich` (__main__.py:468-469) dedupes across the *union* of repoqa + swebench targets — load-bearing for `--suite both`; `unique_repos_from_tasks` only dedupes within each suite. Resolved from code, folded into the enrich bullet under Where it lives.

## Open questions sharpened

- **supervise.sh**: dev said provenance "cannot be verified". It exists on disk as a gitignored runtime script (`.gitignore:37`). Reframed: committed runbook references an untracked artifact → fresh-clone reproducibility gap. Still genuinely open (ownership).
- **benchmark_smoke**: added `--strict-markers` context (pyproject.toml:81); noted README.md is low-confidence but content re-verified. Conflict with feature.json summary stands (spec.md already cross-references it).

## Mandate-driven additions

- **Patterns named**: composition root (`__main__`), suite adapters, transport port + injected seams (`stream_fn`/`cli_fn`/`run_fn`/`copy_fn`), report pipeline (`load_rows → aggregate → render_report`), gate evaluation over summaries, shared pinned-clone cache.
- **Dependencies made visible**: new acyclic dependency-direction block (`__main__` → suites/runner/arms/report/enrich; suites → arms; enrich → arms+runner; report → gates; runner → telemetry) plus lazy-import isolation of heavy optional deps (`datasets`, `nltk`, tree-sitter wheels).
- **Decisions promoted to explicit rationale**: fail-closed double gate incl. no-retry-on-`PayGateError` (#1); cost-ledger purity — why amortized section is gate-invisible and paid-calls-only (#4); AGENTS.md-written-last ordering invariant (#2); explicit error-row honesty + exit-code mapping (#9).
- **Filler cut**: data-model bullets tightened without losing any citation; decision wording compressed; stream-dump env gate named (`DUMMYINDEX_BENCH_KEEP_STREAMS=1`) replacing a vague clause.

## Conflicts flagged (code wins)

- `.context/architecture/overview.md` describes a java/js/kotlin stack, 576 files all under `results/`, 0 symbols — it does not describe this Python package at all. Ignored entirely; deterministic backbone needs `dummyindex context rebuild --changed`.
- feature.json summary vs code: `benchmark_smoke` opt-in claim overstated (kept as open question #1).
