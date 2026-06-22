# Correctness-gated retrieval eval — spec

confidence: INFERRED

## Intent

`dummyindex context query` retrieval can *look* helpful — fewer tokens-to-answer — while
steering an agent to the **wrong** feature. This eval pairs a recording metric (cost) with a
correctness gate (precision) so that failure mode can't pass silently. It gates the
`context-query` feature: a retrieval regression that drops the right feature out of the top-3
fails CI loudly. Ported from ponytail's paired `loc.js` (measurement) + `correctness.js` (gate)
methodology onto dummyindex's deterministic `query()` — **no retrieval-logic change**; the eval
*is* the test (`tests/eval/test_retrieval_eval.py:1-26`).

## User-visible behavior

Running the harness (`python -m pytest tests/eval/ -q`, or with `-s` to see the printed metrics)
exercises three integration tests over a frozen `SAMPLE_REPO` index built once per module
(`tests/eval/test_retrieval_eval.py:60-67`):

- **The gate** (`test_retrieval_eval_gate`, `:117-173`) runs every positive fixture through
  `query(ctx, question, top_k=3)`, records **MRR**, **hit-rate@3**, and **mean
  tokens-to-answer**, prints them, then asserts the two correctness floors. Pass = both floors
  met; fail = a real regression, with the failure message pointing at `BASELINE.md`.
- **The negative control** (`test_negative_control_scores_zero`, `:181-206`) asserts a
  known-wrong fixture scores 0 / rank ∞ (in this frozen index it matches nothing at all), so the
  gate cannot pass vacuously.
- **Fixture validation** (`test_every_positive_fixture_shares_a_token`, `:248-265`) asserts every
  positive question shares ≥1 non-stopword token with its expected feature's file/symbol vocab —
  guarding fixtures against drifting into questions the deterministic scorer cannot answer.

Recording metrics (MRR, mean tokens) are **always printed**; only hit-rate@3 and MRR are
**gated**. Mean tokens is a cost signal, not a correctness one (`BASELINE.md:75-76`).

## Contracts

- **Frozen index, not the live `.context/`** (Decision **D5**): the eval reuses the `SAMPLE_REPO`
  + `build_all` fixture that `tests/context/domains/test_query.py` uses — a deterministic, stable
  index with authored ids (`community-0` = `app.py`, `community-1` = `web/app.ts`, `community-2`
  = `helpers.py`) — instead of the volatile, re-clustering live index. Reuses `query()` /
  `tokenize()` from `dummyindex/context/domains/query.py` only
  (`query` at `query.py:168-174`, `tokenize` at `query.py:47`).
- **Fixtures** (`tests/eval/retrieval_fixtures.json`) — 12 positive
  `{question, expected_feature_id, expected_path}` entries plus exactly one `negative_control`
  (`retrieval_fixtures.json:1-68`). The harness asserts `len(positives) >= 12`
  (`test_retrieval_eval.py:127`) and exactly one negative (`:79-81`).
- **Thresholds (gate floors), set one documented margin below the baseline** — module constants
  `T_HIT = 0.90` (hit-rate@3; observed 1.0, 0.10 margin) and `T_MRR = 0.85` (MRR; observed 1.0,
  0.15 margin), `K=3` (`test_retrieval_eval.py:46-49`). Rationale of record in `BASELINE.md:57-76`:
  with 12 positives, one fixture out of top-3 → `11/12 ≈ 0.917` (tolerated); two misses
  `10/12 ≈ 0.833` trips `T_HIT`. **Never lower the floors to make a regression pass.**
- **Non-vacuity (negative control)** — the `negative_control` fixture
  (`"kubernetes pod scheduling across availability zones"` pointed at the wrong target
  `community-0`/`app.py`, `retrieval_fixtures.json:62-67`) shares no token with any sample
  feature, so `query()` returns zero matches; the permanent test asserts
  `result.matches == ()` and rank ∞ (`test_retrieval_eval.py:181-206`).
- **Stable signals only** — assertions key on the **expected file path** surfacing in a match's
  **citations** (`_path_in_citations`, `:97-109`) and on feature-id rank, never on raw
  `community-N` cluster ids, because the live index re-clusters on rebuild
  (paths survive re-clustering; ids do not — `testing.md:50`).

## Examples

A positive fixture and the assertion it drives:

```json
{ "question": "how does make_app build an App instance",
  "expected_feature_id": "community-0", "expected_path": "app.py" }
```

`query(ctx, "how does make_app build an App instance", top_k=3)` ranks `community-0` at #1
(reciprocal rank 1.0, a hit), and `app.py` surfaces in that match's citations — so both the rank
and the path-in-citations assertion (`test_retrieval_eval.py:145-150`) pass.

The negative control:

```json
{ "question": "kubernetes pod scheduling across availability zones",
  "expected_feature_id": "community-0", "expected_path": "app.py",
  "negative_control": true }
```

`query()` returns no matches; `result.matches == ()`, the wrong target `community-0` is absent
(rank ∞), reciprocal rank 0 — proving the gate is non-vacuous.

## Key artifacts

- `tests/eval/test_retrieval_eval.py` — the harness + gate (`test_retrieval_eval_gate`,
  `test_negative_control_scores_zero`, `test_every_positive_fixture_shares_a_token`).
- `tests/eval/retrieval_fixtures.json` — the 12 positives + 1 negative control.
- `tests/eval/BASELINE.md` — observed baseline (MRR 1.0, hit@3 1.0, mean tokens 40.5), the chosen
  floors (`T_HIT=0.90`, `T_MRR=0.85`), and the margin rationale.
