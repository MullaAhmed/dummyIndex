# Doc budget: implementation map

`confidence: EXTRACTED`

1. Ceilings, ratchet paths: `dummyindex/context/domains/docbudget/constants.py:17-32`.
2. Group enum: `enums.py:10-17`. Result models: `models.py:10-34`.
3. Pure core: `ratchet.py`. `measure` `:37`, `scan` `:57`, `read_ratchet` `:72`, `write_ratchet` `:98`, `check` `:103`, `update_ratchet` `:121`.
4. Style lint: `style.py`. `lint_text` `:74`, `count_violations` `:123`.
5. CLI: `dummyindex/cli/check.py:75-87` dispatches. `_run_ratchet_check` `:196-260` runs each group.
6. Tests: `tests/context/domains/docbudget/`, `tests/cli/test_check_budget.py`, `tests/test_skills_doc_hygiene.py:738-791`.

## Flow

Check: read ratchet, `scan` current size, compare with `check`, print violations, exit 1 on any.

Update: `scan`, `update_ratchet`, `write_ratchet`, print refusals. Refused entries keep their old value, so rewriting is safe.

## Boundaries

- Budget and style run only under `check --budget` or `--style`. `check --refs` is separate (`managed-doc-homes`).
- The gate counts words or violations, not quality.
- Writes go through `write_text_atomic` (`ratchet.py:100`).
