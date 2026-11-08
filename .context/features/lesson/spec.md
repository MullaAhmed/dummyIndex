# Lesson records

`confidence: EXTRACTED`

A lesson is one validated `cue`, `lesson`, `evidence` and `confidence` record.
Each closeout or learning event carries at most one. `validate_lesson` is the
only shape check. Source: `dummyindex/context/domains/lesson/models.py:91`.

Required fields are non-empty strings. `confidence` is `low|medium|high`.
A list is rejected; a closeout takes exactly one object.
`models.py:91-108`, `enums.py:8`, `tests/context/domains/test_lesson.py:85`.

Optional `edits` rows are `{component, change, verdict}`. Verdict is
`helped|hurt|no_observed_effect|confounded`. Prefer `confounded` to invented attribution.
`models.py:80-88`, `enums.py:16`.

A pre-change reflection has no lesson fields. It is not rejected. It returns
`legacy_shape`, and learning warns once. `models.py:95-96`,
`evolve_learning.py:264-270`. Library storage refuses it:
`equip/lifecycle/library.py:45-46`.

`lesson_to_delta` is pure. It returns `plan_rule` keyword arguments with body
`When <cue>: <lesson>`. Op is `revise` when the rule ID exists, else `add`.
`supersede` needs explicit `supersedes`. `models.py:111-140`,
`test_lesson.py:108-127`.

Merge and hash checks stay in `living_rules.plan_rule`. An owner edit between
plan and apply is refused: `test_lesson.py:138-143`.

`LearningStatus` is the closed alphabet
`applied|evaluated|blocked|no_entry|pending|ignored|failed`.
`evolve_learning.learning_status` derives it from event state:
`evolve_learning.py:28-39`, `enums.py:33-42`.

Exports: `lesson/__init__.py:19-29`. Consumers: `dummyindex/context/domains/proposals/closeout.py:153-156`,
`evolve_learning.py:191,214`, `equip/lifecycle/library.py:37-46`.
