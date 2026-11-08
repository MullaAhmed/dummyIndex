# Feature: Doc budget ratchet

`confidence: EXTRACTED`

Caps word counts of authored `.context/` docs and packaged `SKILL.md` files. A recorded doc may not grow. An unrecorded doc must fit a ceiling. Entry point: `dummyindex context check --budget`, dispatched at `dummyindex/cli/check.py:69`.

## Behavior

- Two groups, two ratchet files: `.context/doc-budget.txt` (CONTEXT) and `tests/data/skill-budget.txt` (SKILLS). Paths: `dummyindex/context/domains/docbudget/constants.py:22-23`.
- Ceilings live in code. Unrecorded authored docs cap at 1500 words (`constants.py:18`). Unrecorded `SKILL.md` files cap at 2500 (`constants.py:20`).
- Growth fails. A recorded doc above its entry is flagged (`dummyindex/context/domains/docbudget/ratchet.py:106-107`).
- Words are whitespace-split tokens (`ratchet.py:34-36`). Markdown syntax counts.
- Context scope: feature `spec.md`, `plan.md`, `concerns.md`, `PROJECT.md`, `architecture/overview.md`, `conventions/*.md` (`ratchet.py:22-29`).
- Skills scope matches the exact name `SKILL.md`. Windows globbing is case-insensitive (`ratchet.py:51-53`).
- `--update-ratchet` requires `--budget` (`cli/check.py:62-63`). It lowers entries and drops entries for deleted docs (`ratchet.py:111-137`).
- The update never raises an entry. Grown docs keep the old entry and are reported as `refused`, exit 1 (`cli/check.py:186`).
- Seeding: an unrecorded doc is recorded at its current size, even above the ceiling (`ratchet.py:128-129`).
- A malformed ratchet line exits 2 (`ratchet.py:76-78`, `cli/check.py:176-177`).
- A missing ratchet file reads as empty (`ratchet.py:63-65`).
- Default `check` never runs the budget. It runs only with `--budget`.

## Tests

- `tests/context/domains/docbudget/test_ratchet.py`: growth, ceiling, seeding, sort, malformed input.
- `tests/cli/test_check_budget.py`: exit codes and `--update-ratchet` output.
- `tests/test_skills_doc_hygiene.py:717-763`: repo-wide ratchet gates for skills and `.context/`.
