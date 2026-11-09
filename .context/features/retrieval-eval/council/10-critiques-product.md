## Product surface

- **A scoring change reorders features without zeroing any** — the built
  sample index holds exactly 3 one-file features (`community-0/1/2`) and the
  gate queries at `top_k=3` (`tests/eval/test_retrieval_eval.py:49`, `:136`),
  so every nonzero-scoring feature lands in the top 3. Hit@3 fails only when
  the expected feature scores 0 or the budget drops it, which is close to what
  `test_every_positive_fixture_shares_a_token` already guards (`:248-265`).
  Spec presents hit@3 as a ranking floor (`spec.md:9-10`, `:19-20`), but MRR is
  the only assertion here that is sensitive to rank. MRR tolerates
  the wrong feature at rank 1 for 3 of 12 questions (3 slips to rank 2: MRR
  10.5/12 = 0.875 ≥ `T_MRR` 0.85, hit@3 1.0, green); 4 slips (0.833) fail
  (`:46-47`, `:152-173`). Hit@1 is not computed. `plan.md:46-48` gives the
  per-slip cost (≈0.042) but not this slips-to-fail count. Probe at `0634bfd`:
  all 4 `community-0` questions lead `community-1` by 0.44–0.93 points
  (7.27/6.78 vs 6.34).
- **A PR lowers MRR from 1.0000 to 0.8750 in CI** — CI runs
  `python -m pytest tests/ -q --tb=short` without `-s`
  (`.github/workflows/tests.yml:31-33`), and `addopts = ["-ra", ...]` reports
  only non-passed tests (`pyproject.toml:81`). On a pass, pytest captures and
  discards the metrics block (`:158-163`), so the run looks the same as a 1.0
  run. Only the documented local command with `-s` shows the numbers
  (`spec.md:16`). When a floor is breached, the assertion names only the
  aggregate and the floor (`:166-173`); no per-question rank is printed
  anywhere, so finding the miss means instrumenting the loop (`:133-150`).
  Citation failures do name the question, the expected path and the actual
  paths (`:145-150`).
- **`tests/fixtures/sample_repo/` or clustering changes renumber
  `community-N`** — feature ids are the clusterer's community numbers
  (`dummyindex/context/domains/features/builder.py:93-113`). All 12 positives
  hard-code them (`tests/eval/retrieval_fixtures.json:4-59`), and 28 other
  test modules share `SAMPLE_REPO` (`tests/paths.py:14`). If ids swap, the gate
  fails with `hit-rate@3 … below floor 0.90 — retrieval regression (see
  tests/eval/BASELINE.md)` (`:166-169`), and the comment forbids lowering the
  floors (`:41-44`). Both point maintainers at scoring, not at fixture ids. A
  merged or missing id raises a bare `FileNotFoundError` from `_feature_vocab`
  (`:226-227`) that names no question. `expected_path`, the key the plan calls
  stable across re-clustering (`plan.md:42-43`), is not used to resolve ids,
  so repair means hand-editing each entry. The `>= 12` guard (`:127`) lets the
  corpus grow under fixed floors, which changes miss tolerance without any
  signal (`plan.md:67-68`).
- **Answer cost grows (excerpt bloat, budget or byte-cap change)** — mean
  tokens-to-answer prints beside the gated metrics (`:163`) but is never
  asserted (`spec.md:21-22`). HEAD prints 43.0, while the comment at `:42-43`
  and the record the failure messages cite (`tests/eval/BASELINE.md:45`) say
  40.5, and nothing failed. `BASELINE.md` is catalogued `confidence: low`
  (`broken_ratio` 0.4444, `.context/source-docs/INDEX.json:3063-3092`). The
  code wins, and the record the failure messages point to is stale. Once
  costs reach the 2000-token budget or the 16 000-byte cap, matches drop
  (`dummyindex/context/domains/query.py:379-392`, `:406-425`). The gate never
  reads `truncated` (`query.py:237`), so a dropped match reports as "retrieval
  regression". In the probe, one fixture (`startWebApp entry point that calls
  mount`) accounts for 201 of the 516 total tokens.

### Resolved since last review

- "Running the pinned benchmark for the first time" — resolved by deletion:
  `benchmarks/` removed in `404654a`; no `benchmarks/**/*.py` at `0634bfd`.
- "Reading a clean benchmark exit as a quality approval" — resolved by the same
  deletion.
- "A ranking change breaches an aggregate floor" — still open; it is carried
  into bullet 2, which adds that a CI pass discards the metrics.
- "Changing fixtures or comparing historical records" — still open; it is split
  into bullets 3 (growth, id churn) and 4 (stale 40.5 record).
