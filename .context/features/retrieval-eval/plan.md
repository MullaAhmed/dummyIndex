# Retrieval correctness gate — plan

`confidence: INFERRED`

## Bounded context

This feature observes production retrieval; it owns test fixtures and metric
calculation, not scoring behavior. Its source is the frozen gate:

| Lane | Source and contract |
|---|---|
| Frozen correctness gate | `tests/eval/test_retrieval_eval.py:46-265`: stable expected feature ID and cited path, fixed hit@3/MRR floors |

`tests/eval/retrieval_fixtures.json` is the input. `tests/eval/BASELINE.md` is a
historical record; current execution is authoritative.

## Gate flow and decisions

The module-scoped `indexed_repo` fixture copies `SAMPLE_REPO` and runs
`build_all` once. The gate calls production retrieval with `top_k=3`, records
mean estimated tokens, and asserts `T_HIT=0.90` and `T_MRR=0.85`. A hit must also
carry the expected citation path; aggregate success cannot hide a wrong path
(`tests/eval/test_retrieval_eval.py:46-67`,
`tests/eval/test_retrieval_eval.py:118-160`).

The corpus requires at least twelve positives and exactly one negative control;
the committed corpus has twelve and one. Separate checks require no matches for
the off-topic control and vocabulary overlap for every positive fixture
(`tests/eval/test_retrieval_eval.py:70-81`,
`tests/eval/test_retrieval_eval.py:182-214`,
`tests/eval/test_retrieval_eval.py:216-265`). Fixed expectations make regressions
repeatable. They represent a small authored sample, not
live feature IDs from arbitrary rebuilds. Token estimates are observations, not
an additional quality floor.

## Evidence boundary

Upstream are the backbone builder, public query API and local fixture source.
Downstream is the pytest failure report and printed metrics. This is a one-way
evaluator dependency (`tests/eval/test_retrieval_eval.py:36-37`).

The pytest gate protects correctness at fixed floors. It does not measure agent
task quality, and this reconciliation adds no new measurements or quality claim.
