# Plan — Split dummyindex into shared, context and evolve layers with a one-way import boundary

Start only after the equip-bugs task merges (Wave 1 gate). Rerun the scan scripts in `D:\temp\` on the merged tree first.
File lists below come from the scan at the proposal commit. `boundary-map.md` has the full lists.

Every rename means: rename the definition and every use. Find uses with the AST scan or the symbol map. Keep no alias.

## Tasks

1. **Gate** (Wave 1). `git merge-base --is-ancestor <equip-bugs tip> HEAD` exits 0. Record `HEAD` as `GATE_SHA` in the checklist item.
   Rerun `D:\temp\split_scan.py`, `split_contract.py` and `split_waves.py`. Refresh `boundary-map.md` and the file lists if counts moved.

2. **Create the shared layer and boundary test v1** (Wave 2). Touches 86 files (66 source, 20 test) plus the new test.
   - Add `dummyindex/shared/__init__.py` and `dummyindex/shared/lesson/__init__.py`.
   - Move `dummyindex/context/domains/atomic_io.py` → `dummyindex/shared/atomic_io.py`. Rename `_replace_bytes` → `replace_bytes` (C2).
   - Move `dummyindex/context/domains/lesson/{__init__,enums,models}.py` → `dummyindex/shared/lesson/`.
   - Add `dummyindex/shared/errors.py` with `EvolveError` from `context/domains/evolve_gate.py`.
   - Add `dummyindex/shared/guard.py` with `safe_file` from `evolve_gate.py` and `project_lock` from `context/domains/evolve_promotion.py`.
   - Add `dummyindex/shared/lesson/rules.py` with `rules_in` and `_BLOCK` from `context/domains/living_rules.py`.
   - Rename `_bump` → `bump` in `context/domains/equip/lifecycle/status.py`, `equip/lifecycle/evolve.py`, `evolve_gate.py` (C2).
   - In `evolve_native_snapshot.py` and `evolve_gate.py`, apply spec C3.4 (sibling read, `guard.py` digest coverage).
   - Update every importer that `boundary-map.md` section B marks "move into shared".
   - Fix old-path comments in `pipeline/io/cache.py:147` and `context/domains/log_scan.py:3` (C3.13).
   - Retarget `tests/context/domains/test_closeout.py:512,522,547,557,564` to `module.replace_bytes` (C3.11).
   - Move `tests/context/domains/test_atomic_io.py` and `test_lesson.py` to `tests/shared/`. Add `tests/shared/__init__.py`.
   - Add `tests/test_import_boundaries.py` with the Wave 2 part of spec C5.

3. **Create the evolve layer, the seams and boundary test v2** (Wave 3). Touches 53 files (36 source, 17 test).
   - Add `dummyindex/evolve/__init__.py` and `dummyindex/evolve/cli/__init__.py`.
   - Move, names unchanged, from `dummyindex/context/domains/` to `dummyindex/evolve/`:
     `evolve.py`, `evolve_experiments.py`, `evolve_gate.py`, `evolve_learning.py`, `evolve_native.py`,
     `evolve_native_response.py`, `evolve_native_snapshot.py`, `evolve_promotion.py`, `evidence.py`, `living_rules.py`,
     `observe/`, `probation/`.
   - Move `dummyindex/cli/evolve.py` and `dummyindex/cli/evolve_probation.py` → `dummyindex/evolve/cli/`.
     Their `from .common import ...` becomes `from dummyindex.cli.common import ...`.
   - In `dummyindex/cli/__init__.py`, remove the module-level `evolve` import. Add 3 lazy root adapters (spec C1, C4):
     `_evolve_run`, `_closeout_learning` (with the failure `try`), `_probation_block`. Register them with `functools.partial`.
   - Seam S1: move `_learn_after_closeout`, `_SETTLED`, `_no_mark` into `dummyindex/evolve/evolve_learning.py` as `learn_after_closeout`.
     Add `after_closeout` to `closeout_workspace`/`closeout_from_file`. Thread it through `cli/gc.py` and `cli/build_loop/dispatch.py`.
   - Seam S2: add `session_block` to `cli/memory.py` `run`.
   - Rename `_human_prompt_text` → `human_prompt_text` in `memory/miner/scan.py` and `observe/importer.py`.
     Rename `_decode`, `_FORMAT`, `_read_manifest`, `_HASH_RE` in `export/storage.py` and `evolve_native_snapshot.py` (C2).
   - Move the 13 evolve test files to `tests/evolve/` and `tests/evolve/cli/` (`boundary-map.md` A3). Add `__init__.py` files.
   - Retarget test strings and paths (C3.11): `test_memory_cli.py:112`, `test_evolve_gate.py:111`, `test_closeout_exit_codes.py:16`.
   - Replace about 14 `learner=` sites in `tests/context/domains/test_closeout.py` (and any in `test_build_loop.py`, `gc/test_delete.py`)
     with `after_closeout=functools.partial(learn_after_closeout, learner=...)`.
   - Add seam tests (spec Acceptance 3–5) in `tests/context/domains/test_closeout.py`, `tests/cli/test_closeout_exit_codes.py`
     (gc and build paths) and `tests/context/domains/memory/test_memory_cli.py`.
   - Extend `tests/test_import_boundaries.py` with the Wave 3 part of spec C5.

4. **Update the layering docs** (Wave 3, parallel with task 3). Edit `docs/reference/01-conventions.md` §1–3 and line 177:
   the 3-layer rule, the root exception, the `evolve/cli/` exception, the new `atomic_io` path. ASD-STE100 style.

5. **Acceptance** (Wave 4). Full CI suite and lint. The unchanged-files diff against `GATE_SHA`.

## Reused symbols

- `write_text_atomic`, `replace_bytes` (`shared/atomic_io.py`)
- `EvolveError` (`shared/errors.py`)
- `safe_file`, `project_lock` (`shared/guard.py`)
- `validate_lesson`, `LearningStatus` (`shared/lesson/`)
- `closeout_from_file`, `learning_exit_code`, `learning_line`, `failed_record_path` (`context/domains/proposals/closeout.py`)
- `session_block` (`evolve/probation/`)

## Tooling

No plugin or skill is bound to a task. Code tasks dispatch to python-implementer, then python-tester. The docs task dispatches to dummyindex-docs-specialist.
