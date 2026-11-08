# Testing

How `dummyindex` tests itself. Derived from the real `tests/` tree, `pyproject.toml`, and `.github/workflows/tests.yml`. Not generic advice.

## Framework & invocation

Framework is **pytest**. Configured in `pyproject.toml:52-64` (`[tool.pytest.ini_options]`). Collection is rooted at `tests/` (`testpaths = ["tests"]`). Files match `test_*.py`. `addopts = ["-ra", "--strict-markers"]`. Every marker must be declared or collection fails. Two markers are registered: `unit` and `integration` (`pyproject.toml:61-64`).

CI (`.github/workflows/tests.yml`) is the source of truth for the command. It runs a **3.10 / 3.12 matrix**. The test step:

```
python -m pytest tests/ -q --tb=short
```

Note the `norecursedirs` override (`pyproject.toml:55-59`). Pytest's default skip-list contains `build`. That would silently drop `tests/context/build/`, the mirror of `dummyindex/context/build/`. The override removes it.

## What's unit vs integration vs e2e

Every test carries an explicit `@pytest.mark.{unit,integration}` decorator. Counts: ≈590 `unit`, ≈422 `integration`, across ~100 test modules. There is **no implicit default**. The split follows the I/O boundary, not the directory:

- **unit**: pure, in-process. Call a function, assert its return value. Canonical example: the git-dir parsers in `tests/pipeline/io/test_git.py`. They build on-disk shapes under `tmp_path`. They assert `resolve_git_dir`/`is_git_repo` return values, with **no subprocess and no real `git`** (`tests/pipeline/io/test_git.py:1-9`). CLI-dispatch tests are `unit` too. They call `dispatch([...])` and assert return code plus `capsys` output (`tests/cli/test_cli.py:9-41`).
- **integration**: in-process, but crosses into the real filesystem build pipeline. Copy `SAMPLE_REPO` into `tmp_path`. Call `dispatch(["init", ...])` or `build_all(...)`. Assert emitted `.context/` artifacts exist (`tests/cli/test_cli.py:43-60`, `tests/eval/test_retrieval_eval.py:60-67`).
- **e2e**: subset of `integration`. Shells out to the installed entrypoint via `subprocess.run([sys.executable, "-m", "dummyindex", ...])`. Only two modules do this: `tests/cli/test_ingest_command.py:24-31` and `tests/cli/test_reconcile_gate_e2e.py:61-66`. They exercise the real process boundary: stdin JSON in, stdout decision out, for the hook gate. No Selenium or browser layer. This is a CLI, so "e2e" means the subprocess. CI adds a smoke test of the binary (`tests.yml:32-46`): `--help`, `--version`, `install`, `ingest`, artifact existence.

## Fixtures

Shared fixtures live in `tests/conftest.py`. `tests/usage/` has its own sub-`conftest.py` for the usage corpus. Patterns in use:

- **`tmp_path` / `tmp_path_factory`** everywhere, for filesystem isolation. `tmp_repo` is a thin alias (`tests/conftest.py:9-11`).
- **`tests/paths.py`** exports stable anchors: `REPO_ROOT`, `FIXTURES_DIR`, `SAMPLE_REPO`. So deep modules never chain `Path(__file__).parent.parent`.
- **`SAMPLE_REPO`** (`tests/fixtures/sample_repo/`) is the frozen input repo. Tests `shutil.copytree` it into `tmp_path` before mutating. The fixture stays pristine (`tests/cli/test_cli.py:44-53`).
- **Module-scoped build** for expensive setup. `test_retrieval_eval.py:60-67` runs `build_all` once per module (`scope="module"`). Tree-sitter parse + graph + cluster is the costly part.
- **Constructed corpora**, not recorded ones. `tests/usage/conftest.py` hand-builds a JSONL corpus. It uses fixed timestamps and token counts, so tests assert **exact** numbers.

## Mocking philosophy

Minimal mocking. Repo prefers **dependency injection at the boundary** over `unittest.mock` patching. The default-plugin installer takes a `runner` parameter. Tests pass a `_FakeRunner` that records `(argv, cwd)` and returns scripted `RunResult`s. No real `claude` CLI is touched (`tests/context/test_default_plugins.py:204-213`).

`monkeypatch` is used sparingly. The autouse `_no_real_plugin_install` fixture sets `SKIP_INSTALL_ENV`. No test shells out to the production plugin path by accident (`tests/conftest.py:14-21`). Pure functions are tested with filesystem shapes, not mocks.

## Determinism & assertion style

Assertions check **deterministic, exact output**. Exact return codes. Exact stdout or stderr substrings via `capsys`. Exact emitted artifacts. Exact aggregate numbers.

The retrieval eval (`tests/eval/`) is **correctness-gated**. It records MRR, hit-rate@3, and mean-tokens. It asserts floors, each one documented margin below the `BASELINE.md` baseline. A permanent **negative-control** fixture scores 0 and rank ∞. So the gate can't pass vacuously (`tests/eval/test_retrieval_eval.py:117-206`).

## Coverage

`pytest-cov>=7.1.0` is a dev dependency (`pyproject.toml:98-101`). No `--cov` flag in the CI command. No `fail_under` gate in `pyproject.toml`. Coverage works locally: `pytest --cov=dummyindex --cov-report=term-missing`. It is **not enforced** in this repo. Treat the global 80% rule as aspirational. The enforced bar is "the suite is green on the 3.10/3.12 matrix."

## Anti-patterns to avoid (repo-specific)

- **Don't add an unmarked test.** `--strict-markers` plus the unit/integration convention means a missing marker is a smell. An *undeclared* marker fails collection.
- **Don't gate on live `.context/` cluster ids.** They re-cluster on rebuild. Gate on the frozen `SAMPLE_REPO` index, or on stable signals like citation **paths**. Not `community-N` ids (`tests/eval/test_retrieval_eval.py:1-26,144-150`).
- **Don't shell out to real `claude`/`git`.** Inject a fake runner, or build the on-disk shape by hand.
- **Don't mutate `SAMPLE_REPO` in place.** Copytree into `tmp_path` first.
- **Don't lower retrieval floors to make a regression pass.** Any drop below `T_HIT`/`T_MRR` is a real regression (`tests/eval/test_retrieval_eval.py:40-47`).
