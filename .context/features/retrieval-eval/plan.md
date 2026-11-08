# Correctness-gated retrieval eval — plan

`confidence: INFERRED`

Bare `:N` = `tests/eval/test_retrieval_eval.py`; `query.py` = `dummyindex/context/domains/query.py`.

## Where it lives

- `tests/eval/test_retrieval_eval.py` — fixture, helpers, 3 `integration` tests.
- `tests/eval/retrieval_fixtures.json` — 12 positives + 1 negative control.
- `tests/eval/BASELINE.md` — floor rationale of record (`:157`); catalogued `low`.
- `tests/eval/__init__.py` — empty package marker.

## Architecture in three sentences

The module-scoped `indexed_repo` fixture runs `build_all` once on a `SAMPLE_REPO`
copy for 3 tests (`:54-61`), and one JSON corpus, split on its
`negative_control` flag (`:68-75`), is table-driven through `query` (`:123-140`).
Pure helpers `_expected_rank`/`_path_in_citations` score each match (`:78-101`),
the gate asserts threshold floors (`:155-162`), and two guards check the corpus:
a permanent negative control (`:168-193`) and `_feature_vocab`, which
reads built artifacts (`:200-229`). Dependencies are one-way, no cycle:
`build_all` (`dummyindex/context/build/runner.py:92-100`), `query`/`tokenize`
(`dummyindex/context/domains/query.py:271-278`, `dummyindex/context/domains/query.py:147-163`) and `SAMPLE_REPO` (`tests/paths.py:14`,
shared by 29 test modules) are the whole import surface (`:35-37`); downstream
are CI (`.github/workflows/tests.yml:31-33`) and the separate behavior gate's
prose-only citations of `:10` (`tests/eval/behavior_gate.py:5`,
`tests/eval/behavior_arms.py:7` (citation unverifiable)).

## Data model

None persisted; metrics only print (`:111-113`). Besides
`features/INDEX.json` via `query`, the vocab check reads `feature.json`
(`files`, `members`) and `map/symbols.json` (`symbol_id`/`node_id`, `name`)
directly (`:210-227`): a renamed on-disk key empties the vocab and fails at `:245`.

## Key decisions

- **Frozen `SAMPLE_REPO`, not live `.context/`, because live ids re-cluster**
  (`:3-8`; `.context/conventions/testing.md:50`). Corpus ids `community-0/1/2`
  hold only while `tests/fixtures/sample_repo/` and clustering are unchanged.
- **Path asserted via `match.citations`, because `INDEX.json` has no `files` key
  and paths survive re-clustering** (`:22-24`, `:133-134`). Hard fail per hit
  (`:135-140`); a miss only lowers the aggregate.
- **Fixed floors one margin below observed 1.0, never lowered to pass**
  (`:39-44`; `.context/conventions/testing.md:53`). At n=12, hit@3 tolerates 1
  miss (11/12 ≈ 0.917) and fails on 2; a rank 1→2 slip costs ≈0.042 MRR. Mean
  tokens: printed, not gated (`:12-15`).
- **Negative control requires `matches == ()`, because matching everything would
  pass the gate vacuously** (`:174`, `:188-193`). Its real target id
  (`tests/eval/retrieval_fixtures.json:64`) makes absence testable.
- **Vocab check uses production `tokenize`, because overlap must match what
  `query` scores and `summary` is null** (`:203-206`, `:236-238`).
- **No env opt-in, unlike `tests/eval/test_behavior_arms.py:20`:** deterministic
  (`:3`), 0.63s.
- **Unstated (no rationale in code): the gate ranks post-budget output.** Only
  `top_k` is passed (`:126`), so the budget loop (`dummyindex/context/domains/query.py:353-366`) and
  `_bounded_result` (`dummyindex/context/domains/query.py:380-399`) can move it with scoring unchanged;
  `truncated` (`dummyindex/context/domains/query.py:214`) is never read. Now 43 mean tokens vs 2000.

## Open questions

- `:3` cites "Contract §4, Decision D5" (citation unverifiable); no spec in the repo defines it
  (`tests/eval/behavior_gate_fixtures.json:50`'s D5 is unrelated).
- Mean tokens: `:40-42` and `tests/eval/BASELINE.md:45` say 40.5; HEAD `0634bfd` prints
  43.0. Ungated; code wins; neither record updated.
- The `>= 12` guard (`:117`) lets the corpus grow under fixed floors (n=20 at
  0.90 tolerates 2 misses). Recalculate margins on growth?
