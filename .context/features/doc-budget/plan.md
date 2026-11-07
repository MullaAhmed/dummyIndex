# Doc budget: implementation map

`confidence: EXTRACTED`

1. Ceilings, ratchet paths: `dummyindex/context/domains/docbudget/constants.py:17-26`.
2. Group enum: `enums.py:10-16`. Result models: `models.py:10-34` (`BudgetViolation`, `UpdateResult`).
3. Pure core: `ratchet.py`. `measure` `:34`, `scan` `:48`, `read_ratchet` `:62`, `format_ratchet` `:82`, `write_ratchet` `:88` (atomic write, `:90`), `check` `:93`, `update_ratchet` `:111`.
4. CLI: `dummyindex/cli/check.py:69` dispatches; `_run_budget_check` `:151-196` runs both groups and prints results.
5. Tests: `tests/context/domains/docbudget/test_ratchet.py`, `tests/cli/test_check_budget.py`, `tests/test_skills_doc_hygiene.py:717-763`.

## Flow

Check: read ratchet, `scan` current words, compare with `check`, print violations, exit 1 on any.

Update: `scan`, then `update_ratchet`, then `write_ratchet`, then print refusals. Refused entries keep their old value, so rewriting the file is safe.

## Boundaries

- Budget runs only under `check --budget`. `check --refs` is a separate path (`managed-doc-homes`).
- The gate is a word count, not a quality check.
- Writes go through `write_text_atomic` (`ratchet.py:90`).
