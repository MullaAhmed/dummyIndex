# Lesson implementation

1. Models and parsing: `lesson/models.py:21-108`. Closed enums: `lesson/enums.py:8-42`.
   Exports: `lesson/__init__.py:19-29`.
2. Pure delta mapping: `lesson/models.py:111-140`. It reads current rule IDs
   through `living_rules.rules_in` and writes nothing.
3. Learning intake: `evolve_learning.py:191` validates the reflection, `:214`
   maps it to a delta, `:224` plans via `plan_rule`, `:264` flags legacy shape.
4. Closeout pre-check: `dummyindex/context/domains/proposals/closeout.py:153-158` validates before writes.
5. Equip library: `equip/lifecycle/library.py:37-46` maps errors to `EquipError`
   and refuses legacy shape.
6. Learning status: `evolve_learning.py:28-39` derives `LearningStatus`;
   `dummyindex/context/domains/proposals/closeout.py:246-252` treats settled statuses as final.

Tests: `tests/context/domains/test_lesson.py`. They cover round trip, field
rejection, delta purity, add/revise/supersede, double apply and owner edits.
