# Lesson records

`confidence: EXTRACTED`

A lesson is one validated `cue`, `lesson`, `evidence` and `confidence` record.
Each closeout or learning event carries at most one. `validate_lesson` is the
only shape check. Source: `dummyindex/shared/lesson/models.py:92`.

Required fields are non-empty strings. `confidence` is `low|medium|high`.
A list is rejected; a closeout takes exactly one object.
`models.py:92-109`, `enums.py:8`, `tests/shared/test_lesson.py:85`.

Optional `edits` rows are `{component, change, verdict}`. Verdict is
`helped|hurt|no_observed_effect|confounded`. Prefer `confounded` to invented attribution.
`models.py:81-89`, `enums.py:16`.

A pre-change reflection has no lesson fields. It is not rejected. It returns
`legacy_shape`, and learning warns once. `models.py:96-97`,
`evolve_learning.py:271-277`. Library storage refuses it:
`equip/lifecycle/library.py:45-46`.

`lesson_to_delta` is pure. It returns `plan_rule` keyword arguments with body
`When <cue>: <lesson>`. Op is `revise` when the rule ID exists, else `add`.
`supersede` needs explicit `supersedes`. `models.py:112-141`,
`test_lesson.py:108-127`.

Merge and hash checks stay in `living_rules.plan_rule`. An owner edit between
plan and apply is refused: `test_lesson.py:138-143`.

`LearningStatus` is the closed alphabet
`applied|evaluated|blocked|no_entry|pending|ignored|failed`.
`evolve_learning.learning_status` derives it from event state:
`evolve_learning.py:35-46`, `enums.py:33-42`.

Exports: `lesson/__init__.py:19-29`. Consumers: `dummyindex/context/domains/proposals/closeout.py:153-156`,
`evolve_learning.py:198,214`, `equip/lifecycle/library.py:37-46`.
