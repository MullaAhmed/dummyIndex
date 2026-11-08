# Context retrieval query — plan

`confidence: INFERRED`

## Bounded context and dependencies

This read-only retrieval domain ranks feature records and returns cited excerpts.
`dummyindex/cli/query.py:10-126` owns arguments, rendering choice and exit codes;
`dummyindex/context/domains/query.py:294-425` owns validation and retrieval.
Upstream deterministic/curated files are `features/INDEX.json`, each feature's
`feature.json` and `map/symbols.json`. The graph-storage reader is not on this
query path. Downstream CLI callers, planning/build workflows and retrieval eval
consume the public result; the evaluator does not import back into production.

Missing `INDEX.json` is a hard error. Optional symbol/feature reads catch I/O or
JSON-decoding failure. The fallback loses those signals. It does not validate
arbitrary index schemas (`dummyindex/context/domains/query.py:313-358`,
`dummyindex/context/domains/query.py:576-633`).

## Retrieval pipeline

1. Validate query/top-K/budgets, resolve the context root, tokenize and expand
   synonyms. Parse the symbol map once; join per-feature members into cached
   name tuples and load fallback file lists
   (`dummyindex/context/domains/query.py:108-185`,
   `dummyindex/context/domains/query.py:294-358`,
   `dummyindex/context/domains/query.py:576-633`). This is per-query reuse, not a
   cache across calls.
2. Compute token inverse document frequency (IDF), score each feature and sort
   by `(-score, feature_id)` (`dummyindex/context/domains/query.py:360-377`,
   `dummyindex/context/domains/query.py:428-573`). This weighted ranking pipeline
   is the implementation; no model, embedding or second scoring service runs.
3. Construct citations and excerpts within the estimated token budget. Then
   remove complete trailing matches until both renderers fit `max_bytes`
   (`dummyindex/context/domains/query.py:379-425`,
   `dummyindex/context/domains/query.py:636-780`).

## Scoring decisions

Each token receives `max(0.25, ln(1 + N / (1 + df)))`; `df` counts features whose
ID, name, summary, file basename or symbol name contains the token
(`dummyindex/context/domains/query.py:428-458`). Field contributions multiply
that value by these fixed weights:

| Signal | Weight before IDF |
|---|---:|
| Feature name / summary / feature ID | 5 / 3 / 1 |
| Basename substring, per file | 2 |
| Exact basename stem, additional | 6 |
| Directory segment, once per token/file | 1 |
| Symbol contribution | 1.5 |

Symbol scoring keeps the five largest sums of matching-token IDFs and multiplies
by `1 / (1 + ln(1 + symbol_count))`. This limits incidental hits from large
features; file contributions still accumulate per file. The displayed symbol
list separately keeps eight names by token coverage/name, and file output keeps
twenty paths (`dummyindex/context/domains/query.py:461-573`). These are explicit
ranking policies rather than guarantees of general retrieval quality.

## Output and I/O tradeoffs

Entry `path` is display metadata; canonical feature directories come from the
resolved root and feature ID. The selected feature record is reread for citation
membership, but the symbol map is reused
(`dummyindex/context/domains/query.py:313-316`,
`dummyindex/context/domains/query.py:470-473`,
`dummyindex/context/domains/query.py:636-720`).

Excerpt lookup follows a fixed curated-document order. Token pressure shrinks
excerpts while retaining citations; the final byte guard may drop the entire
match. This preserves complete JSON/Markdown records at the cost of fewer
matches. Metadata alone exceeding the cap raises `ValueError`; callers needing
complete top-K output must inspect `truncated`
(`dummyindex/context/domains/query.py:406-425`,
`dummyindex/context/domains/query.py:665-780`). Character-based token estimates
remain approximate.

## Verification seam

Synthetic tests isolate fallback files, IDF, size normalization, exact stems,
synonyms, directories and top-five symbol scoring
(`tests/context/domains/test_query.py:339-483`). Byte bounds and canonical
missing-index paths have dedicated checks at
`tests/context/domains/test_query.py:63-67` and
`tests/context/domains/test_query.py:273-279`. The frozen correctness gate and
networked benchmark belong to `retrieval-eval`. Historical benchmark scores are
not a new measurement of the combined release.
