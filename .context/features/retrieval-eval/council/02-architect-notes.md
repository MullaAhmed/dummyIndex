# Architect notes — retrieval-eval (stage 2)

## What I changed

- Reframed "Where it lives" into a **Bounded context** section that names the read-only import
  seam explicitly: three production symbols consumed, zero source changes, one-directional boundary
  (the eval observes `query()`, never reaches into scoring internals).
- **Promoted decisions to the top** and ordered them load-bearing-first: D5 (frozen index) →
  golden-baseline gate → non-vacuous control → stable-signals → cost-vs-correctness → build-once.
  Previously decisions sat below the data model.
- Tightened cited ranges to verified source: gate body `:117-178` (was `:117-173`),
  path-in-citations assertion `:146-150` (was `:145-150`), fixture-split helpers `:74-86` (was
  `:74-81`), `query`/`build_all`/`tokenize`/`SAMPLE_REPO` to single-line def anchors
  (`query.py:168`, `query.py:47`, `runner.py:75`, `tests/paths.py:14`).
- Corrected the corpus count framing: **13 entries (12 positives + 1 negative)** — the raw file has
  13 objects; the old plan said "12 positives + 1 negative" without the total, which read as 13 vs 12
  ambiguously.
- Cut the dropped-in three-sentence "Architecture in three sentences" filler; its content is now
  distributed into Decisions + Components with citations.
- Trimmed Open questions from prose paragraphs to three tight bullets; removed restated rationale.

## Patterns named

- **Golden-baseline gate** — floors as module constants one documented margin below observed
  (`test_retrieval_eval.py:46-49`); margin calibrated to corpus size 12 (`BASELINE.md:66-75`).
- **Non-vacuous negative control** — known-wrong fixture asserted to `result.matches == ()` / rank ∞
  (`test_retrieval_eval.py:181-206`).
- **Stable-signal assertion** — feature-id rank + path-in-`match.citations`, never `community-N` ids
  (`test_retrieval_eval.py:146-150`, `testing.md:50`).
- **Module-scoped build fixture** — `build_all` once per module (`test_retrieval_eval.py:60-67`).

## Dependencies surfaced

- **Gates `context-query`** — consumer-side guard; gate correctness is a pure function of `query()`
  scoring over the frozen index.
- **`SAMPLE_REPO` fixture + `build_all` pipeline** — a change to either shifts authored ids / the
  achievable baseline and invalidates `BASELINE.md`.
- **`tokenize` semantics** — the fixture-quality guard tokenizes feature vocab with public
  `tokenize`; a stop-word/tokenization change can flip a fixture from valid to unanswerable.

## Decisions promoted

- **D5 (frozen `SAMPLE_REPO`, not live `.context/`)** raised to the first decision — it is the
  foundation the other four rest on (re-clustering brittleness is *why* stable-signal assertion and
  authored ids exist).
- **Floors-one-margin-below-baseline never lowered** promoted from a buried clause to a first-class
  decision with the 12-positive calibration (`11/12≈0.917` tolerated, `10/12≈0.833` trips).
- **Record-cost / gate-correctness** kept as an explicit decision so mean-tokens' ungated status is a
  choice on the record, not an omission.
