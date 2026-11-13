# Plan — Split dummyindex into shared, context and evolve layers with a one-way import boundary

Start only after the equip-bugs task merges. Rerun the AST scan on the merged tree first.
File lists below come from the scan at the proposal commit. `boundary-map.md` has the full lists.

## Tasks

1. **Create the shared layer** (Wave 2). Touches 86 files (66 source, 20 test).
   - Add `dummyindex/shared/__init__.py` and `dummyindex/shared/lesson/` with `__init__.py`.
   - Move `dummyindex/context/domains/atomic_io.py` → `dummyindex/shared/atomic_io.py`.
     Rename `_replace_bytes` → `replace_bytes`. Update `context/build/upgrade.py`, `context/domains/proposals/closeout.py`.
   - Move `dummyindex/context/domains/lesson/{__init__,enums,models}.py` → `dummyindex/shared/lesson/`.
   - Add `dummyindex/shared/guard.py`. Move into it, unchanged:
     `EvolveError` and `safe_file` from `context/domains/evolve_gate.py`, `project_lock` from `context/domains/evolve_promotion.py`.
   - Add `dummyindex/shared/lesson/rules.py`. Move `rules_in` and `_BLOCK` into it from `context/domains/living_rules.py`.
   - Rename `_bump` → `bump` in `context/domains/equip/lifecycle/status.py`. Update its importers (`evolve_gate.py`).
   - In `context/domains/evolve_native_snapshot.py`, read `atomic_io` through `Path(atomic_io.__file__)` (spec C3.4).
   - Update every importer that `boundary-map.md` section B marks "move into shared" to the new path.
   - Move `tests/context/domains/test_atomic_io.py` → `tests/shared/test_atomic_io.py`,
     `tests/context/domains/test_lesson.py` → `tests/shared/test_lesson.py`. Add `tests/shared/__init__.py`.

2. **Create the evolve layer and the two seams** (Wave 3). Touches 53 files (36 source, 17 test).
   - Add `dummyindex/evolve/__init__.py` and `dummyindex/evolve/cli/__init__.py`.
   - Move, names unchanged, from `dummyindex/context/domains/` to `dummyindex/evolve/`:
     `evolve.py`, `evolve_experiments.py`, `evolve_gate.py`, `evolve_learning.py`, `evolve_native.py`,
     `evolve_native_response.py`, `evolve_native_snapshot.py`, `evolve_promotion.py`, `evidence.py`, `living_rules.py`,
     `observe/`, `probation/`.
   - Move `dummyindex/cli/evolve.py` and `dummyindex/cli/evolve_probation.py` → `dummyindex/evolve/cli/`.
     Their `from .common import ...` becomes `from dummyindex.cli.common import ...`.
   - Seam S1 (spec C4): move `_learn_after_closeout`, `_SETTLED`, `_no_mark` from `context/domains/proposals/closeout.py`
     into `dummyindex/evolve/evolve_learning.py` as `learn_after_closeout`.
     Add `after_closeout` to `closeout_workspace`/`closeout_from_file`. Thread it through `cli/gc.py` and `cli/build_loop/dispatch.py`.
   - Seam S2 (spec C4): add `session_block` to `cli/memory.py` `run`.
   - Wire both seams in `dummyindex/cli/__init__.py` with `functools.partial` and two lazy root adapters.
     Point `ContextSubcommand.EVOLVE` at `dummyindex.evolve.cli.evolve.run`.
   - Rename `_human_prompt_text` → `human_prompt_text` in `context/domains/memory/miner/scan.py`. Update `evolve/observe/importer.py`.
   - Move the 13 evolve test files to `tests/evolve/` and `tests/evolve/cli/` (`boundary-map.md` A3). Add `__init__.py` files.
   - Retarget the `monkeypatch.setattr` strings (spec C3.11).
   - Update closeout tests that expect learning to pass `after_closeout=learn_after_closeout`:
     `tests/context/domains/test_closeout.py`, `tests/context/domains/test_build_loop.py`, `tests/context/domains/gc/test_delete.py`.

3. **Add the boundary test** (Wave 4). Touches `tests/test_import_boundaries.py` only. Design: spec C5.
   Reuse the scan logic from the proposal script. Keep it under about 120 lines.

4. **Acceptance** (Wave 5). Run the full CI suite. Check the unchanged-files diff (spec Acceptance).

## Reused symbols

`write_text_atomic`, `replace_bytes` (`shared/atomic_io.py`); `safe_file`, `project_lock`, `EvolveError` (`shared/guard.py`);
`validate_lesson`, `LearningStatus` (`shared/lesson/`); `closeout_from_file`, `learning_exit_code`, `learning_line`,
`failed_record_path` (`context/domains/proposals/closeout.py`); `session_block` (`evolve/probation/`).

## Tooling

No plugin or skill is bound to a task. All tasks dispatch as subagents (python-implementer, python-tester).
