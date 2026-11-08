# Correctness-gated retrieval eval — spec

`confidence: INFERRED`

## Intent

Catch regressions in deterministic feature retrieval before they ship. A small,
hand-authored question set is answered against a frozen sample index, and the
suite fails when the right feature stops ranking near the top or stops citing
the right file. A permanent off-topic question proves the gate is not passing
by matching everything. It measures retrieval correctness only; it does not
change retrieval, call a model, or judge agent task quality.

## User-visible behavior

`python -m pytest tests/eval/test_retrieval_eval.py -q -s` runs three
`integration` tests against one module-scoped `SAMPLE_REPO` build
(`tests/eval/test_retrieval_eval.py:54-61`). The gate prints a block of
positives count, MRR, hit-rate@3 and mean tokens-to-answer, then fails on
hit-rate@3 < `T_HIT = 0.90` or MRR < `T_MRR = 0.85`
(`tests/eval/test_retrieval_eval.py:43-44`, `:147-162`). Mean tokens are printed,
never asserted. A hit whose expected path is missing from its citations fails
immediately and names the question, expected path and actual citation paths
(`tests/eval/test_retrieval_eval.py:135-140`).

## Contracts

- **Fixture file** `tests/eval/retrieval_fixtures.json`: JSON array of
  `{question, expected_feature_id, expected_path}`; exactly one entry also
  carries `negative_control: true`. The committed file has 12 positives
  (`:2-61`) and the Kubernetes negative (`:62-67`). Loaders split on
  `negative_control` and assert exactly one negative
  (`tests/eval/test_retrieval_eval.py:64-75`); the gate asserts ≥12 positives
  (`:117`).
- **Metrics** per positive, at `query(ctx, question, top_k=3)`
  (`tests/eval/test_retrieval_eval.py:126`): rank = 1-based position of
  `expected_feature_id` in `result.matches`, else none (`:81-86`); hit@3 = rank
  present; RR = `1/rank` or 0; tokens = `result.total_estimated_tokens`
  (`:128-131`). MRR, hit-rate@3 and mean tokens are plain means over positives
  (`:142-145`).
- **Path match**: a citation path equals `expected_path` or ends with
  `"/" + expected_path` (`tests/eval/test_retrieval_eval.py:89-101`).
- **Negative control**: its `expected_feature_id` is absent from matches and
  `result.matches == ()` (`tests/eval/test_retrieval_eval.py:168-193`).
- **Fixture vocabulary**: every positive question shares ≥1 `tokenize` token
  with its feature's file basenames plus member symbol names
  (`tests/eval/test_retrieval_eval.py:200-249`).
- **Production API under test**: `query(context_dir, query_text, *, top_k=3,
  budget_tokens=2000, max_bytes=16_000) -> QueryResult`
  (`dummyindex/context/domains/query.py:271-278`) and `tokenize(text) ->
  tuple[str, ...]` (`dummyindex/context/domains/query.py:147-163`).

## Examples

`"how does make_app build an App instance"` → `community-0` / `app.py`
(`tests/eval/retrieval_fixtures.json:2-6`). `query` returns `community-0` at
rank 1, so RR = 1.0 and hit@3 = 1; `app.py` appears in that match's citations,
so the path assertion passes. At HEAD all 12 positives behave this way: the run
prints MRR 1.0000, hit-rate@3 1.0000, mean tokens 43.0, and all 3 tests pass.
`"kubernetes pod scheduling across availability zones"` returns no matches.
