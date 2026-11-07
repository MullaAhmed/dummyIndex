# Architect notes — Correctness-gated retrieval eval

## What I changed

- `plan.md` went from 71 to 68 lines and from 447 to 444 words; it keeps the `confidence: INFERRED` line and all five sections.
- Added a one-line citation key (bare `:N` = `tests/eval/test_retrieval_eval.py`, `query.py` = `dummyindex/context/domains/query.py`). The draft repeated full paths.
- Corrected the draft's claim of "pure helpers (`:89-109`, `:216-245`)". Only `_expected_rank` and `_path_in_citations` are pure (`:85-109`). `_feature_vocab` reads `feature.json` and `map/symbols.json` (`:226-243`).
- Dropped the separate behavior-gate paragraph and its `BASELINE.md:3-6` citation. The boundary now comes from code: the behavior gate imports nothing from this feature and only cites `:11` in prose.
- Folded the draft's "code's stated reason" paraphrases into citations, and rewrote Key decisions as "X, because Y".
- Doc evidence: `tests/eval/BASELINE.md` is catalogued `low` with `broken_ratio` 0.4444, so it is cited only as the rationale of record that the code points to (`:168`, `:172`). I re-derived the floor arithmetic from `T_HIT`/`T_MRR` (`:46-47`) and n=12, not from the BASELINE prose.
- Conflict, code wins: `BASELINE.md:45` and `:42-44` record 40.5 mean tokens. `pytest tests/eval/test_retrieval_eval.py -q -s` on HEAD `0634bfd` printed 43.0000 (MRR 1.0000, hit@3 1.0000, 3 passed in 0.63s).
- Replaced the previous `02-architect-notes.md`, which cited the deleted `benchmarks/retrieval/run_eval.py`.
- Symbols I named that are in `map/symbols.json`: `indexed_repo`, `_expected_rank`, `_path_in_citations`, `_feature_vocab`, `build_all`, `query`, `tokenize`, `_bounded_result`. `SAMPLE_REPO` (`tests/paths.py:14`) and `T_HIT`/`T_MRR` (`:46-47`) are module constants, which the map does not extract, so I checked them in the source.

## Patterns named

- Module-scoped shared fixture: `indexed_repo` runs one `build_all` for all 3 tests (`:60-67`). `.context/conventions/testing.md:32` cites it as the exemplar.
- Table-driven corpus with a discriminator flag: one JSON file, split on `negative_control` (`:74-81`, `tests/eval/retrieval_fixtures.json:66`) and looped at `:133-150`.
- Pure evaluator helpers: `:85-109`.
- Threshold gate: floors at `:46-47`, asserts at `:166-173`.
- Permanent negative control: `:181-206`.
- One-way black-box evaluator: the import surface is `:36-38`, and a grep found no `dummyindex/` module that imports `tests/eval`.
- I named no dispatcher, registry or port/adapter, because none exists here.

## Dependencies surfaced

- Upstream, code: `build_all` (`dummyindex/context/build/runner.py:92-100`), `query` (`query.py:294-301`), `tokenize` (`query.py:168-184`) and `SAMPLE_REPO` (`tests/paths.py:14`).
- Upstream, shared fixture: `tests/fixtures/sample_repo/` holds 3 files and 29 test modules use `SAMPLE_REPO`. A change there can break the hard-coded `community-0/1/2` ids in the corpus.
- Upstream, on-disk schema: the vocab check reads `feature.json` keys `files`/`members` and `symbols.json` keys `symbol_id`/`node_id`/`name` directly (`:226-243`). It does not go through the `query` API.
- Upstream, not scoring: the budget loop (`query.py:379-392`) and `_bounded_result` (`query.py:406-425`) can drop matches without any scoring change.
- Downstream: CI runs the whole `tests/` tree with no marker filter (`.github/workflows/tests.yml:31-33`, Python 3.10–3.12).
- Downstream, prose only: `tests/eval/behavior_gate.py:6` and `tests/eval/behavior_arms.py:7` cite `test_retrieval_eval.py:11` by line number. Any docstring edit above line 11 silently breaks those citations.
- Downstream, conventions: `.context/conventions/testing.md:22,32,50,53` uses this file as its exemplar.
- Cycles: none.

## Decisions promoted

- Frozen `SAMPLE_REPO`, because live ids re-cluster (`:3-9`, `testing.md:50`). Caveat added: the ids are stable only while the shared fixture and the clustering stay unchanged.
- The path is asserted through citations, because `INDEX.json` has no `files` key and paths survive re-clustering (`:23-25`, `:143-144`). It is a hard fail per hit, while a miss only lowers the aggregate (`:145-150`).
- Fixed floors are never lowered to make a regression pass (`:41-47`, `testing.md:53`). Their tolerance is quantified from the constants.
- The negative control requires `matches == ()`, because matching everything would make the gate pass vacuously (`:187`, `:201-206`). Its target is a real id (`retrieval_fixtures.json:64`).
- Metrics are print-only and nothing is persisted, because the pytest `-s` output and the failure report are the consumers (`:121-123`).
- There is no env opt-in, unlike `tests/eval/test_behavior_arms.py:24`. This is a stated fact, not a stated rationale: the suite is deterministic (`:4`) and runs in 0.63s.
- Left marked as unstated: the gate ranks post-budget `query` output and never reads `truncated` (`:136`, `query.py:237`). The code gives no rationale, so I invented none.
