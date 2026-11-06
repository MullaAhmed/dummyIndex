# Retrieval correctness gate and pinned benchmark — plan

`confidence: INFERRED`

## Bounded context

This feature observes production retrieval; it owns test fixtures, metric
calculation and experimental records, not scoring behavior. Its two lanes share
`query` but retain different answer contracts:

| Lane | Source and contract |
|---|---|
| Frozen correctness gate | `tests/eval/test_retrieval_eval.py:46-206`: stable expected feature ID and cited path, fixed hit@3/MRR floors |
| Pinned repository benchmark | `benchmarks/retrieval/run_eval.py:27-184`: first returned feature containing an accepted gold file/directory, reported hit@1/hit@3/MRR |

`tests/eval/retrieval_fixtures.json` and three benchmark question JSON files are
the inputs. `tests/eval/BASELINE.md` and `benchmarks/retrieval/RESULTS.md` are
historical records; current execution is authoritative.

## Gate flow and decisions

The module-scoped `indexed_repo` fixture copies `SAMPLE_REPO` and runs
`build_all` once. The gate calls production retrieval with `top_k=3`, records
mean estimated tokens, and asserts `T_HIT=0.90` and `T_MRR=0.85`. A hit must also
carry the expected citation path; aggregate success cannot hide a wrong path
(`tests/eval/test_retrieval_eval.py:46-67`,
`tests/eval/test_retrieval_eval.py:117-172`).

The corpus requires at least twelve positives and exactly one negative control;
the committed corpus has twelve and one. Separate checks require no matches for
the off-topic control and vocabulary overlap for every positive fixture
(`tests/eval/test_retrieval_eval.py:70-81`,
`tests/eval/test_retrieval_eval.py:175-265`). Fixed expectations make regressions
repeatable, at the cost of representing a small authored sample rather than
live feature IDs from arbitrary rebuilds. Token estimates are observations, not
an additional quality floor.

## Benchmark flow and tradeoffs

`ensure_repo` clones/checks out pinned sources; `ensure_index` force-rebuilds a
deterministic standard-depth index. The disposable work directory isolates that
replacement from an owner's project. No council or model authoring participates
(`benchmarks/retrieval/run_eval.py:27-88`).

Question files map repository names to ordered `[question, golds]` rows. Default
questions alternate even/odd positions into development/holdout; `--split all`
evaluates a supplied file as one bucket. The default has 54 questions, later
files 21 and 28. The last set additionally uses pinned Click
(`benchmarks/retrieval/run_eval.py:27-48`,
`benchmarks/retrieval/run_eval.py:121-163`). Splits are runner policy; the runner
does not enforce research blinding or prevent manual reuse.

Each query requests ten matches, 100,000 estimated tokens and `max_bytes=65_536`.
A `truncated` result aborts before scoring, because token allowance alone cannot
bypass the production byte cap (`benchmarks/retrieval/run_eval.py:163-175`). Gold
matching accepts full paths, basenames or descendants of a directory; basename
matching can accept a same-named file elsewhere. Metrics print without an
automatic success threshold (`benchmarks/retrieval/run_eval.py:91-118`,
`benchmarks/retrieval/run_eval.py:178-184`).

## Dependencies and evidence boundary

Upstream are the backbone builder, public query API, local fixture source and,
for the benchmark, Git/network access plus pinned external repositories.
Downstream are pytest failure reports and printed benchmark metrics. This is a
one-way evaluator dependency, not a production/evaluator import cycle
(`tests/eval/test_retrieval_eval.py:35-37`,
`benchmarks/retrieval/run_eval.py:134-175`).

The pytest gate protects correctness at fixed floors. The networked benchmark
supports explicit experiments, with selection reuse and small-sample caveats in
its historical records. Neither lane measures agent task quality, and this
reconciliation adds no new benchmark measurements or broader quality claim.
