# Checklist — agent-language-policy

> Every item: no long code comments; new tests carry `@pytest.mark.unit`; never run `rebuild`.

## Wave 1 — independent foundations

- [x] Style lint module, `BudgetGroup.STYLE`, STYLE ratchet branch, tests (`dummyindex/context/domains/docbudget/{style,enums,constants,ratchet,__init__}.py`, `tests/context/domains/docbudget/test_style.py`)
- [x] `cjk_share` module and threshold tests (`dummyindex/context/domains/docguard/language.py`, `tests/context/domains/docguard/test_language.py`)
- [x] Policy constants, canary rows and hash, three restatement regions, repo `AGENTS.md` re-render (`dummyindex/context/output/bootstrap.py`, `tests/cli/test_cli_doc_sync_policy_canary.py`, `dummyindex/skills/skill.md`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `AGENTS.md`)
- [x] `ensure_caveman_manual`, call in `wire_default_plugins`, tests, repo `.caveman.json` (`dummyindex/context/default_plugins.py`, `tests/context/test_default_plugins.py`, `.caveman.json`)
- [x] HOW_TO_USE template compression and sync (`dummyindex/context/output/instructions.py`, `tests/context/output/test_instructions.py`, `.context/HOW_TO_USE.md`)
- [x] Measurement spec authored and key-checked, not run (`.context/proposals/agent-language-policy/experiment.json`)
- [x] PreToolUse matcher widen, docstring, matcher tests (`dummyindex/context/hooks.py`, `tests/context/test_hooks.py`)

## Wave 2 — CLI and guard

- [x] `check --style`, shared ratchet runner, `--update-ratchet` rule, help line, flag tests (`dummyindex/cli/check.py`, `dummyindex/cli/help.py`, `tests/cli/test_check_budget.py`)
- [x] Language guard branch, docstring, parametrized tests (`dummyindex/cli/guard_doc_write.py`, `tests/cli/test_guard_doc_write.py`)

## Wave 3 — docs and compression

- [x] Docs for `check` flags, language hook, `.caveman.json`; D12 reconcile line (`dummyindex/skills/skill.md`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `dummyindex/skills/council/65-reconcile.md`)
- [x] Compress conventions; backticked spans preserved (`.context/conventions/{coding-practices,data-access,folder-organization,testing}.md`)
- [x] Compress bootstrap feature docs, then fold in policy behavior (`.context/features/bootstrap/{spec,plan,concerns}.md`)
- [x] Compress managed-doc-homes feature docs, then fold in language guard (`.context/features/managed-doc-homes/{spec,plan,concerns}.md`)
- [x] Add new behavior sentences to touched specs (`.context/features/install-surface/spec.md`, `.context/features/cli-dispatch/spec.md`)

## Wave 4 — lock

- [x] Seed `.context/style-budget.txt`; lower `.context/doc-budget.txt`; add repo-level style and constant-lint tests (`tests/context/domains/docbudget/test_style_ratchet.py`)

## Wave 5 — acceptance

- [ ] Acceptance: `pytest -q` passes
- [ ] Acceptance: `lint_text` returns `()` for both policy constants and `generate_how_to_use_md()`
- [ ] Acceptance: canary row pins "at most 5 items per group" in the constant and three restatement regions
- [ ] Acceptance: repo `AGENTS.md` equals `dummyindex context bootstrap --platform agents` output
- [ ] Acceptance: guard emits `additionalContext` without `permissionDecision` for English Agent, Task, and SendMessage text
- [ ] Acceptance: `dummyindex context check --style`, `--budget`, and `--refs` each exit 0
- [ ] Acceptance: `.context/style-budget.txt` records 0 for each of the 10 compressed files
- [ ] Acceptance: `.context/HOW_TO_USE.md` equals `generate_how_to_use_md()` output byte for byte
