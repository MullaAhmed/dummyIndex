# Probation: concerns

`confidence: INFERRED`

- Contest persists. By design (`tests/context/domains/test_probation.py:228`, `:436`): an attributed correction that cannot be verified counts as contested and blocks promotion. `followed` returns UNKNOWN for a null probe (`rules.py:62-63`), and `_tally` records it (`sync.py:162-166,191`). A probe-less item promotes only if never attributed. Only re-enter clears contested; demote keeps it (`actions.py:98`). `eligible` blocks promotion (`rules.py:104-105`).
- Dead states. `observed` is never assigned (`enums.py:11`). `proposed` is set and replaced in the same call (`actions.py:111-114`). Readers of stored state never see either.
- Unknown origin disables the harm exclusion. `origin` is `None` when no correction matches (`actions.py:94-97`). `harm_reached` and `eligible` then count every session (`rules.py:78`, `rules.py:99`).
- Errors vanish on the hook path. `session_block` swallows sync and block errors (`render.py:55-57`, `render.py:61-62`). `_print_probation` also swallows (`cli/memory.py:69-70`). A broken store shows no line and no error.
- Lock-busy session block hides state. It lists only `probation` items, with no `Next:`, exposure or write (`render.py:71-72`).
- Promotion can outlive its event. Files promote before the event log write (`actions.py:213-238`). A log failure keeps `promoted` and only adds a note (`actions.py:237-238`).
- Read path writes. `_next_line` pops a routed entry (`render.py:145-146`). `_block` records exposure and saves state (`render.py:85-103`). A SessionStart hook therefore writes cache files.
- Reminder is advisory. `needs_enforcement` only adds a reminder line (`render.py:126-127`). Nothing blocks the rule.
- Thresholds are guesses. Every constant says `uncalibrated default` (`constants.py:3-12`). The bound is reported as `detector-limited` (`actions.py:256`, `dummyindex/skills/evolve/probation-protocol.md:37-39`).
- Expiry depends on pruned data. `_expire` reads exposure rows (`sync.py:288-296`). `observe` prunes exposure rows on the same retention window (`observe/ledger.py:84`, `ledger.py:103-124`). An item can expire on a pruned record.
- Tampered source path reads as drift. `_file_sha` returns `None` for an unsafe path, so the item suspends (`sync.py:270-285`).
- Size budget counts characters. `INDEX_MAX_CHARS` bounds characters (`render.py:114`). `resident_bytes` sums bytes (`render.py:209-216`).
- Source-text guard is brittle. `test_probation_source_has_no_ledger_string` fails on any `improv` substring (`tests/context/domains/test_probation.py:575-580`).
