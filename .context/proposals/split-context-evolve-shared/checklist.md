# Checklist — Split dummyindex into shared, context and evolve layers with a one-way import boundary

> Waves run in order. One item per wave, so file sets never overlap inside a wave.
> Waves 2–4 start only after the equip-bugs task merges (spec: Conflict with the equip-bugs task).
> Tick `- [x]` only after the named pytest command passes.

## Wave 1 — gate

- [ ] **GATE** Confirm equip-bugs is merged into this branch. Rerun the AST scan and refresh the Wave 2 and Wave 3 file lists.

## Wave 2 — shared layer (BLOCKED until equip-bugs merges)

- [ ] Create `dummyindex/shared/` (`atomic_io.py`, `guard.py`, `lesson/`, `lesson/rules.py`). Move tests to `tests/shared/`. Rename `_replace_bytes` and `_bump`. Fix the `atomic_io` sibling read (plan task 1). Verify: `python -m pytest tests/shared tests/context/domains/equip tests/context/domains/gc tests/context/domains/test_closeout.py tests/context/build/test_upgrade.py tests/context/domains/test_evolve_gate.py tests/context/domains/test_evolve_learning.py tests/context/domains/test_evolve_native.py tests/context/domains/test_probation.py tests/test_install.py -q` passes, then `python -m pytest tests/ -q --tb=short` passes.

## Wave 3 — evolve layer and seams (BLOCKED until equip-bugs merges)

- [ ] Create `dummyindex/evolve/` and `dummyindex/evolve/cli/`. Move tests to `tests/evolve/`. Add seams S1 and S2 and wire them in `dummyindex/cli/__init__.py`. Rename `_human_prompt_text` (plan task 2). Verify: `python -m pytest tests/evolve tests/context/domains/test_closeout.py tests/context/domains/test_build_loop.py tests/context/domains/gc tests/context/domains/memory tests/cli -q` passes, then `python -m pytest tests/ -q --tb=short` passes.

## Wave 4 — boundary test

- [ ] Add `tests/test_import_boundaries.py` per spec C5. Verify: `python -m pytest tests/test_import_boundaries.py -q` passes, and its self-check test reports the planted `tmp_path` edge.

## Wave 5 — acceptance

- [ ] Acceptance: `python -m pytest tests/ -q --tb=short` passes on the split tree.
- [ ] Acceptance: `git diff main -- pyproject.toml docs/COMMANDS.md dummyindex/skills dummyindex/context/hooks.py dummyindex/context/enums.py` is empty, and no old path from spec C5 exists.
