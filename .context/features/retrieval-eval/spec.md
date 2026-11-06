# Retrieval correctness gate and pinned benchmark — spec

`confidence: INFERRED`

## Intent

Keep deterministic retrieval correct while measuring ranking behavior on larger
repositories. The frozen pytest gate protects known navigation answers; a
separate pinned real-repo runner supports historical ranking experiments.
Neither lane measures model task quality or changes production retrieval itself.

## User-visible behavior

`python -m pytest tests/eval/test_retrieval_eval.py -q -s` builds one temporary
copy of `SAMPLE_REPO` per module and runs three integration checks. The main
gate evaluates positive fixtures with `query(..., top_k=3)`, prints MRR,
hit-rate@3 and mean estimated tokens, and requires hit-rate@3 >= 0.90 and MRR >=
0.85. Mean estimated tokens is recorded rather than gated. The other checks
require the off-topic negative control to return no matches and every positive
question to overlap its expected feature vocabulary
(`tests/eval/test_retrieval_eval.py:46-67`,
`tests/eval/test_retrieval_eval.py:117-206`,
`tests/eval/test_retrieval_eval.py:216-265`).

The pinned benchmark is invoked as
`python benchmarks/retrieval/run_eval.py [--workdir PATH] [--split dev|holdout|both|all] [--questions PATH]`.
It checks out the recorded requests, Flask and dummyindex commits; the newest
question set also uses pinned Click. It force-builds deterministic backbone
indexes without council/model calls and scores the first returned feature
containing an accepted gold path. Use a disposable work directory: its indexes
are rebuilt with `--force`
(`benchmarks/retrieval/run_eval.py:27-88`,
`benchmarks/retrieval/run_eval.py:121-158`).

The default corpus contains 54 questions split by alternating per-repo indices
into development/holdout sets. Separate JSON files contain 21 and 28 later
validation questions; `--split all --questions PATH` evaluates a supplied set as
one bucket. Each query requests ten matches, 100,000 estimated tokens and the
65,536-byte ceiling. A `truncated` result aborts with `RuntimeError`; the runner
never silently scores a shortened top ten
(`benchmarks/retrieval/run_eval.py:141-176`). It prints hit@1, hit@3 and MRR;
there is no automatic quality threshold in this script
(`benchmarks/retrieval/run_eval.py:178-184`).

## Contracts

- The frozen fixture corpus is a JSON array of `question`,
  `expected_feature_id`, `expected_path`, with one `negative_control` entry.
  The gate requires at least twelve positives and exactly one negative
  (`tests/eval/test_retrieval_eval.py:70-81`, `:125-127`). Hits require the expected
  feature rank plus its expected path in citations; path matching accepts an
  exact or trailing path segment (`tests/eval/test_retrieval_eval.py:89-109`,
  `:133-150`). Stable expectations concern this frozen index, not live cluster
  IDs after a rebuild.
- `ensure_repo(workdir, name, url, sha) -> pathlib.Path` clones/checks out pinned
  source; `ensure_index(repo_dir) -> pathlib.Path` rebuilds its index
  (`benchmarks/retrieval/run_eval.py:51-88`).
- `feature_files(context_dir) -> dict[str, set[str]]` loads per-feature file
  paths and basenames. `gold_matches(golds, ffiles) -> bool` accepts full paths,
  matching basenames or descendants of a directory gold
  (`benchmarks/retrieval/run_eval.py:91-118`).
- Benchmark `main() -> int` accepts question JSON shaped as
  `{repo_name: [[question, [gold_paths]], ...]}` and returns zero after printing
  metrics; clone/index/query failures propagate
  (`benchmarks/retrieval/run_eval.py:121-188`).

## Examples and evidence limits

The committed positive fixture `how does make_app build an App instance` targets
`community-0` and `app.py`; the gate checks its rank and cited path. The
off-topic Kubernetes fixture must return no matches. For a separate real-repo
validation, run the benchmark with `--split all --questions
benchmarks/retrieval/questions_holdout3.json` in a disposable work directory.

`tests/eval/BASELINE.md` is historical rationale for the existing gate;
`benchmarks/retrieval/RESULTS.md` records earlier tuning/validation and selection
caveats. Neither record is a new run of the combined release. The model-dependent
behavior gate has a separate scope and evidence; these retrieval metrics do not
establish agent-quality improvement.
