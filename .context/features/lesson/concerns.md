# Lesson boundaries

- `evidence` is required text only. It is not checked against any file. Learning
  checks its own event evidence separately: `evolve_learning.py:152-159`.
- `confidence` and `edits` are validated, then dropped. Only `cue` and `lesson`
  reach the rule body. `evolve_learning.py:262-263` stores no lesson fields.
- Verdicts are author claims. No code measures them.
- Legacy reflections still pass learning with a warning. Library storage refuses them.
- Owner text is the source of truth. Rule IDs and hashes guard the merge; a
  stale `expected_sha256` fails instead of overwriting.
