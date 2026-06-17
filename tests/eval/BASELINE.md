# Retrieval eval baseline

Committed baseline for the correctness-gated retrieval eval
(`test_retrieval_eval.py`). The gate floors (`T_HIT`, `T_MRR`) are module
constants set **one documented margin below** the observed numbers recorded
here. This file is the rationale of record for those floors; update it (and the
constants) only after a deliberate re-observation, never to paper over a
regression.

## What is measured

The eval reuses the deterministic `query()` retrieval (no LLM, no
retrieval-logic change) over the **frozen `SAMPLE_REPO` index** — the same
`SAMPLE_REPO` + `build_all` fixture `tests/context/domains/test_query.py` uses
(Decision **D5**). The live `.context/` is un-enriched (`community-N`,
`summary: null`) and re-clusters on rebuild, so gating on its ids would be
brittle; the sample index is deterministic and carries stable authored ids
(`community-0` = `app.py`, `community-1` = `web/app.ts`, `community-2` =
`helpers.py`).

For each **positive** fixture (the 12 `retrieval_fixtures.json` entries without
`negative_control`) the harness runs `query(..., top_k=3)` and records:

- **hit@3** — whether `expected_feature_id` appears in the top-3 matches.
- **path-in-citations** — whether `expected_path` surfaces in that match's
  **citations** (in this frozen index `INDEX.json` carries no `files` key, so
  the path surfaces via a match's citations, not a `files` field).
- **reciprocal rank** — `1 / rank` of the expected feature (0 if absent), for MRR.
- **`total_estimated_tokens`** — the query's tokens-to-answer, for the mean.

## Observed numbers

Observed by running the harness against a freshly built `SAMPLE_REPO` index
(12 positive fixtures):

| Metric                 | Observed |
|------------------------|----------|
| MRR                    | 1.0000   |
| hit-rate@3             | 1.0000   |
| mean tokens-to-answer  | 40.5     |

Every positive fixture's expected feature ranks **#1**, and its `expected_path`
appears in that match's citations. The fixtures were authored (Wave 1) so each
question shares ≥1 non-stopword token with a file basename or symbol name of its
expected feature — so name/path/symbol overlap alone is enough to rank the right
feature first even though `summary` is null (the summary weight contributes
nothing here).

## Negative control (proves the gate is non-vacuous)

The `negative_control` fixture — `"kubernetes pod scheduling across
availability zones"` pointed at `community-0`/`app.py` — shares no token with any
sample feature. `query()` returns **zero matches** for it: the wrong target
scores 0 and ranks ∞ (reciprocal rank 0). A permanent test asserts this, so the
gate cannot pass vacuously by matching everything.

## Gate floors and margin

The observed MRR and hit-rate@3 are a perfect `1.0`. The gate is set **one
margin below** that baseline so an ordinary retrieval regression (a couple of
fixtures dropping out of the top-3, or the right feature slipping from rank 1)
fails the gate loudly, while incidental scoring jitter does not:

| Constant | Floor | Margin below observed |
|----------|-------|-----------------------|
| `T_HIT` (hit-rate@3) | **0.90** | 0.10 absolute below 1.0 |
| `T_MRR` (MRR)        | **0.85** | 0.15 absolute below 1.0 |

Rationale for the magnitudes: with 12 positives, one fixture falling out of the
top-3 drops hit-rate@3 to `11/12 ≈ 0.917` — still above `T_HIT = 0.90` (tolerated
as jitter); **two** misses (`10/12 ≈ 0.833`) trip it. For MRR, one expected
feature slipping from rank 1 to rank 2 costs `0.5/12 ≈ 0.042`; the `0.85` floor
absorbs roughly three such single-rank slips (or one fixture dropping to rank ∞
plus minor slippage) before tripping — tight enough to catch a real regression,
loose enough not to flap on a tie-break reshuffle. The mean-tokens metric is
**recorded and printed, not gated** (it is a cost signal, not a correctness one).
