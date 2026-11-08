# Feature: Doc budget ratchet

`confidence: EXTRACTED`

Caps word counts and style violations of authored `.context/` docs and `SKILL.md` files. A recorded doc may not grow. Entry point: `dummyindex context check --budget` or `--style`, dispatched at `dummyindex/cli/check.py:75-80`.

## Behavior

- Three groups: CONTEXT `.context/doc-budget.txt`, SKILLS `tests/data/skill-budget.txt`, STYLE `.context/style-budget.txt`. Paths: `constants.py:24-29`.
- Ceilings live in code. Unrecorded authored docs cap at 1500 words (`constants.py:20`). Unrecorded `SKILL.md` files cap at 2500 (`:22`). Unrecorded docs allow zero style violations (`:28`).
- Growth fails. A recorded doc above its entry is flagged (`ratchet.py:116-117`).
- Words are whitespace-split tokens (`ratchet.py:37-39`).
- Style flags sentences over 20 words and filler phrases (`style.py:13`, `:22-37`). Code, comments, tables and headings are skipped (`style.py:74`). `naming.md` is exempt (`ratchet.py:33-34`).
- Context scope: feature docs, `PROJECT.md`, `architecture/overview.md`, `conventions/*.md` (`ratchet.py:23-30`).
- Skills match exact name `SKILL.md`; Windows globbing is case-insensitive (`ratchet.py:60-62`).
- `--update-ratchet` needs `--budget` or `--style` (`cli/check.py:70-71`). It lowers entries and drops deleted docs (`ratchet.py:121-147`).
- The update never raises an entry. Grown docs keep their entry, print `refused`, exit 1 (`cli/check.py:245-247`).
- Seeding records an unrecorded doc at its current size, even above ceiling (`ratchet.py:138-139`).
- Malformed ratchet lines exit 2 (`ratchet.py:85-88`, `cli/check.py:236-238`).
- A missing ratchet reads as empty (`ratchet.py:74-75`). Style prints details and a seed hint (`cli/check.py:225-233`).
- Default `check` never runs a group. Only `--budget` or `--style` does (`cli/check.py:75`).

## Tests

- `tests/context/domains/docbudget/`, `tests/cli/test_check_budget.py`, `tests/test_skills_doc_hygiene.py:738-791`.
