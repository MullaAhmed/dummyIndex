# Context retrieval query — plan

confidence: INFERRED

## Where it lives

- `dummyindex/context/domains/query.py` — the retrieval engine: tokenizer, scorer, excerpt/citation builder, dataclasses, and the two renderers (`query.py:1-583`).
- `dummyindex/cli/query.py` — the `dummyindex context query` argument parser and I/O boundary; prints `render_json`/`render_markdown` and maps results to exit codes (`cli/query.py:1-93`).
- `tests/context/domains/test_query.py` — unit tests for tokenize, scoring, budget, JSON serialization, CLI arg errors.
- `tests/eval/test_retrieval_eval.py` — the protected **retrieval-eval** gate that benchmarks this surface over a frozen `SAMPLE_REPO` index (`tests/eval/test_retrieval_eval.py:1-13`).
- Reads (never writes) `features/INDEX.json`, per-feature `features/<id>/feature.json`, `map/symbols.json`, and the feature's markdown — consistent with the convention that `domains/*` own retrieval logic while I/O stays at the `cli/*` boundary (`.context/conventions/data-access.md`).

## Architecture in three sentences

`tokenize()` reduces the query to lowercase, stopword-filtered, CamelCase/snake-split tokens, then `query()` loads `features/INDEX.json`, joins each feature's `members` against `map/symbols.json` for symbol names, and scores every feature by weighted token overlap against its name (5), summary (3), file basenames (2), symbol names (2 × token count), and feature_id (1) — **no LLM, no embeddings** (`query.py:47-63,210-220,250-326`). Features are sorted by descending score (ties broken by feature_id), the top-K are walked, and for each one `_build_match` emits a query-relevant paragraph excerpt plus citations from the matched symbols' real `path:range`, stopping once the estimated-token running total would exceed `budget_tokens` (`query.py:220-247,373-421`). The result is a frozen `QueryResult` that renders either as markdown (default) or indented JSON via `to_dict()` (`query.py:111-148,534-583`).

## Data model

Scoring inputs, all read-only from `.context/`:

- `features/INDEX.json` → `features[]` with `feature_id`, `name`, `summary`, `path`, `files[]` (`query.py:197-198,257-294`).
- `features/<id>/feature.json` → `members[]` symbol ids (`query.py:357-369,441`).
- `map/symbols.json` → `symbols[]` with `symbol_id`/`node_id`, `name`, `path`, `range` — joined by member id to produce symbol-name hits and citation ranges (`query.py:339-350,451-465`).
- Tunable weights/caps are module constants: `_NAME_WEIGHT`/`_SUMMARY_WEIGHT`/`_FILE_WEIGHT`/`_SYMBOL_WEIGHT`/`_FEATURE_ID_WEIGHT`, `_DEFAULT_TOP_K`, `_DEFAULT_BUDGET_TOKENS`, `_CHARS_PER_TOKEN`, `_MAX_SYMBOL_HITS_KEPT` (`query.py:151-160`).

Output model: frozen dataclasses `FeatureScore` → `QueryMatch` → `QueryResult`, plus `Citation`, each carrying a `schema_version` on the top-level result and a deterministic `to_dict()` (`query.py:84-148`), matching the repo's "frozen dataclass + schema_version + to_dict" serialization convention (`.context/conventions/data-access.md`).

## Key decisions

- **Token-overlap ranking, not semantic search.** Scoring is intentionally simple weighted substring/identifier overlap so it is deterministic, dependency-free, and reproducible — the same answer a tree-walking agent derives by hand (`query.py:11-21`). A token matches a whole identifier or as a substring of a multi-word one; multi-token queries sum (`query.py:267-305`).
- **Gated by retrieval-eval.** `tests/eval/test_retrieval_eval.py` records MRR / hit-rate@3 / mean tokens-to-answer and fails below documented floors (`T_HIT=0.90`, `T_MRR=0.85`) with a permanent negative control, all over the frozen `SAMPLE_REPO` index rather than the live re-clustering `.context/` (`tests/eval/test_retrieval_eval.py:34-39`). Any scoring/tokenizer change must keep that gate green and update `tests/eval/BASELINE.md` if the baseline legitimately moves.
- **Token budget is non-negotiable for citations.** When a block overflows, the excerpt is shrunk but the header and citations are kept, so navigation never drops (`query.py:407-414`).
- **Excerpt read-order is fixed** (`spec.md` first) so the answer favors the curated entry point over historical docs (`query.py:479-487`).
- **CLI exit codes encode hit/no-hit** (0/1) for shell composition; arg/index errors are exit 2 (`cli/query.py:84-93`).

## Open questions

- Symbol-path lookup is recomputed per match (`_symbol_paths`) rather than memoized; the author notes the win is small at K=3 (`query.py:424-432`) — revisit only if top_k grows large.
- `_index_symbols_by_feature` and `_symbol_paths` both parse `feature.json` + `symbols.json`, a deliberate duplication for path/range vs name — could be unified if a third caller appears.
- `--budget` counts an estimate (`chars // 4`); whether that heuristic should track a real tokenizer is left open and is what retrieval-eval's "mean tokens-to-answer" metric would surface if it drifts.
