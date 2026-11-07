# Correctness-gated retrieval eval — concerns

`confidence: INFERRED`

Bare `:N` = `tests/eval/test_retrieval_eval.py`; `query.py` = `dummyindex/context/domains/query.py`; `builder.py` = `dummyindex/context/domains/features/builder.py`. Source lines cite HEAD `0634bfd`.

## Data integrity

- **[HIGH]** `:43,46,155-158` — hit@3 is saturated: 3 features at `_TOP_K = 3`, and the vocab check (`:232-249`) already forces a nonzero score (substring scorer, `dummyindex/context/domains/query.py:487,513`), so `T_HIT` trips only on truncation; `T_MRR` is the sole rank floor (3 rank-2 slips = 0.875 pass, 4 = 0.833 fail). — Gate hit@1 or a rank-1 miss budget; stop calling `T_HIT` a ranking floor (`.context/features/retrieval-eval/plan.md:45-47`, `.context/features/retrieval-eval/spec.md:9-10`).
- `tests/eval/retrieval_fixtures.json:22-31,37-41` — 3 of 12 positives score only `community-2` even at `top_k=100`, so RR = 1.0 by construction; relabeling `:7-11` to `community-1`/`web/app.ts` still passes vocab, path and gate (MRR 0.958). — Assert each positive scores ≥2 features; swap single-candidate questions for contested ones.
- `:117` with `:43-44` — `>= 12` lets n grow under fixed percentage floors, so tolerated misses drift (n=20 at 0.90 allows 2) and single-candidate additions inflate MRR (`.context/features/retrieval-eval/plan.md:67-68`). — Floors as miss budgets calibrated at n=12 (`misses <= 1`, `sum(1 - rr) <= 1.8`), or pin `== 12`.
- `:126-131` — `result.truncated` is never read, so a budget cut (`dummyindex/context/domains/query.py:356-366`) or byte cut (`dummyindex/context/domains/query.py:380-399`) reports as "retrieval regression"; headroom is wide today (max 201 of 2000 tokens). — `assert not result.truncated` per positive, so a miss always means a scoring change.

## Security

- `:54-61`, `tests/conftest.py:10-20,28-35` — module-scoped `indexed_repo` sets up before the function-scoped autouse sandbox (`--setup-plan`), so `build_all` sees the real `HOME`/`USERPROFILE`/`CODEX_HOME`/`CLAUDE_CONFIG_DIR` and no `SKIP_INSTALL_ENV`; harmless today (`bootstrap=False`, `dummyindex/context/build/runner.py:97,301`). — Isolate inside the fixture via a module-scoped `pytest.MonkeyPatch.context()` before `build_all`.
- `:60` → `dummyindex/context/build/runner.py:157` → `dummyindex/context/build/git_delta.py:32-42,245-268` — `git -C <copy> rev-parse HEAD` on a `.git`-less copy searches upward (`GIT_CEILING_DIRECTORIES` unset) and can stamp an enclosing repo's HEAD into throwaway `meta.json`; no gate impact, but `.context/features/retrieval-eval/plan.md:22-25` omits the subprocess. — Set `GIT_CEILING_DIRECTORIES` to the copy's parent; list the subprocess in `plan.md`.
- `:59`, `tests/paths.py:14` — `copytree` follows symlinks and copies untracked files; a stray `tests/fixtures/sample_repo/.context/` (not gitignored) survives a build that rewrites only `feature.json`/`spec.md` (`dummyindex/context/domains/features/builder.py:257-264`) and feeds `_excerpt_from_feature` (`dummyindex/context/domains/query.py:694-723`); excerpts/tokens only, tree clean today. — `ignore=shutil.ignore_patterns(".context")`; gitignore that path.

## Product surface

- `.github/workflows/tests.yml:33`, `pyproject.toml:81` — a CI pass discards the metrics block (`:147-152`; no `-s`, `-ra` reports non-passed only), so MRR 1.0 → 0.875 looks identical to green; a breach names only the aggregate (`:155-162`). — Put each miss's `(question, rank)` in both assert messages; surface metrics on pass (e.g. `record_property`).
- `tests/eval/retrieval_fixtures.json:4-59`, `dummyindex/context/domains/features/builder.py:109-113` — all 12 positives hard-code clusterer `community-N` ids on a `SAMPLE_REPO` shared with 28 other modules; renumbering fails as "retrieval regression" beside a no-lowering comment (`:39-42`), or as a bare `FileNotFoundError` (`:210-211`) naming no question. — Resolve ids from `expected_path` via `feature.json` `files`, or pre-assert the id→path map with a "fixture ids stale" message.
- `:40-41`, `tests/eval/BASELINE.md:45` — the record every failure message cites says mean tokens 40.5; HEAD measures 43.0 (one fixture = 201 of 516) and, being ungated, nothing caught it. — Update both to 43.0 or drop the number from the comment.

## Cross-review notes

- Confirmed by a working-tree probe: 3 features; no `top_k=100` result exceeds 3; `community-0` leads `community-1` by 0.44–0.93 (7.27/6.78 vs 6.34); mean tokens 43.0; `--setup-plan` order; `GIT_CEILING_DIRECTORIES` appears nowhere; fixture tree = 3 tracked files, no `.context/`.
- Merged: database + product hit@3 → Data #1; database `>= 12` + product id-churn tail → Data #3; database `truncated` + product answer-cost tail → Data #4; database stale 40.5 + product answer-cost head → Product #3.
- Dropped: every prior `benchmarks/` bullet (basename gold matching, truncation rejection, networked pinned checkouts, reused `.git` destination, first-run cost, clean exit read as approval); package deleted in `404654a`.
- Refuted: none. Anchors corrected: critics mixed HEAD and working-tree lines (`dummyindex/context/domains/features/builder.py:93-113,257-264`, `dummyindex/context/domains/query.py:594-605` are working-tree); uncommitted comment-only edits to `query.py`, `builder.py`, `git_delta.py` shift them, so this doc cites HEAD (`dummyindex/cli/wire.py:210` = working-tree `:210`).
