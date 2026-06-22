# Retrieval eval gate — plan

confidence: INFERRED

## Where it lives

Wholly under `tests/eval/`: `test_retrieval_eval.py` (harness + gate),
`retrieval_fixtures.json` (the corpus), `BASELINE.md` (rationale of record for the floors), and
`__init__.py`. It imports the production retrieval surface read-only —
`query` and `tokenize` from `dummyindex/context/domains/query.py`
(`query.py:168-174`, `query.py:47`) — and the build entrypoint `build_all` from
`dummyindex/context/build/runner.py`, plus the `SAMPLE_REPO` anchor from `tests/paths.py`
(`test_retrieval_eval.py:35-38`). No file under `dummyindex/` changes: the eval is additive and
the feature *is* the test.

## Architecture in three sentences

A deterministic benchmark builds the frozen `SAMPLE_REPO` index once per module via `build_all`
(`test_retrieval_eval.py:60-67`) and runs every positive fixture through `query(ctx, q, top_k=3)`,
recording MRR, hit-rate@3, and mean tokens-to-answer. It gates the `context-query` feature on
**hit-rate@3 ≥ T_HIT** and **MRR ≥ T_MRR** — floors set one documented margin below the
baseline in `BASELINE.md` — while leaving mean tokens recorded but ungated as a cost signal. A
permanent negative-control test asserts a known-wrong fixture scores 0 / rank ∞ so the gate is
non-vacuous, and a per-fixture token-overlap test guards fixture quality.

## Data model

- **Fixtures** (`retrieval_fixtures.json`): a flat JSON array of
  `{question, expected_feature_id, expected_path}`; the single negative entry adds
  `negative_control: true`. Split at load time into `_positives()` / `_negative_control()`
  (`test_retrieval_eval.py:74-81`). 12 positives + 1 negative.
- **Frozen index** (built into `tmp_path/.context/`): authored stable ids
  `community-0` = `app.py`, `community-1` = `web/app.ts`, `community-2` = `helpers.py`;
  `summary: null`, so scoring leans entirely on file-basename + symbol-name overlap.
- **Baseline** (`BASELINE.md`): observed MRR 1.0, hit@3 1.0, mean tokens 40.5; floors
  `T_HIT=0.90`, `T_MRR=0.85` mirrored as module constants (`test_retrieval_eval.py:46-49`).
- **Per-fixture scoring helpers** (pure): `_expected_rank` (1-based rank, `:89-94`),
  `_path_in_citations` (exact or trailing-segment path match in `match.citations`, `:97-109`),
  `_feature_vocab` (basenames + symbol names via `feature.json` + `map/symbols.json`,
  tokenized with the public `tokenize`, `:216-245`).

## Key decisions

- **D5 — gate the frozen `SAMPLE_REPO` index, not the live `.context/`.** The live index is
  un-enriched (`community-N`, `summary: null`) and re-clusters on rebuild, so gating on its ids
  would be brittle. The sample index is deterministic with authored ids
  (`BASELINE.md:11-19`, `testing.md:50`).
- **Assert on stable signals, not cluster ids.** Hits key on feature-id rank plus the expected
  **path in citations** (`test_retrieval_eval.py:145-150`); paths survive re-clustering, ids do
  not.
- **Non-vacuous negative control.** A known-wrong fixture sharing no token with any feature must
  return zero matches (`test_retrieval_eval.py:181-206`); without it a gate that matched
  everything would pass vacuously.
- **Floors one margin below baseline.** `T_HIT=0.90` / `T_MRR=0.85` absorb incidental tie-break
  jitter (one fixture out of top-3 → `0.917`, tolerated) but trip on a real regression (two
  misses → `0.833`); never lowered to paper over a regression
  (`BASELINE.md:57-76`, `test_retrieval_eval.py:40-47`).
- **Record cost, gate correctness.** Mean tokens-to-answer is printed but not asserted — a cost
  signal, not a correctness one (`BASELINE.md:75-76`).
- **Build once per module.** `build_all` (tree-sitter parse + graph + cluster) is the costly
  step, so the index is a `scope="module"` fixture shared by all three tests
  (`test_retrieval_eval.py:60-67`).
- **Marked `@pytest.mark.integration`.** It crosses into the real filesystem build pipeline;
  `--strict-markers` requires the explicit marker (`testing.md:22,49`).

## Open questions

- **Baseline re-observation cadence.** `BASELINE.md` is the rationale of record, updated only on a
  deliberate re-observation — but nothing automates detecting that `query()` scoring legitimately
  improved (raising the achievable baseline). Today that re-observation is manual.
- **Corpus breadth.** 12 positives over 3 sample features is enough to make the floors meaningful,
  but the margins are tuned to exactly this count (`BASELINE.md:69-75`); growing the corpus would
  require re-deriving the margins.
- **Frozen-index fidelity.** Gating the `SAMPLE_REPO` index trades realism for determinism; a
  retrieval regression that only manifests on enriched, summary-bearing live indices would not be
  caught here.
