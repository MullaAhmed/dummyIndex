# Doc budget: concerns

`confidence: EXTRACTED`

- Seeding bypasses the ceiling. `--update-ratchet` records an unrecorded doc at any size (`ratchet.py:128-129`). The ceiling applies only to `check`. Run `check` before updating.
- Deletion resets growth. Update drops entries for missing docs (`ratchet.py:126`). A recreated doc is unrecorded and gets the ceiling again.
- A missing ratchet file means no growth guard. `read_ratchet` returns `{}` silently (`ratchet.py:63-65`).
- Word count ignores meaning. Tables, code and links count per token. Authors may write terse prose to fit.
- Scope gaps: only direct children of `features/*/` are measured. `council/`, `docs.md` and `feature.json` are excluded (`ratchet.py:22-29`). `features/x/sub/spec.md` is never checked.
- Generated `conventions/naming.md` is measured (`ratchet.py:28`). A regeneration that grows it fails `check` until the ratchet is updated.
- Skills and context share one exit code. Output names the failing path, but the code alone does not say which group failed.
- Malformed ratchet lines are fatal, while a well-formed but stale entry is silent. Entries lag until `--update-ratchet` runs.
