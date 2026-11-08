# Plan — Three-way language policy: ADHD-minimal human replies, English caveman persistent docs, concise-Chinese agent-to-agent prompts

> Rules for every task:
> - New code carries no long comments. One-line docstrings only.
> - Every new test carries `@pytest.mark.unit` (`--strict-markers`).
> - Never run `rebuild`. Edit `.context/` docs in place only.
> - New prose in docs and constants: 20 words or fewer per sentence.

## Tasks

1. **Style lint module.** Add `dummyindex/context/domains/docbudget/style.py`: frozen `StyleViolation`, `lint_text`, `count_violations`, per spec. Add `BudgetGroup.STYLE` to `enums.py`. Add `STYLE_CEILING = 0` and `STYLE_RATCHET_REL = ".context/style-budget.txt"` to `constants.py`. In `ratchet.py`, branch `scan` and `_ceiling` on STYLE; STYLE reuses `_CONTEXT_GLOBS`, drops `conventions/naming.md`, and measures with `count_violations`. Export from `__init__.py`. Reuse `check` and `update_ratchet` unchanged. Tests: `tests/context/domains/docbudget/test_style.py` with the spec's style cases.

2. **Language share.** Add `dummyindex/context/domains/docguard/language.py` with `cjk_share` per D6. Tests: `tests/context/domains/docguard/test_language.py` with the spec's threshold cases.

3. **Policy constants.** Rewrite `ALWAYS_ON_OUTPUT_POLICY` and `ALWAYS_ON_TURN_REMINDER` in `dummyindex/context/output/bootstrap.py` per spec Contracts. Count words by hand; task 12 adds the lint test. Update `_POLICY_INVARIANTS` and `_POLICY_CONSTANT_HASH` in `tests/cli/test_cli_doc_sync_policy_canary.py`. Keep every row whose clause survives; add the "at most 5 items per group" row. Rewrite the three `test-anchor:policy-restatement` regions: `dummyindex/skills/skill.md`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`. Re-render the repo `AGENTS.md` with `dummyindex context bootstrap --platform agents`. Leave `tests/eval/behavior_arms.py` untouched.

4. **Caveman manual default.** Add `ensure_caveman_manual` to `dummyindex/context/default_plugins.py` per D1/D2. Call it in `wire_default_plugins` for `caveman@caveman` when `_effective_enabled` is not `False`. Reuse `write_text_atomic` from `dummyindex/context/domains/atomic_io.py`. Tests in `tests/context/test_default_plugins.py`. Dogfood: create repo-root `.caveman.json` by calling `ensure_caveman_manual(Path("."))`.

5. **HOW_TO_USE template.** Compress the prose in `generate_how_to_use_md` (`dummyindex/context/output/instructions.py`). Keep every command, path, and table meaning. Update pinned phrases in `tests/context/output/test_instructions.py`. Write the output to `.context/HOW_TO_USE.md` with `write_how_to_use_md`.

6. **Measurement spec.** Author `.context/proposals/agent-language-policy/experiment.json` for `dummyindex context evolve experiment --run agent-language --from-file <file>`. Use `"execution": "native"`. Arms: English vs Chinese subagent prompts on the same held-out tasks. Metrics: output tokens and task pass rate. Read the keys `run_native` expects in `dummyindex/context/domains/evolve_native.py`; do not edit evolve code. Verify only: the file parses as JSON and carries those keys. Do not run the experiment.

7. **`check --style`.** In `dummyindex/cli/check.py`, generalize `_run_budget_check` to take a tuple of `(BudgetGroup, ratchet_rel)` pairs; no copy. `--budget` passes CONTEXT+SKILLS; `--style` passes STYLE. STYLE output lists `path:line: rule: excerpt` from `lint_text`. Missing style ratchet gives D9. Keep the exact line `context check --budget: ok`; `tests/cli/test_check_refs.py:31` pins it. `--update-ratchet` needs `--budget` or `--style`. Update the `check` line in `dummyindex/cli/help.py`. Tests in `tests/cli/test_check_budget.py` with the spec's flag cases.

8. **Language guard.** In `dummyindex/cli/guard_doc_write.py`, add `LANGUAGE_TOOLS = frozenset({"Agent", "Task", "SendMessage"})`. Branch first in `_decide`, before `CITATION_TOOLS` and `read_doc_guard_settings`. Call `cjk_share`; print the `additionalContext` payload per spec. Update the module docstring in one line. Tests in `tests/cli/test_guard_doc_write.py`, parametrized over the three tool names.

9. **Matcher.** Set `_PRE_TOOL_USE_HOOK["matcher"]` in `dummyindex/context/hooks.py` to `Write|Edit|MultiEdit|Agent|Task|SendMessage`. Update the module docstring item 5. `install_hook_entry` refreshes the old entry by sentinel. Update the 3 matcher asserts in `tests/context/test_hooks.py`; add the re-install-over-old-matcher case. Dogfood: rerun `dummyindex context hooks install` locally; it refreshes the baked turn reminder. Settings files are untracked.

10. **Docs.** In `dummyindex/skills/skill.md`, note `.caveman.json` `manual` in the caveman default bullet. In `docs/COMMANDS.md` and `docs/guide/07-cli.md`: document `check --budget`, `--refs`, `--style`, `--update-ratchet`; the language hook; the `.caveman.json` default and `CAVEMAN_DEFAULT_MODE` precedence. In `dummyindex/skills/council/65-reconcile.md`, add the D12 line.

11. **One-time compression.** Rewrite in place to zero `lint_text` violations. Compress first; fold new behavior second. Before editing, save the set of backticked spans per file; after, assert none was lost. Leave no backup files under `.context/`. Three disjoint groups:
    - a. `.context/conventions/{coding-practices,data-access,folder-organization,testing}.md`.
    - b. `.context/features/bootstrap/{spec,plan,concerns}.md`, plus the new policy behavior.
    - c. `.context/features/managed-doc-homes/{spec,plan,concerns}.md`, plus the language guard.
    - d. `.context/features/install-surface/spec.md` (caveman manual, matcher) and `.context/features/cli-dispatch/spec.md` (`--style`). New sentences only; no full compression.

12. **Lock.** Run `dummyindex context check --style --update-ratchet` to seed `.context/style-budget.txt`. Run `dummyindex context check --budget --update-ratchet` to lower `.context/doc-budget.txt`. Add `tests/context/domains/docbudget/test_style_ratchet.py`: the repo-level STYLE check passes, mirroring `test_context_doc_budget_ratchet_exists_and_passes`. Same file: `lint_text` returns `()` for both policy constants and `generate_how_to_use_md()`.

13. **Acceptance.** Run `pytest -q` and `dummyindex context check --style`, `--budget`, `--refs`. All exit 0.

## Reused symbols

- `check`, `update_ratchet`, `read_ratchet`, `write_ratchet`, `scan`, `_CONTEXT_GLOBS` (`dummyindex/context/domains/docbudget/ratchet.py`).
- `read_hook_stdin` (`dummyindex/cli/memory.py`), `MAX_SCAN_CHARS` (`dummyindex/cli/guard_doc_write.py`).
- `install_hook_entry` via `_CLAUDE_HOOKS` (`dummyindex/context/hooks.py`).
- `wire_default_plugins`, `_effective_enabled` (`dummyindex/context/default_plugins.py`).
- `generate_how_to_use_md`, `write_how_to_use_md` (`dummyindex/context/output/instructions.py`).
- `write_text_atomic` (`dummyindex/context/domains/atomic_io.py`).

## Out of scope

- Compressing the other 40 feature dirs. Follow-up after the fleet merges.
- Any edit to `plan`, `build`, `equip`, `gc`, `evolve`, `audit`, `fleet` `SKILL.md`.
- Any change to evolve code, `envelopes.py`, or `agents_md.py`.
- Running the measurement experiment.
