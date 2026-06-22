# Context retrieval query — plan

confidence: INFERRED

## Bounded context

This feature is the **read side of `.context/`**: a deterministic retrieval engine plus its CLI boundary. It answers "which feature(s) does this question touch, and where in source do I look?" by token-overlap scoring over already-built index artifacts. It owns no writes, no clustering, no LLM, no embeddings — it is the queryable face of the build side, and the surface the protected **retrieval-eval** gate benchmarks.

The boundary is two files split along the repo's I/O-at-the-edge rule (`.context/conventions/data-access.md`):
- `dummyindex/context/domains/query.py` (`query.py:1-583`) — engine: tokenizer, scorer, excerpt/citation builder, frozen dataclasses, two renderers. Reads `.context/` JSON + markdown; emits no files.
- `dummyindex/cli/query.py` (`cli/query.py:1-93`) — `dummyindex context query` arg parser + I/O boundary: parses flags, prints `render_json`/`render_markdown`, maps results to exit codes.

Tests pin both halves:
- `tests/context/domains/test_query.py` — tokenize, scoring, budget truncation, JSON serialization, CLI arg errors.
- `tests/eval/test_retrieval_eval.py:1-13` — the **retrieval-eval** gate; reuses `query()`/`tokenize()` unchanged over a frozen `SAMPLE_REPO` index (spec Decision **D5**).

Inputs (read-only): `features/INDEX.json`, per-feature `features/<id>/feature.json`, `map/symbols.json`, and the feature's own markdown.

## Pattern map (located)

- **Pipeline, single pass** (`query.py:168-247`): `tokenize` → load `INDEX.json` → join members against `symbols.json` → `_score_feature` per feature → sort by `(-score, feature_id)` → walk top-K, `_build_match` each → stop at `budget_tokens`. One function (`query`) orchestrates; helpers are pure.
- **Weighted bag-of-tokens scorer** (`_score_feature`, `query.py:250-326`): query tokens matched against feature name (×5), summary (×3), file basenames (×2), symbol names (×2 per token), feature_id (×1). A token matches a whole identifier or as a substring of a multi-word identifier; multi-token queries sum (`query.py:267-305`).
- **Frozen dataclass + schema_version + to_dict** serialization (`query.py:84-148`): `FeatureScore` → `QueryMatch` → `QueryResult`, plus `Citation`; `SCHEMA_VERSION=1` carried on `QueryResult`; deterministic `to_dict()`. This is the repo-wide artifact convention (`.context/conventions/data-access.md`, "Schema versioning & stable serialization").
- **Two renderers off one model** (`query.py:534-583`): `render_markdown` (default) and `render_json` (`json.dumps(to_dict(), indent=2) + "\n"`) — the CLI picks one; neither re-derives state.
- **Member→symbol join** appears twice for two purposes: `_index_symbols_by_feature` (`query.py:329-369`, name hits) and `_symbol_paths` (`query.py:424-465`, citation `path:range`). Both parse `feature.json` + `symbols.json`.

## Data flow

Read-only, all from `.context/`:

- `features/INDEX.json` → `features[]` with `feature_id`, `name`, `summary`, `path`, `files[]` (`query.py:197-198,257-294`).
- `features/<id>/feature.json` → `members[]` symbol ids (`query.py:357-369,441`).
- `map/symbols.json` → `symbols[]` with `symbol_id`/`node_id`, `name`, `path`, `range`; joined by member id for name hits and citation ranges (`query.py:339-350,451-465`).

Tunables are module constants (`query.py:151-160`): `_NAME_WEIGHT`/`_SUMMARY_WEIGHT`/`_FILE_WEIGHT`/`_SYMBOL_WEIGHT`/`_FEATURE_ID_WEIGHT`, `_DEFAULT_TOP_K=3`, `_DEFAULT_BUDGET_TOKENS=2000`, `_CHARS_PER_TOKEN=4`, `_MAX_SYMBOL_HITS_KEPT=8`.

## Dependencies

**Upstream (this feature reads their output):**
- The build/cluster side that writes `features/INDEX.json`, `features/<id>/feature.json`, and `map/symbols.json`. Query is a pure consumer; it never triggers a rebuild and tolerates a stale index (the code wins, per repo policy).
- A missing `features/INDEX.json` raises `FileNotFoundError`, surfaced by the CLI as "run `dummyindex ingest` first" (exit 2) (`cli/query.py:84-93`) — the one hard upstream coupling.

**Downstream (consumers of this feature):**
- **retrieval-eval** (`tests/eval/test_retrieval_eval.py`) imports `query` and `tokenize` directly and gates them. This is a hard contract: a signature or scoring change here can break the gate. The frozen `SAMPLE_REPO` index carries **no `files` key**, so eval keys positives on **citations + feature-id rank**, not on a `files` field (`test_retrieval_eval.py:23-25`).
- planning/build skills consume the CLI to ground against the existing index — but only via the documented CLI/JSON contract, not internals.

**Cycles:** none. Engine helpers are pure; the only join (member→symbol) is acyclic.

## Decisions (decided X because Y)

- **Decided token-overlap ranking over semantic search** because the answer must be deterministic, dependency-free, and reproducible — identical to what a tree-walking agent derives by hand (`query.py:11-21`). Embeddings would add nondeterminism and a dependency for no navigational gain at this index size.
- **Decided to gate on a frozen `SAMPLE_REPO` index, not live `.context/`** (Decision **D5**) because the live index is un-enriched and re-clusters on rebuild, so its ids are brittle; the frozen fixture has authored ids (`community-0`=`app.py`, etc.) and a stable baseline (`test_retrieval_eval.py:4-9`). Floors `T_HIT=0.90` / `T_MRR=0.85` sit one documented margin below the observed baseline (MRR 1.0, hit@3 1.0, mean tokens 40.5) recorded in `tests/eval/BASELINE.md`; a permanent negative control asserts a known-wrong fixture scores 0 / rank ∞ so the gate is non-vacuous (`test_retrieval_eval.py:14-18`). Any scoring/tokenizer change must keep the gate green and move `BASELINE.md` only when the baseline legitimately shifts.
- **Decided citations are non-negotiable under budget pressure** because navigation must never drop: when a block overflows, `_build_match` shrinks the excerpt but keeps the header and citations (`query.py:407-414`). A match is dropped entirely only when < 80 estimated tokens of budget remain, and the result is marked `truncated` (`query.py:226-237`).
- **Decided excerpt read-order is fixed `spec.md → plan.md → concerns.md → README.md → architecture.md → implementation.md → product.md`** because the curated entry point should win over historical docs (`query.py:479-487`).
- **Decided CLI exit codes encode hit/no-hit (0/1)** because shells compose on "did this find anything?"; arg/index errors are exit 2 (`cli/query.py:84-93`).
- **Decided to recompute the member→symbol join per match rather than memoize** because the win is negligible at K=3 (`query.py:424-432`); revisit only if `top_k` grows large.

## Open questions

- **Budget thresholds are inline literals, not named constants.** The min-block cutoff `80` (`query.py:227`, again `query.py:488`) and the shrink floor `40` (`query.py:525`) are magic numbers, unlike the named caps at `query.py:151-160`. Promoting them to module constants would make the budget contract self-documenting and tunable — but any change must keep retrieval-eval's "mean tokens-to-answer" green.
- **The member→symbol join is parsed twice** — `_index_symbols_by_feature` (names) and `_symbol_paths` (path/range) both read `feature.json` + `symbols.json`. Deliberate duplication for now; unify only if a third caller appears.
- **`estimate_tokens` is `len(text) // 4`, a heuristic, not a real tokenizer** (`query.py:163-165`, `_CHARS_PER_TOKEN`). Whether to track an actual tokenizer is open; retrieval-eval's "mean tokens-to-answer" metric is the early-warning signal if the estimate drifts from reality.
