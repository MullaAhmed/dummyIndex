# Checklist — Split dummyindex into shared, context and evolve layers with a one-way import boundary

> Waves run in order. Items in one wave touch disjoint files.
> Waves 2–3 start only after the equip-bugs task merges (spec: Conflict with the equip-bugs task).
> Tick `- [x]` only after every named command passes.

## Wave 1 — gate

- [x] **GATE** `git merge-base --is-ancestor <equip-bugs tip> HEAD` exits 0. Record `HEAD` here as `GATE_SHA`. Rerun the `D:\temp\split_*.py` scans and refresh `boundary-map.md` and the Wave 2–3 file lists (plan task 1).
  - equip-bugs tip `d45e39f`. `GATE_SHA = df72961a8b392ac8726886c0d6cda7e91e71f706`.
  - Rescan: 415 source + 276 test modules. Wave 2 now 89 files (69 source, 20 test). Wave 3 stays 53 (36 source, 17 test).
  - New Wave 2 importers of `atomic_io`: `equip/generate/grounding.py`, `requirements/gate.py`, `requirements/toml_io.py`. `gc/delete.py` has 2 more lock sites (lines 277–278).
  - R6 finds 0 unresolved bases. R7 allowlist lines are unchanged.

## Wave 2 — shared layer (BLOCKED until equip-bugs merges)

- [x] Create `dummyindex/shared/` (`atomic_io.py`, `errors.py`, `guard.py`, `lesson/`, `lesson/rules.py`), rename `_replace_bytes` and `_bump`, and keep digest coverage. Move tests to `tests/shared/` and add boundary test v1 (plan task 2). Verify: `ruff check .` passes. `python -m pytest tests/test_import_boundaries.py tests/shared tests/context tests/cli tests/test_install.py -q` passes. `python -m pytest tests/ -q --tb=short` passes.

## Wave 3 — evolve layer, seams, docs (BLOCKED until equip-bugs merges)

- [ ] Create `dummyindex/evolve/` and `dummyindex/evolve/cli/`, add the 3 lazy root adapters and seams S1/S2, and rename the C2 names. Move tests to `tests/evolve/`, add the seam tests, and extend the boundary test to v2 (plan task 3). Verify: `ruff check .` passes. `python -m pytest tests/test_import_boundaries.py tests/evolve tests/context tests/cli -q` passes. `python -m pytest tests/ -q --tb=short` passes.
- [ ] Update `docs/reference/01-conventions.md` with the 3-layer rule and its two exceptions (plan task 4). Verify: `python -m pytest tests/test_repo_doc_style.py -q` passes.

## Wave 4 — acceptance

- [ ] Acceptance: `ruff check .` passes and `python -m pytest tests/ -q --tb=short` passes on the split tree, including every R1–R7 self-check and the seam tests.
- [ ] Acceptance: `git diff <GATE_SHA> HEAD -- pyproject.toml docs/COMMANDS.md dummyindex/skills dummyindex/context/hooks.py dummyindex/context/enums.py` is empty.
