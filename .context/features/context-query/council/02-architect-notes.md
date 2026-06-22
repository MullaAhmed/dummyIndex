# Architect notes — context-query (stage 2)

## What I changed

- Replaced the loose "Where it lives / Architecture in three sentences" framing with a **Bounded context** section that states what the feature owns (read side of `.context/`) and explicitly disowns (writes, clustering, LLM, embeddings).
- Renamed "Architecture" into a **Pattern map** where every pattern carries a `path:range`: pipeline (`query.py:168-247`), weighted bag-of-tokens scorer (`query.py:250-326`), frozen-dataclass serialization (`query.py:84-148`), two-renderers-off-one-model (`query.py:534-583`), and the twice-used member→symbol join (`query.py:329-369` / `424-465`).
- Split the flat "Open questions" upstream/downstream confusion into a real **Dependencies** section: upstream (build side + the `FileNotFoundError`→exit-2 coupling), downstream (retrieval-eval hard contract + CLI consumers), and an explicit **Cycles: none**.
- Cut filler ("three sentences", restated weights) and tightened the data-flow list.

## Patterns named

- Single-pass pipeline — `query.py:168-247`.
- Weighted bag-of-tokens scorer (name×5 / summary×3 / files×2 / symbols×2-per-token / id×1) — `_score_feature`, `query.py:250-326`.
- Frozen dataclass + `schema_version` + `to_dict()` (repo-wide, per `.context/conventions/data-access.md`) — `query.py:84-148`.
- Two renderers off one model — `render_markdown`/`render_json`, `query.py:534-583`.
- Member→symbol join (two purposes) — `_index_symbols_by_feature` `query.py:329-369`; `_symbol_paths` `query.py:424-465`.

All named symbols cross-checked against `map/symbols.json`: `tokenize@47`, `query@168`, `_score_feature@250`, `_index_symbols_by_feature@329`, `_build_match@373`, `_symbol_paths@424`, `_excerpt_from_feature@469`, `render_markdown@534`, `render_json@582`, `run@7` (cli) — all present, ranges match.

## Dependencies surfaced

- **Upstream:** build/cluster side that emits `features/INDEX.json`, `feature.json`, `map/symbols.json`. Pure consumer; tolerates staleness. Hard coupling: missing `INDEX.json` → `FileNotFoundError` → CLI "run `dummyindex ingest` first", exit 2 (`cli/query.py:84-93`).
- **Downstream:** retrieval-eval (`tests/eval/test_retrieval_eval.py`) imports `query`/`tokenize` directly — signature/scoring changes can break the gate. Surfaced the frozen-index quirk: `SAMPLE_REPO`'s `INDEX.json` has **no `files` key**, so eval keys on citations + feature-id rank (`test_retrieval_eval.py:23-25`). CLI/JSON consumers (planning/build) bind only to the documented contract.
- **Cycles:** none — join is acyclic, helpers pure.

## Decisions promoted

- "token-overlap not semantic" → **decided … because** deterministic/dependency-free/reproducible, no navigational gain from embeddings at this scale.
- "gated by retrieval-eval" → tied to spec **D5**; promoted the *why frozen index* (live re-clusters, brittle ids) and pinned the concrete floors + baseline (`T_HIT=0.90`/`T_MRR=0.85`; baseline MRR 1.0 / hit@3 1.0 / mean 40.5 in `BASELINE.md`) and the non-vacuous negative control.
- "budget non-negotiable" → reframed as **decided citations survive budget because** navigation must never drop; located the drop rule (`query.py:226-237`).
- New open question promoted from reading source: budget thresholds `80` (`query.py:227,488`) and `40` (`query.py:525`) are **inline magic numbers**, unlike the named caps at `query.py:151-160` — candidates for module constants. Flagged a spec/code divergence: spec implies these are constant-driven; the code wins (they are literals).
