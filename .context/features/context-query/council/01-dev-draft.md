# Context retrieval query — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/context/domains/query.py:108-271` holds synonym expansion,
  tokenization and frozen result records; `:294-425` orchestrates retrieval and
  bounds complete output records.
- `dummyindex/context/domains/query.py:428-633` computes IDF, scores features and
  joins feature members/files to one parsed symbol map. `:636-780` constructs
  citations and excerpts; `:786-837` renders both output formats.
- `dummyindex/cli/query.py:10-126` owns flags, output and exit codes.
- `tests/context/domains/test_query.py:339-483` isolates ranking signals with
  synthetic indexes. `tests/eval/test_retrieval_eval.py:117-206` supplies the
  frozen correctness gate; `benchmarks/retrieval/run_eval.py:121-184` is the
  separate pinned real-repo experiment runner.

## Architecture in three sentences

`query` validates limits, resolves the context directory, tokenizes/expands the
question and loads feature metadata plus one symbol map. It derives per-feature
names/files, calculates IDF and stable float rankings, then builds cited
matches under the estimated token budget. A final pass removes whole trailing
matches until both renderings fit `max_bytes`; the CLI prints one renderer and
returns hit/no-hit/error status.

## Scoring data

Inputs are read-only: `features/INDEX.json` supplies feature metadata,
`features/<id>/feature.json` supplies owned members and fallback files, and
`map/symbols.json` supplies names, paths and ranges. Missing or unreadable
optional symbol/feature files degrade the corresponding signals; a missing
feature index remains a hard error
(`dummyindex/context/domains/query.py:313-358`,
`dummyindex/context/domains/query.py:576-633`).

Each query token receives `max(0.25, ln(1 + N / (1 + df)))`, where `df` counts
features matching that token in their ID, name, summary, basenames or symbol
names. A token's field contributions are multiplied by this IDF
(`dummyindex/context/domains/query.py:428-458`). The weights are:

| Signal | Weight before IDF |
|---|---:|
| Feature name | 5 |
| Summary | 3 |
| Feature ID | 1 |
| Basename substring, per file | 2 |
| Exact basename stem, additional | 6 |
| Matching directory segment, once per token/file | 1 |
| Symbol contribution | 1.5 |

Symbol contributions sum matching token IDFs, retain the five largest
contributions and multiply by `1 / (1 + ln(1 + symbol_count))`. The displayed
symbol list independently keeps eight names ranked by token coverage and name;
the navigable file list keeps twenty paths. Zero-score features are omitted;
the final order is `(-score, feature_id)`
(`dummyindex/context/domains/query.py:461-573`).

## I/O reuse and output decisions

`_load_symbols_by_id` parses the symbol map once per nonempty query, and the
same dictionary feeds scoring and citation construction. This is per-query
reuse, not a cache across calls. `_index_symbols_by_feature` loads each feature
record for names and files; `_symbol_paths` still rereads a selected feature's
record to recover its member set, but never reparses the symbol map
(`dummyindex/context/domains/query.py:351-358`,
`dummyindex/context/domains/query.py:576-633`,
`dummyindex/context/domains/query.py:687-720`).

Canonical directories are constructed from the resolved context root and feature
ID. Entry `path` remains display metadata; it does not redirect excerpt reads
(`dummyindex/context/domains/query.py:313-316`,
`dummyindex/context/domains/query.py:470-473`,
`dummyindex/context/domains/query.py:645-650`). Excerpts keep the fixed curated
document order. Under token pressure the excerpt shrinks while citations remain;
the later byte guard can remove a whole match. Both formats remain complete,
and callers must check `truncated` before treating output as an exhaustive top-K
result (`dummyindex/context/domains/query.py:379-425`,
`dummyindex/context/domains/query.py:665-780`).

## Verification and open questions

Synthetic regressions cover file fallback, size normalization, rare-token IDF,
exact stems, synonyms, directories and top-five symbol contributions
(`tests/context/domains/test_query.py:339-483`). The byte-bound and canonical-path
guards are at `tests/context/domains/test_query.py:63-67` and `:273-279`.
The frozen eval keeps its existing correctness floors; historical benchmark
scores are not a fresh measurement of this integrated release. Token cost
remains a character heuristic, and index-schema corruption outside the optional
read fallbacks is not normalized into a new error type by this change.
