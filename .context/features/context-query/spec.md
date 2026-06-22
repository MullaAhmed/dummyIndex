# Context retrieval query — spec

confidence: INFERRED

## Intent

Answer "given this question, which feature(s) does it touch, and where in the source should I look?" against an already-built `.context/` index, deterministically and without an LLM. It is the PageIndex-style retrieval surface that grounds planning/build against the existing index — the same JSON a tree-walking agent could read manually, scored by token overlap and returned as a ranked, cited, token-budgeted answer (`dummyindex/context/domains/query.py:1-21`). The CLI is a convenience wrapper; nothing it returns is unavailable to a manual walk (`query.py:8-9`).

The protected **retrieval-eval** feature (`tests/eval/test_retrieval_eval.py`) benchmarks and gates this surface: it reuses `query()` and `tokenize()` unchanged over a frozen `SAMPLE_REPO` index and asserts MRR / hit-rate@3 floors plus a non-vacuous negative control, so any change to scoring here must keep that gate green (`tests/eval/test_retrieval_eval.py:1-13,37-39`). The doc `dummyindex/skills/retrieval/00-overview.md` (DocConfidence.HIGH) describes this as PageIndex-style tree search; its `query` reference matches `map/symbols.json` and is consistent with the code.

## User-visible behavior

`dummyindex context query "search text" [--top-k N] [--budget N] [--json]` (usage string, `dummyindex/cli/query.py:64-70`).

- **Query string** — everything left after flags are stripped, joined on spaces; both `query "..."` and `query find auth` shapes work (`cli/query.py:18-21,60-72`). Empty after stripping → `error: empty query`, exit 2 (`cli/query.py:73-75`).
- **`--top-k N`** (default 3, `query.py:152`) — max features returned. Accepts `--top-k N` and `--top-k=N`; non-integer → `error: --top-k must be an integer`, exit 2 (`cli/query.py:32-45`).
- **`--budget N`** (default 2000 tokens, `query.py:153`) — estimated-token cap across all returned blocks. Same two spellings and integer validation (`cli/query.py:46-59`). When the running total leaves < 80 tokens of room a further match is dropped and the result is marked `truncated` (`query.py:226-237`).
- **`--json`** — emit `render_json` (indented `to_dict()`) instead of the default `render_markdown` (`cli/query.py:29-30,91`; `query.py:582-583`).
- **Cited excerpts** — each match renders feature name · id · score, summary, matched tokens, one most-relevant paragraph excerpt drawn from the feature's own markdown (read order `spec.md → plan.md → concerns.md → README.md → architecture.md → implementation.md → product.md`), and a `Citations:` list of `` `path:line` `` entries labelled with the matching symbol (`query.py:469-487,534-579`).
- **No-hit / stopword-only** — markdown explains zero matches or a query that reduced to zero tokens after stopword filtering (`query.py:536-548`).
- **Exit codes** — `0` when ≥1 match, `1` when no match (so shells can detect "no hit"), `2` on usage/arg errors, and `2` with a "run `dummyindex ingest` first" message if `features/INDEX.json` is absent (`cli/query.py:84-93`).

## Contracts

Public functions/types in `dummyindex/context/domains/query.py`:

- `tokenize(text: str) -> tuple[str, ...]` — lowercase tokens, stopwords + 1-char tokens dropped, CamelCase/snake_case split, deduped (`query.py:47-63`).
- `estimate_tokens(text: str) -> int` — `len(text) // 4` with a floor of 1 (`query.py:163-165`).
- `query(context_dir: Path, query_text: str, *, top_k: int = 3, budget_tokens: int = 2000) -> QueryResult` — scores every feature, returns ranked budget-capped matches; raises `FileNotFoundError(features/INDEX.json)` when the index is missing (`query.py:168-247`).
- `render_markdown(result: QueryResult) -> str` — default CLI rendering (`query.py:534-579`).
- `render_json(result: QueryResult) -> str` — `json.dumps(to_dict(), indent=2) + "\n"` (`query.py:582-583`).
- Frozen dataclasses: `FeatureScore` (`query.py:84-93`), `Citation` (`query.py:96-100`), `QueryMatch` (`query.py:103-108`), `QueryResult` with `to_dict() -> dict[str, Any]` (`query.py:111-148`).
- CLI entry `run(args: list[str]) -> int` (`cli/query.py:7-93`).
- Module constant `SCHEMA_VERSION = 1` carried on every `QueryResult` (`query.py:31,113`).

## Examples

```
$ dummyindex context query "how does auth work" --top-k 2
# query: 'how does auth work'

_2 match(es), ~120 tokens._

## Auth  ·  `community-3` (score 13)

**Matched tokens:** `auth`, `work`

…best paragraph from the feature's spec.md…

**Citations:**

- `app/auth.py:42` — `authenticate`
```

```
$ dummyindex context query "ParseBodyV2" --json
{ "schema_version": 1, "query": "ParseBodyV2", "tokens": ["parsebodyv2","parse","body","v2"], ... }
```

```
$ dummyindex context query "the and of"   # pure stopwords
# query

_(query reduced to zero tokens after stopword filtering — nothing to look up.)_
# exit 1
```
