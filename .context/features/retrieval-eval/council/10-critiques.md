## Data integrity

- `tests/eval/test_retrieval_eval.py:46,49,166-169` — the `T_HIT` floor cannot see a ranking slip. The frozen build has exactly 3 features (`community-0/1/2`) and `_TOP_K = 3`, so every scored feature lands in the top 3. hit@3 therefore only measures "the expected feature scored above zero". That is already implied when `test_every_positive_fixture_shares_a_token` (`:248-265`) passes: `_feature_vocab` (`:229-243`) joins `files`/`members`→`symbols.json` the same way the scorer does (`query.py:594-605`), and the scorer matches by substring (`query.py:513,539`). So any vocab-token overlap yields a positive score, and hit@3 = 1.0 by construction unless output is truncated. Only `T_MRR` is a live floor. The calibration "hit@3 tolerates 1 miss" (`plan.md:45-47`) and the low-confidence `BASELINE.md:64-67,74-76` ("falling out of the top-3") describe an event ranking cannot produce here; the code wins, and this conflict is flagged. `plan.md:52-53` ("overlap must match what query scores") also overstates the guard: exact-token overlap is a stricter, sufficient condition, not the scorer's predicate. Fix: gate hit@1, or grow the frozen index past `_TOP_K` features (costly: `SAMPLE_REPO` is shared by 29 modules, `plan.md:24-25`). Otherwise stop presenting `T_HIT` as an independent gate.
- `tests/eval/retrieval_fixtures.json:22-31,37-41` — 3 of 12 positives ("how to format currency for an amount", "parse amount from a text string", "parse_amount float conversion in helpers") score only `community-2`, even at `top_k=100`. They return RR = 1.0 whenever they score at all, so they add no ranking signal. MRR rests on the other 9 positives. The 4 `community-0` positives all hinge on one comparison against `community-1`'s `app.ts` stem (7.27 or 6.78 vs 6.34; the narrowest margin is 0.44, at `:7-11`). Because `app` appears in both the `community-0` and `community-1` vocabularies, mislabeling `:7-11` as `community-1`/`web/app.ts` would still pass the vocab check, the path check (rank 2) and the gate (MRR 0.958). Fix: add a fixture-validation assert that each positive scores ≥2 features, and replace the single-candidate questions with contested ones.
- `tests/eval/test_retrieval_eval.py:127` (with `:46-47`) — `>= 12` lets the corpus grow under fixed percentage floors, so the number of tolerated misses drifts with n (for example, n=20 at 0.90 allows 2). Adding single-candidate fixtures also inflates MRR without adding signal. This is already an open question (`plan.md:67-68`). Fix: express the floors as miss budgets calibrated at n=12 (`misses <= 1`, `sum(1 - rr) <= 1.8`), or pin `== 12`.
- `tests/eval/test_retrieval_eval.py:42-43` — stale baseline: the comment records mean tokens 40.5, but a fresh build at HEAD `0634bfd` measures 43.0 (per-fixture 8–201). The same stale figure is in the low-confidence `BASELINE.md:45`, cited here only as a stale record; the code wins. The metric is ungated, so the gate is unaffected, but the "rationale of record" no longer matches observation and nothing detects the drift. Fix: re-observe and update both, or drop the number from the code comment.
- `tests/eval/test_retrieval_eval.py:136-141` — `result.truncated` is never read. A budget cut (`query.py:379-392`) or a `max_bytes` cut (`query.py:406-425`) therefore registers as a retrieval miss and lowers MRR, with no way to attribute it. There is wide headroom today (max 201 tokens vs 2000). Fix: `assert not result.truncated` for each positive, so that a miss always means a scoring change.

### Resolved since last review

- `benchmarks/retrieval/run_eval.py:101-117` basename gold matching: the package was deleted in `404654a`, and no tracked files remain under `benchmarks/`.
- The benchmark truncation-rejection clause of the prior post-budget bullet (`run_eval.py:163-175`) was deleted with the package. The frozen-gate half carries forward as the `truncated` bullet above.

## Security

- `tests/eval/test_retrieval_eval.py:60-67`, `tests/conftest.py:10-20`, `tests/conftest.py:28-35`. The module-scoped `indexed_repo` is set up before the function-scoped autouse `_isolate_user_config` and `_no_real_plugin_install`. `pytest --setup-plan` prints `SETUP M indexed_repo` ahead of `SETUP F _isolate_user_config`. So `build_all` runs with the developer's real `HOME`/`USERPROFILE`/`CODEX_HOME`/`CLAUDE_CONFIG_DIR` and without `SKIP_INSTALL_ENV`, while every other test in the suite is sandboxed. Today the only real-profile read is git's global config, through the subprocess in the next bullet. If a later change to `build_all` reads or writes user config, this gate will touch the real profile without any test failing. Existing mitigation is incidental:
  - `:66` passes only `cache_root`, so the gate depends on the `bootstrap=False` default (`dummyindex/context/build/runner.py:97`), which skips `reconcile_claude_md` (`runner.py:325-332`). A default protects less than an explicit argument would.
  - `install_default_plugins` has no caller under `context/build/`; its only callers are `dummyindex/cli/init.py:74`, `dummyindex/cli/wire.py:243` and `dummyindex/installer/install/project_init.py:372`.
  - A grep of `dummyindex/context/build/` and `domains/features/` finds no `Path.home()` call and no import of `hooks`, `claude_plugins`, `default_plugins`, `usage` or `installer`.

  None of this isolates the fixture, because the conftest sandbox does not cover module scope.
- `tests/eval/test_retrieval_eval.py:66` → `dummyindex/context/build/runner.py:172` → `dummyindex/context/build/git_delta.py:56-66`, `:289-312`. Every gate run spawns `git -C <copy> rev-parse HEAD`. The copy has no `.git`, so git searches upward from the pytest basetemp. Under a `--basetemp` inside a checkout, or a home directory that is itself a git repo, git reads that enclosing repo's `.git` and config and stamps an unrelated HEAD into the throwaway `meta.json` `indexed_commit`. Nothing is written to the enclosing repo, and `query` never reads `indexed_commit`, so gated metrics are unaffected. Existing mitigation:
  - an argv list with no shell and `capture_output`;
  - a non-zero exit, `FileNotFoundError` or `OSError` maps to `None`;
  - the default basetemp lies outside any repo: verified on this host (`%LOCALAPPDATA%\Temp` and `%USERPROFILE%` both exit 128), and CI `.github/workflows/tests.yml:33` passes no `--basetemp`.

  No mitigation stops the upward search itself, because `GIT_CEILING_DIRECTORIES` is never set. The record and the code disagree here. The prior `concerns.md:13` blamed only the deleted benchmark for voiding the "no-subprocess" verdict, but the code shows the gate itself is not subprocess-free. `plan.md:22-25` is accurate about the imports; it just does not mention this subprocess.
- `tests/eval/test_retrieval_eval.py:65`, `tests/paths.py:14`. `shutil.copytree(SAMPLE_REPO, dest)` keeps the default `symlinks=False`, so it copies the working tree, untracked files included, and follows links. A symlink added to the fixture would pull content from outside the repo into the indexed copy, where its names can reach citations and the printed failure messages. The fixture is shared with 29 modules, and a stray `tests/fixtures/sample_repo/.context/` is not gitignored (`git check-ignore` gives no match). Per feature, scaffolding rewrites `feature.json`, `spec.md` and `flows/` (`dummyindex/context/domains/features/builder.py:257-274`) plus `docs.md` (`dummyindex/context/domains/features/docs.py:88`), and it never clears the folder first: `_rmtree` is called only from `placement.py:275` and `ops.py:245`. A leftover `features/community-N/plan.md` or `concerns.md` would therefore survive and could feed `_excerpt_from_feature` (`dummyindex/context/domains/query.py:723-754`). That shifts excerpts and the ungated `total_estimated_tokens`; no impact on hit@3 or MRR is shown. Existing mitigation: none in code. The tree is clean today: 3 tracked files, no links (`find -type l` is empty, no mode-120000 entries) and no `.context/`. A stray `.context/` would show as untracked in `git status`.

### Resolved since last review

- `benchmarks/retrieval/run_eval.py:27-88`: networked Git/Python subprocesses with pinned checkouts. Resolved by deletion in `404654a`; the orphaned tests were dropped in `ddcb605`. Only untracked `benchmarks/__pycache__` residue remains, and `benchmarks/retrieval/` is gone. The frozen-gate half of that bullet still holds and was re-verified:
  - the gate writes only into a fresh pytest copy (`tests/eval/test_retrieval_eval.py:63-66`), with `cache_root=base / "cache"`;
  - the trusted cache override is restored in `finally` (`dummyindex/context/build/common.py:185-190`);
  - `query.py` has no write calls;
  - nothing on the build path uses the network.

  The "no-subprocess" verdict does not return; see the git bullet above.
- `benchmarks/retrieval/run_eval.py:51-88`: a reused `.git` destination was force-rebuilt. Resolved by deletion.

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

## Cross-review

Verified against the cited `path:range` plus a probe (`build_all` on a fresh `SAMPLE_REPO` copy, each question at `top_k=3` and `top_k=100`) and `pytest --setup-plan`. Source lines are cited at HEAD `0634bfd`. The working tree has uncommitted comment-only edits to `query.py`, `builder.py` and `git_delta.py`, so the probe reproduces HEAD behavior.

### Confirmed

- **[HIGH] hit@3 saturation** (database #1, product #1): the probe returns exactly 3 features and no `top_k=100` result exceeds 3, and `_TOP_K = 3` (`:49`). The vocab check uses exact `tokenize` tokens, and those imply a substring hit in the scorer (`query.py:513` basename, `:539` symbol; IDF floor 0.25 > 0). So `T_HIT` can fail only through truncation. MRR slip math holds: 10.5/12 = 0.875 passes and 10/12 = 0.833 fails. `plan.md:45-47` and `BASELINE.md:64-67` describe a miss that cannot happen.
- **Single-candidate positives** (database #2): `retrieval_fixtures.json:22-26`, `:27-31` and `:37-41` score only `community-2` at `top_k=100`. The 4 `community-0` positives lead `community-1` 7.27/6.78 vs 6.34 (minimum margin 0.44). The relabel scenario was checked by hand: `app` is in `community-1`'s vocab, `web/app.ts` is cited at rank 2, and MRR = 11.5/12 = 0.958.
- **Stale 40.5** (database #4, product #4): `:42-43` and `BASELINE.md:45` say 40.5; the probe gives mean 43.0, total 516, max 201 (`startWebApp entry point that calls mount`), and `truncated=False` for all 13 questions.
- **`truncated` unread** (database #5, product #4): `:136-141` never reads it. Budget loop at `query.py:382-392`, byte cap at `query.py:406-425`.
- **Fixture scope** (security #1): `--setup-plan` prints `SETUP M indexed_repo` before `SETUP F _isolate_user_config` / `_no_real_plugin_install`. No `Path.home()`/`expanduser` on the build path (the only memory import, `ensure_memory_store`, writes under `context_dir`). `install_default_plugins` callers are `cli/init.py:74`, `cli/wire.py` and `installer/install/project_init.py:372` only.
- **git upward search** (security #2): `runner.py:172` → `head_commit` (`git_delta.py:56-66`) → `_run_git` (`:289-312`), argv list, no shell. `GIT_CEILING_DIRECTORIES` appears nowhere in `dummyindex/` or `tests/`.
- **copytree / stray `.context/`** (security #3): the fixture has 3 tracked files; `git check-ignore` on `tests/fixtures/sample_repo/.context/x` reports no match. The build writes `feature.json` and `spec.md` only (`builder.py:284-291`). From the data-integrity side, leftovers reach excerpts and tokens but not scores, because `INDEX.json`, `feature.json` and `map/symbols.json` are all rewritten.
- **CI discards metrics / id churn** (product #2, #3): `tests.yml:33` runs without `-s`, and `pyproject.toml:81` sets `addopts = ["-ra", ...]`. Ids are assigned at `builder.py:127-131`. 29 test modules import `SAMPLE_REPO`, which is 28 besides this one.

### Refuted

- None outright.
- Refined: product #1 says hit@3 "fails only when the expected feature scores 0 or the budget drops it". Once the vocab test passes, a zero score is impossible, so truncation is the only path.
- Refined: database #1 says `plan.md:52-53` overstates the guard. That is correct: exact-token overlap is sufficient for a score, not the scorer's predicate (substring plus synonyms).

### Merged

- Database #1 + product #1 → concerns Data #1 (hit@3 saturation, MRR slip count).
- Database #3 + product #3 tail (`>= 12` under fixed floors) → Data #3.
- Database #5 + product #4 tail + prior Data #2 frozen-gate half (`truncated` unread) → Data #4.
- Database #4 + product #4 head (stale 40.5 vs 43.0) → Product #3.
- Prior Security #1 frozen-gate half (fresh copy, cache override restored) → kept as mitigation context; the "no-subprocess" verdict stays void (Security #2).

### Dropped

- Prior Data #1 (`run_eval.py:101-117` basename gold matching).
- Prior Data #2 benchmark clause (`run_eval.py:163-175` truncation rejection).
- Prior Security #1 benchmark half (`run_eval.py:27-88` networked pinned checkouts).
- Prior Security #2 (`run_eval.py:51-88` reused `.git` destination).
- Prior Product #2 (first-run benchmark cost).
- Prior Product #3 (clean benchmark exit read as approval).
- All were resolved by deleting `benchmarks/` in `404654a`; the orphaned tests were dropped in `ddcb605`.

### Anchor corrections

- The critics mixed anchors. `builder.py:93-113`, `builder.py:257-264` and `query.py:594-605` are working-tree lines; at HEAD they are `builder.py:127-131`, `:284-291` and `query.py:620-632`.
- `cli/wire.py:243` is HEAD; it is `:210` in the working tree.
- `query.py:237`, `:294-301`, `:379-392`, `:406-425`, `:513`, `:539` and `:723-754` are HEAD lines, consistent with `plan.md`.
