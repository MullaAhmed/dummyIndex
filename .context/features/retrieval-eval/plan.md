# Retrieval eval gate — plan

confidence: INFERRED

## Bounded context

This feature lives **wholly under `tests/eval/`** and adds nothing to `dummyindex/`: the eval *is*
the test, ported from ponytail's paired `loc.js` (measurement) + `correctness.js` (gate) onto
dummyindex's deterministic `query()` — no retrieval-logic change (`test_retrieval_eval.py:1-26`).
Four files: `test_retrieval_eval.py` (harness + gate + two guards), `retrieval_fixtures.json`
(the corpus), `BASELINE.md` (rationale of record for the floors), `__init__.py`.

The production surface is consumed **read-only** through exactly three import seams:

- `query` and `tokenize` from `dummyindex/context/domains/query.py` (`query.py:168`, `query.py:47`);
- `build_all` from `dummyindex/context/build/runner.py` (`runner.py:75`);
- `SAMPLE_REPO` from `tests/paths.py` (`tests/paths.py:14`) — imports gathered at
  `test_retrieval_eval.py:35-38`.

Nothing under `dummyindex/` changes. The boundary is one-directional: the eval observes `query()`,
it does not reach into scoring internals.

## Decisions (load-bearing first)

- **D5 — gate the frozen `SAMPLE_REPO` index, not the live `.context/`.** *The* foundational
  decision. The live index is un-enriched (`community-N`, `summary: null`) and **re-clusters on
  rebuild**, so gating on its ids would be brittle. The sample index is deterministic with authored
  ids — `community-0`=`app.py`, `community-1`=`web/app.ts`, `community-2`=`helpers.py` — built once
  via `build_all` (`test_retrieval_eval.py:60-67`, `BASELINE.md:11-19`, `testing.md:50`). Reuses the
  same `SAMPLE_REPO` + `build_all` fixture `tests/context/domains/test_query.py` uses.

- **Golden-baseline gate, floors one documented margin below.** Observed MRR 1.0, hit@3 1.0
  (`BASELINE.md:38-40`). Floors are module constants `T_HIT=0.90` (0.10 margin) and `T_MRR=0.85`
  (0.15 margin), `K=3` (`test_retrieval_eval.py:46-49`). The margin is **calibrated to the corpus
  size of 12**: one fixture out of top-3 → `11/12 ≈ 0.917` (tolerated as tie-break jitter); two
  misses → `10/12 ≈ 0.833` trips `T_HIT` (`BASELINE.md:66-75`). **Never lower the floors to make a
  regression pass** (`testing.md:53`) — a drop is the signal, not noise.

- **Non-vacuous negative control.** Without it a gate that matched *everything* would pass
  vacuously. The permanent `test_negative_control_scores_zero` feeds a known-wrong fixture
  (`"kubernetes pod scheduling across availability zones"` pointed at the wrong target `community-0`,
  `retrieval_fixtures.json` entry with `negative_control: true`) that shares no token with any sample
  feature, and asserts the wrong target is absent (rank ∞) **and** `result.matches == ()`
  (`test_retrieval_eval.py:181-206`).

- **Assert on stable signals, not cluster ids.** Hits key on feature-id **rank** plus the expected
  **path surfacing in `match.citations`** (`test_retrieval_eval.py:146-150`), never on raw
  `community-N` ids — paths survive re-clustering, ids do not (`testing.md:50`).

- **Record cost, gate correctness.** MRR, hit-rate@3 and **mean tokens-to-answer** are all computed
  and printed; only hit-rate@3 and MRR are asserted. Mean tokens is a cost signal, not a correctness
  one (`BASELINE.md:75-76`).

- **Build once per module; marked integration.** `build_all` (tree-sitter parse + graph + cluster)
  is the costly step, so the index is a `scope="module"` fixture shared by all three tests
  (`test_retrieval_eval.py:60-67`). The eval crosses into the real filesystem build pipeline, so each
  test carries `@pytest.mark.integration`; `--strict-markers` requires the explicit marker
  (`testing.md:22,49`).

## Dependencies surfaced

- **Gates `context-query`.** This is the consumer-side guard on the `query()` retrieval feature: a
  regression that drops the right feature out of the top-3 fails CI loudly. The gate's correctness is
  entirely a function of `query()`'s scoring behaviour over the frozen index.
- **Depends on the `SAMPLE_REPO` fixture + `build_all` pipeline.** A change to either the sample repo
  contents or the build/cluster pipeline shifts the authored ids or the achievable baseline, which
  invalidates `BASELINE.md` and requires a deliberate re-observation.
- **Depends on `tokenize` semantics.** The fixture-quality guard (`_feature_vocab` →
  `test_every_positive_fixture_shares_a_token`) tokenizes feature vocab with the *public* `tokenize`,
  so a change to stop-word handling or tokenization can flip a fixture from valid to unanswerable.

## Components

The three tests and their pure helpers:

- **The gate** — `test_retrieval_eval_gate` (`test_retrieval_eval.py:117-178`): runs every positive
  through `query(ctx, q, top_k=3)`, asserts `len(positives) >= 12` (`:127`), accumulates reciprocal
  rank, hit@3, and `total_estimated_tokens`, prints all three, then asserts the two floors.
- **The negative control** — `test_negative_control_scores_zero` (`:181-206`): the non-vacuity proof.
- **Fixture-quality guard** — `test_every_positive_fixture_shares_a_token` (`:248-265`): every
  positive question must share ≥1 non-stopword token with its expected feature's file/symbol vocab.
- **Pure helpers**: `_load_fixtures` / `_positives` / `_negative_control` split the corpus at load
  (`:74-86`, asserting exactly one negative); `_expected_rank` 1-based rank or `None` (`:89-94`);
  `_path_in_citations` exact-or-trailing-segment path match in `match.citations` (`:97-109`);
  `_feature_vocab` basenames + symbol names from `feature.json` + `map/symbols.json`, tokenized via
  public `tokenize` (`:216-245`).

## Data model

- **Fixtures** (`retrieval_fixtures.json`): a flat JSON array of
  `{question, expected_feature_id, expected_path}`; the single negative entry adds
  `negative_control: true`. **12 positives + 1 negative = 13 entries.**
- **Frozen index** (built into `tmp_path/.context/`): authored stable ids `community-0`=`app.py`,
  `community-1`=`web/app.ts`, `community-2`=`helpers.py`; `summary: null`, so scoring leans entirely
  on file-basename + symbol-name overlap (which is exactly what `_feature_vocab` mirrors).
- **Baseline** (`BASELINE.md`): observed MRR 1.0, hit@3 1.0, mean tokens 40.5 (`:38-40`); floors
  `T_HIT=0.90`, `T_MRR=0.85` mirrored as module constants (`test_retrieval_eval.py:46-49`).

## Open questions

- **Baseline re-observation is manual.** `BASELINE.md` is the rationale of record, advanced only on a
  deliberate re-observation; nothing detects that `query()` scoring *legitimately improved* (raising
  the achievable baseline above the current floors).
- **Margins are tuned to exactly 12 positives** (`BASELINE.md:66-75`); growing the corpus requires
  re-deriving them.
- **Frozen-index fidelity.** Gating `SAMPLE_REPO` trades realism for determinism: a regression that
  only manifests on enriched, summary-bearing live indices is out of scope here.
