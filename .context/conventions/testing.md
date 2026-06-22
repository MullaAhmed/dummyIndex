# Testing

How `dummyindex` tests itself. Derived from the real `tests/` tree, `pyproject.toml`, and `.github/workflows/tests.yml` — not generic advice.

## Framework & invocation

Framework is **pytest**, configured in `pyproject.toml:52-64` (`[tool.pytest.ini_options]`). Collection is rooted at `tests/` (`testpaths = ["tests"]`), files match `test_*.py`, and `addopts = ["-ra", "--strict-markers"]` — every marker must be declared or collection fails. Two markers are registered: `unit` and `integration` (`pyproject.toml:61-64`).

CI (`.github/workflows/tests.yml`) is the source of truth for the command. It runs on a **3.10 / 3.12 matrix** and the test step is simply:

```
python -m pytest tests/ -q --tb=short
```

Note the `norecursedirs` override (`pyproject.toml:55-59`): pytest's default skip-list contains `build`, which would silently drop `tests/context/build/` (the mirror of `dummyindex/context/build/`). The override removes it.

## What's unit vs integration vs e2e

Every test carries an explicit `@pytest.mark.{unit,integration}` decorator (≈590 `unit`, ≈422 `integration` across ~100 test modules) — there is **no implicit default**. The split is by I/O boundary, not by directory:

- **unit** — pure, in-process. Call a function directly and assert on its return value. The git-dir parsers in `tests/pipeline/io/test_git.py` are the canonical example: they build on-disk shapes under `tmp_path` and assert `resolve_git_dir`/`is_git_repo` return values with **no subprocess and no real `git`** (`tests/pipeline/io/test_git.py:1-9`). CLI-dispatch tests that call `dispatch([...])` and assert a return code + `capsys` output are also `unit` (`tests/cli/test_cli.py:9-41`).
- **integration** — in-process but crossing into the real filesystem build pipeline: copy `SAMPLE_REPO` into `tmp_path`, call `dispatch(["init", ...])` / `build_all(...)`, and assert the emitted `.context/` artifacts exist (`tests/cli/test_cli.py:43-60`, `tests/eval/test_retrieval_eval.py:60-67`).
- **e2e** — a *subset* of `integration`, distinguished by shelling out to the installed entrypoint via `subprocess.run([sys.executable, "-m", "dummyindex", ...])`. Only two modules do this: `tests/cli/test_ingest_command.py:24-31` and `tests/cli/test_reconcile_gate_e2e.py:61-66`. They exercise the real process boundary (stdin JSON → stdout decision for the hook gate). There is no separate Selenium/browser layer — this is a CLI, so "e2e" means the subprocess. CI adds its own smoke-test of the binary (`tests.yml:32-46`: `--help`, `--version`, `install`, `ingest`, artifact existence).

## Fixtures

Shared fixtures live in `tests/conftest.py`; `tests/usage/` has its own sub-`conftest.py` for the usage corpus. Patterns in use:

- **`tmp_path` / `tmp_path_factory`** everywhere for filesystem isolation. `tmp_repo` is a thin alias (`tests/conftest.py:9-11`).
- **`tests/paths.py`** exports stable anchors — `REPO_ROOT`, `FIXTURES_DIR`, `SAMPLE_REPO` — so deep modules never chain `Path(__file__).parent.parent`.
- **`SAMPLE_REPO`** (`tests/fixtures/sample_repo/`) is the frozen input repo; tests `shutil.copytree` it into `tmp_path` before mutating, so the fixture stays pristine (`tests/cli/test_cli.py:44-53`).
- **Module-scoped build** for expensive setup: `test_retrieval_eval.py:60-67` runs `build_all` once per module (`scope="module"`) because tree-sitter parse + graph + cluster is the costly part.
- **Constructed corpora** over recorded ones: `tests/usage/conftest.py` hand-builds a JSONL corpus with fixed timestamps and token counts so tests assert **exact** numbers.

## Mocking philosophy

Minimal mocking. The repo prefers **dependency injection at the boundary** over `unittest.mock` patching. The default-plugin installer takes a `runner` parameter; tests pass a `_FakeRunner` that records `(argv, cwd)` and returns scripted `RunResult`s — no real `claude` CLI is touched (`tests/context/test_default_plugins.py:204-213`). `monkeypatch` is used sparingly and surgically: the autouse `_no_real_plugin_install` fixture sets `SKIP_INSTALL_ENV` so no test ever shells out to the production plugin path by accident (`tests/conftest.py:14-21`). Pure functions are tested by feeding them filesystem shapes, not mocks.

## Determinism & assertion style

Assertions are on **deterministic, exact output**: exact return codes, exact stdout/stderr substrings via `capsys`, exact emitted artifacts, exact aggregate numbers. The retrieval eval (`tests/eval/`) is **correctness-gated**: it records MRR / hit-rate@3 / mean-tokens and asserts floors set one documented margin below the `BASELINE.md` baseline, plus a permanent **negative-control** fixture asserted to score 0 / rank ∞ so the gate can't pass vacuously (`tests/eval/test_retrieval_eval.py:117-206`).

## Coverage

`pytest-cov>=7.1.0` is a dev dependency (`pyproject.toml:98-101`), but there is **no `--cov` flag in the CI command and no `fail_under` gate** in `pyproject.toml`. Coverage is available locally (`pytest --cov=dummyindex --cov-report=term-missing`) but **not enforced** in this repo. Treat the global 80% rule as aspirational here; the enforced bar is "the suite is green on the 3.10/3.12 matrix."

## Anti-patterns to avoid (repo-specific)

- **Don't add an unmarked test** — `--strict-markers` plus the unit/integration convention means a missing marker is a smell, and an *undeclared* marker fails collection.
- **Don't gate on live `.context/` cluster ids** — they re-cluster on rebuild. Gate on the frozen `SAMPLE_REPO` index or on stable signals like citation **paths**, not `community-N` ids (`tests/eval/test_retrieval_eval.py:1-26,144-150`).
- **Don't shell out to real `claude`/`git`** — inject a fake runner or build the on-disk shape by hand.
- **Don't mutate `SAMPLE_REPO` in place** — copytree into `tmp_path` first.
- **Don't lower the retrieval floors to make a regression pass** — a drop below `T_HIT`/`T_MRR` is a real regression (`tests/eval/test_retrieval_eval.py:40-47`).
