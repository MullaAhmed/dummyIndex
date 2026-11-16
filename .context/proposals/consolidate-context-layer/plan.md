# Plan — Move all context code into dummyindex/context/

Scripts live in `D:\temp\` (`scan_rel.py`, `codemod.py`). They do not go into the repo.
Reused: `dummyindex.skills` package anchor (`context/domains/equip/generate/render.py:24`), `tests/paths.py` `TESTS_DIR`, the existing `tests/test_import_boundaries.py` scanner.

## Tasks

1. **Prep, in place (commit 1).** Behavior stays the same at the old paths.
   - Make the 5 cross-package relative imports absolute: `context/domains/requirements/seed.py`, `context/domains/requirements/toml_io.py`, `context/git.py`, `installer/common.py`.
   - `installer/common.py:22` and `cli/statusline.py:20`: locate `skills/` through `dummyindex.skills.__file__`.
   - `installer/ownership.py:21`: root = `Path(dummyindex.__file__).resolve().parent`.
   - Verify: `python -m pytest tests/test_install_ownership.py tests/cli/test_statusline.py -q` passes. The hash root stays the `dummyindex/` package dir. The file count under it stays equal.
2. **Move and rewrite (commit 2).** `D:\temp\codemod.py`:
   - `git mv` 7 source dirs, `versioning.py`, `codex_guidance.py`, and 6 test dirs (table in spec C2 and the target tree).
   - Rewrite the 9 dotted prefixes with `\b` in `dummyindex/`, `tests/`, `docs/`, `scripts/`. Skip `.context/`, `CHANGELOG.md`, `tests/fixtures/`.
   - Rewrite path-style prefixes in `dummyindex/` comments and docstrings, `docs/`, and test comments. Leave opaque test data strings.
   - `ruff check . --select I --fix`, then `ruff check .`.
   - Verify: `python -m dummyindex --help` exits 0. Each of the 9 packages imports alone in a fresh interpreter. A cycle here is a blocker: stop and report it.
3. **Fix depth in moved tests (parallel with 4 and 5).**
   - Depth grows by 1 where a test finds files from `__file__`: `tests/context/cli/test_cli.py` (7 sites), `tests/context/cli/equip/test_equip_source_apply.py:573`, `tests/context/pipeline/build/test_p2_read_counter.py:21`. Use `tests/paths.py`.
   - One test imports a test module by dotted path (`tests.cli...`). Fix it too.
4. **Boundary test.** `tests/test_import_boundaries.py` per spec C4: layer function, composition-root path, R5 prefixes, R7 path, R8 top-level rule with `tmp_path` self-check, fresh-interpreter list.
5. **Docs.** `docs/reference/01-conventions.md`, `docs/guide/03-architecture.md`, `docs/guide/04-data-model.md`, `docs/guide/08-skill.md`. Check `dummyindex/skills/**/*.md` and `dummyindex/context/output/instructions.py` for module paths. Hooks and installer strings stay (confirm only).
6. **Full verification.** Run every Acceptance command. Re-run `scan_rel.py` and a grep over `__file__`, `parents[`, `importlib.resources`. Check `pyproject.toml`, `.github`, `scripts/` for old paths.
7. **Report.** Counts: files moved, imports rewritten, hand fixes, test result. No merge, no push.
