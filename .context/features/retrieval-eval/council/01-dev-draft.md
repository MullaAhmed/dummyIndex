# Correctness-gated retrieval eval — plan

`confidence: INFERRED`

## Where it lives

- `tests/eval/test_retrieval_eval.py` — fixture, helpers and the three tests.
- `tests/eval/retrieval_fixtures.json` — the authored question corpus.
- `tests/eval/BASELINE.md` — rationale record for the floors.
- `tests/eval/__init__.py` — empty package marker.

`tests/eval/` also holds the behavior gate (`behavior_gate.py`,
`behavior_arms.py`, `BEHAVIOR_BASELINE.md`). It is owned separately, and none of
this feature's floors apply to it (`tests/eval/BASELINE.md:3-6`).

## Architecture in three sentences

The module-scoped `indexed_repo` fixture copies `SAMPLE_REPO` into a temp dir
and runs `build_all(dest, cache_root=...)` once
(`tests/eval/test_retrieval_eval.py:60-67`,
`dummyindex/context/build/runner.py:92-100`). Each test loads the JSON corpus,
calls production `query`/`tokenize` against `<copy>/.context`, and evaluates the
result with pure helpers (`tests/eval/test_retrieval_eval.py:36-38`, `:89-109`,
`:216-245`). The pattern is a black-box evaluator: it imports production code
one way only, and production code never imports it.

## Data model

None persisted. The tests read the freshly built index: `features/INDEX.json`
through `query`, and `features/<id>/feature.json` (`files`, `members`) plus
`map/symbols.json` (joined on `symbol_id` or `node_id`) for the vocabulary check
(`tests/eval/test_retrieval_eval.py:226-243`).

## Key decisions

- **Frozen sample index, not the live `.context/`.** Live cluster IDs change
  when the index is rebuilt. `SAMPLE_REPO` yields stable `community-0/1/2` for
  `app.py`, `web/app.ts` and `helpers.py` (`tests/eval/test_retrieval_eval.py:3-9`).
- **The path is checked through citations.** The built `INDEX.json` has no
  `files` key, so `expected_path` can only surface in `match.citations`
  (`tests/eval/test_retrieval_eval.py:23-25`, `:97-109`). The code's stated
  reason is that paths survive re-clustering while IDs do not (`:143-144`).
- **Fixed floors with headroom.** `T_HIT = 0.90` tolerates 1 miss in 12;
  `T_MRR = 0.85` absorbs about 3 single-rank slips (`tests/eval/BASELINE.md:62-81`,
  a low-confidence historical record; the constants at
  `tests/eval/test_retrieval_eval.py:46-47` are authoritative). Mean tokens are
  recorded but not asserted (`:13-16`, `:157-163`); `BASELINE.md:80-81` calls
  them a cost signal.
- **The negative control asserts the strongest form.** The test requires
  `matches == ()`, not just a missing target, so the gate cannot pass by
  matching every question (`tests/eval/test_retrieval_eval.py:201-206`).
- **The vocabulary check uses the scorer's own `tokenize`.** Fixture overlap
  then matches what `query` can score, which matters because `summary` is null
  in the frozen index (`tests/eval/test_retrieval_eval.py:216-223`, `:248-255`).
- **The gate ranks post-budget output.** It uses `query` defaults
  `budget_tokens=2000`, `max_bytes=16_000`
  (`dummyindex/context/domains/query.py:294-301`) and never reads
  `QueryResult.truncated` (`dummyindex/context/domains/query.py:237`). A budget
  change can therefore move the gate even when scoring is unchanged.

## Open questions

- The docstring cites "Contract §4, Decision D5" of a spec
  (`tests/eval/test_retrieval_eval.py:3`). No such spec is in the repo, so the
  original acceptance text cannot be checked.
- Mean tokens drift. The comment at `tests/eval/test_retrieval_eval.py:42-44` and
  `tests/eval/BASELINE.md:45` record 40.5, but HEAD prints 43.0. The value is
  not gated, and neither record has been re-observed.
- The ≥12 guard allows the corpus to grow while the floors stay fixed
  (`tests/eval/test_retrieval_eval.py:127`). It is unclear whether the margin
  rationale should be recalculated when fixtures are added.
