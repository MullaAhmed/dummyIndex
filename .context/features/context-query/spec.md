# Context retrieval query — spec

`confidence: INFERRED`

## Intent

Turn a question into a ranked, cited shortlist of features in an existing `.context/` index. Retrieval is deterministic and read-only. It helps an agent choose where to inspect source without invoking an LLM or rebuilding the index.

## User-visible behavior

`dummyindex context query "search text" [--top-k N] [--budget N] [--max-bytes N] [--json]`

Accepts quoted text or joins remaining positional words. Flags accept separate and `=` values. Unknown flags, missing query text and invalid values are usage errors (`dummyindex/cli/query.py:10-102`). Defaults are three features, 2,000 estimated tokens and 16,000 UTF-8 bytes. `top_k` must be 1..100. The token budget must be positive. `max_bytes` must be 512..65,536. Query text is limited to 2,048 UTF-8 bytes (`dummyindex/context/domains/query.py:274-312`).

Tokenization removes stopwords and one-character tokens. It keeps distinct whole/CamelCase/snake_case forms. It expands a small synonym map once. So `config` also matches `settings`. Result tokens expose that expansion (`dummyindex/context/domains/query.py:108-200`). Scores are floating-point, IDF-weighted overlap signals. They come from feature names, summaries, IDs, file basenames, directory segments and the five strongest size-normalized symbol hits. When the feature index omits files, retrieval reads the owning `feature.json` file list. Equal scores sort by feature ID (`dummyindex/context/domains/query.py:355-377`, `dummyindex/context/domains/query.py:428-633`).

Each match supplies a feature summary, matched tokens, a relevant paragraph and source citations. Symbol citations use the parsed symbol map. Up to five additional bare file paths remain navigable. Excerpts come from the canonical `features/<feature_id>/` directory. The fixed order is `spec.md`, `plan.md`, `concerns.md`, `README.md`, `architecture.md`, `implementation.md`, `product.md` (`dummyindex/context/domains/query.py:636-754`). The context root resolves to its canonical absolute path before reads, including missing-index diagnostics (`dummyindex/context/domains/query.py:313-316`, `tests/context/domains/test_query.py:273-279`).

The token estimate is `len(text) // 4`, with a floor of one. Token budgeting shrinks excerpts and stops adding blocks when little budget remains. Citations are retained, so this estimate is not a strict tokenizer-based output limit.

The byte limit is strict for both JSON and Markdown. Whole trailing matches are removed, and `truncated` becomes true until both renderings fit. Metadata that cannot fit raises a usage error. It never returns broken JSON (`dummyindex/context/domains/query.py:289-291`, `dummyindex/context/domains/query.py:379-425`, `dummyindex/context/domains/query.py:665-683`).

The CLI exits `0` for a match. `1` covers no matches or stopword-only input. `2` covers usage errors or a missing index. The missing-index message recommends `dummyindex ingest`. Other argument errors use the usage hint (`dummyindex/cli/query.py:104-126`). JSON stays at schema version 1. It includes expanded tokens, float scores, citations, estimated costs and truncation state (`dummyindex/context/domains/query.py:230-271`).

## Contracts

- `query(context_dir: Path, query_text: str, *, top_k: int = 3,
  budget_tokens: int = 2000, max_bytes: int = 16_000) -> QueryResult`
  raises `FileNotFoundError` for absent `features/INDEX.json` and `ValueError`
  for invalid limits (`dummyindex/context/domains/query.py:294-316`).
- `tokenize(text: str) -> tuple[str, ...]` and
  `estimate_tokens(text: str) -> int` are reusable public helpers
  (`dummyindex/context/domains/query.py:168-184`,
  `dummyindex/context/domains/query.py:289-291`).
- Frozen `FeatureScore`, `Citation`, `QueryMatch`, `QueryResult` records and
  `QueryResult.to_dict()` carry results. `render_markdown(result)` and
  `render_json(result)` return newline-terminated text
  (`dummyindex/context/domains/query.py:203-271`,
  `dummyindex/context/domains/query.py:786-837`).
- CLI `run(args: list[str]) -> int` parses, prints and maps outcomes to exits
  (`dummyindex/cli/query.py:10-126`).

## Example

On a synthetic index, the feature owns `src/settings.py`. Its index entry has no `files`. `query(context_dir, "config")` expands `settings`. It uses the per-feature file list and returns the matching feature. This behavior is pinned by `tests/context/domains/test_query.py:339-352` and `tests/context/domains/test_query.py:421-435`. A caller can render the same result as JSON or Markdown. A sufficiently small byte budget can drop complete matches and report `truncated` without invalidating either rendering.
