# Retrieval correctness gate — plan

`confidence: INFERRED`

Bare `:N` = `tests/eval/test_retrieval_eval.py`; `query.py` = `dummyindex/context/domains/query.py`.

This feature observes production retrieval; it owns test fixtures and metric
calculation, not scoring behavior. Its source is the frozen gate:

| Lane | Source and contract |
|---|---|
| Frozen correctness gate | `tests/eval/test_retrieval_eval.py:46-265`: stable expected feature ID and cited path, fixed hit@3/MRR floors |

`tests/eval/retrieval_fixtures.json` is the input. `tests/eval/BASELINE.md` is a
historical record; current execution is authoritative.

The module-scoped `indexed_repo` fixture runs `build_all` once on a `SAMPLE_REPO`
copy for 3 tests (`:54-61`), and one JSON corpus, split on its
`negative_control` flag (`:68-75`), is table-driven through `query` (`:123-140`).
Pure helpers `_expected_rank`/`_path_in_citations` score each match (`:78-101`),
the gate asserts threshold floors (`:155-162`), and two guards check the corpus:
a permanent negative control (`:168-193`) and `_feature_vocab`, which
reads built artifacts (`:200-229`). Dependencies are one-way, no cycle:
`build_all` (`dummyindex/context/build/runner.py:92-100`), `query`/`tokenize`
(`dummyindex/context/domains/query.py:271-278`, `dummyindex/context/domains/query.py:147-163`) and `SAMPLE_REPO` (`tests/paths.py:14`,
shared by 29 test modules) are the whole import surface (`:35-37`); downstream
are CI (`.github/workflows/tests.yml:31-33`) and the separate behavior gate's
prose-only citations of `:10` (`tests/eval/behavior_gate.py:5`,
`tests/eval/behavior_arms.py:7` (citation unverifiable)).

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
repeatable, at the cost of representing a small authored sample rather than
live feature IDs from arbitrary rebuilds. Token estimates are observations, not
an additional quality floor.

## Evidence boundary

Upstream are the backbone builder, public query API and local fixture source.
Downstream is the pytest failure report and printed metrics. This is a one-way
evaluator dependency (`tests/eval/test_retrieval_eval.py:36-37`).

The pytest gate protects correctness at fixed floors. It does not measure agent
task quality, and this reconciliation adds no new measurements or quality claim.
