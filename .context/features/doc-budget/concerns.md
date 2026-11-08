# Doc budget: concerns

`confidence: EXTRACTED`

- Seeding bypasses the ceiling. `--update-ratchet` records any size (`ratchet.py:138-139`). Run `check` first.
- Deletion resets growth. Update drops entries for missing docs (`ratchet.py:121-147`). A recreated doc gets the ceiling again.
- A missing ratchet file means no growth guard. `read_ratchet` returns `{}` silently (`ratchet.py:74-75`). Without a style ratchet, `check` exits 0 unguarded (`dummyindex/cli/check.py:225-233`).
- Word count ignores meaning. Tables and links count per token, so authors may write terse prose.
- Style splits sentences only before uppercase letters (`style.py:21`). Filler matches ignore meaning.
- Non-UTF-8 files score zero style violations (`style.py:123-130`).
- Scope gaps: only `features/*/` direct children are measured. `council/`, `docs.md` and `feature.json` are excluded (`ratchet.py:23-30`).
- Generated `conventions/naming.md` is measured (`ratchet.py:29`) but skips style (`ratchet.py:33-34`). A regeneration that grows it fails `check` until the ratchet is updated.
- All three groups share one exit code. Output names the failing path, not the group.
- Malformed ratchet lines are fatal. Stale well-formed entries are silent until `--update-ratchet`.
