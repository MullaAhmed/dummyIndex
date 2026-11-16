# Checklist — Move all context code into dummyindex/context/

> Waves run in order. Items in one wave touch disjoint files.
> Tick `- [x]` only after every named command passes.

## Wave 1 — prep in place

- [x] Make cross-package relative imports absolute and anchor 3 resource paths on package `__file__` (plan task 1). Files: `dummyindex/context/domains/requirements/seed.py`, `dummyindex/context/domains/requirements/toml_io.py`, `dummyindex/context/git.py`, `dummyindex/installer/common.py`, `dummyindex/installer/ownership.py`, `dummyindex/cli/statusline.py`. Verify: `python -m pytest tests/test_install_ownership.py tests/cli/test_statusline.py -q` passes.

## Wave 2 — move and rewrite

- [x] Run `D:\temp\codemod.py`: `git mv` the source and test dirs, rewrite the 9 prefixes, fix import order (plan task 2). Verify: `python -m dummyindex --help` exits 0, and `python -c "import dummyindex.context.<pkg>"` exits 0 for each of the 9 packages.

## Wave 3 — fixes in parallel

- [x] Fix `__file__`-depth sites in the moved tests (plan task 3). Verify: `python -m pytest tests/context/cli tests/context/pipeline tests/context/analysis tests/context/export tests/context/usage tests/context/shared -q` passes.
- [x] Rewrite `tests/test_import_boundaries.py` for the new layout (plan task 4). Verify: `python -m pytest tests/test_import_boundaries.py -q` passes.
- [x] Update docs and doc-generator text (plan task 5). Verify: `python -m pytest tests/test_repo_doc_style.py tests/test_skills_doc_hygiene.py -q` passes.

## Wave 4 — acceptance

- [ ] Acceptance: `ruff check .` passes and `python -m pytest tests/ -q --tb=short` passes with 0 failed.
- [x] Acceptance: `python -m dummyindex --help` exits 0, and the top level of `dummyindex/` is exactly `{__init__.py, __main__.py, skills, context, evolve}` (`__pycache__` ignored).
- [x] Acceptance: `git grep -nE "dummyindex\.(cli|shared|pipeline|analysis|export|usage|installer|versioning|codex_guidance)\b" -- dummyindex tests docs scripts pyproject.toml` has 0 hits.
- [x] Acceptance: `package_source_hash()` covers the same file set as before the move, and `git diff` shows `pyproject.toml` unchanged.
