# Plan — All authored .context docs and repo docs follow ASD-STE100; dummyindex-update rewrites all context prose to STE

Each task names its files and the symbols that it reuses. Tests come first in each code task (`conventions/testing.md`). Logic goes in `context/domains/`, and `cli/` stays wire-only (`conventions/folder-organization.md`).

## Track A — ASD-STE100

1. **STE lint, scope and ruleset transition (C1, C2).** One task, so that `check --style` never goes red between waves.
   - `dummyindex/context/domains/docbudget/style.py`: add the strict rules `long-paragraph`, `contraction` and `semicolon`, and the advice rules `ing-form` and `passive`. Add a `severity` field to `StyleViolation`. `count_violations` counts strict rules only. Skip YAML frontmatter. Normalize CRLF. Reuse `lint_text`, `_lint_unit`, `_SENTENCE_SPLIT_RE` and `_CODE_RE`.
   - `docbudget/constants.py`: add `STE_RULESET_VERSION = 1`.
   - `docbudget/ratchet.py`: give `BudgetGroup.STYLE` its own globs and exempt set. Keep `_CONTEXT_GLOBS` for the word budget. Add `reseed`. `read_ratchet` ignores `#` lines. Add the `# ruleset N` header and the stale-header path.
   - `dummyindex/cli/check.py`: print advice as `advice:` lines and the re-seed hint.
   - `dummyindex/context/build/enriched_refresh.py`: re-seed a stale style ratchet.
   - Run `dummyindex context check --style --update-ratchet` from the worktree to re-record this repo's `.context/style-budget.txt`.
   - Tests: `tests/context/domains/docbudget/test_style.py`, `test_ratchet.py`, `test_style_ratchet.py`, `tests/cli/test_check_budget.py`.

2. **Writing standard text (C3).**
   - Add `STE_DOC_STANDARD` to `dummyindex/context/output/bootstrap.py`. Use it in `ALWAYS_ON_OUTPUT_POLICY`. Change `ALWAYS_ON_TURN_REMINDER` to "Repo docs follow ASD-STE100".
   - Change the hand-kept copies in `dummyindex/skills/skill.md:59-64`, `docs/COMMANDS.md` and `docs/guide/07-cli.md`.
   - Change the pins in `tests/cli/test_cli_doc_sync_policy_canary.py:285-315`. Add assertions for the `AGENTS.md` block, the managed `CLAUDE.md` block (`tests/context/output/test_claude_md.py`) and the Codex guidance render.

3. **Fleet run kind (C4 prep).** In `dummyindex/context/domains/fleet.py`, add a `kind` field to `FleetRun`, read from `state.json` (default `"maintain"`). `create_run`, `find_newest_run` and `resolve_run_dir` take `kind`, and the kind sets the folder prefix. `to_dict` writes the stored kind. Restyle does not call `estimate_run` or `_owned_files`. Tests: `tests/context/domains/test_fleet.py`, including an old `state.json` without `kind`.

4. **Restyle snapshot (C4 core).**
   - Add the domain package `dummyindex/context/domains/restyle/` (`__init__.py`, `constants.py`, `errors.py`, `models.py`, `snapshot.py`).
   - `snapshot.py` holds `protected_tokens(text)` and `diff_tokens(old, new)`. It expands contractions before it counts negations. A loss or a lower count fails, and a gain warns.
   - Add a public `citations(text)` to `dummyindex/context/domains/docguard/citations.py` that wraps `_citations`. Do not copy the regex.
   - Tests: `tests/context/domains/restyle/test_snapshot.py`.

5. **`restyled_ruleset` meta field.** Add an optional integer `restyled_ruleset` to `Meta` in `dummyindex/context/build/meta.py`. `read_meta` and `write_meta` round-trip it. An old `meta.json` reads as `None`. The `replace(meta, …)` re-stamp at `enriched_refresh.py:337` keeps it. Tests: `tests/context/build/test_meta.py`, with a re-stamp case.

6. **Restyle run and CLI (C4).**
   - Add `dummyindex/context/domains/restyle/run.py` with `plan`, `begin`, `next_unit`, `done`, `stamp` and `status`. It uses these parts: task 3 (run state), task 4 (snapshot), task 1 (`lint_text`, `reseed`) and task 5 (stamp).
   - Store the original text under `.context/cache/restyle/<run>/`. `done` restores `mtime_ns` with `os.utime`.
   - Add the wire-only `dummyindex/cli/restyle.py`. Mirror the flag parse of `dummyindex/cli/maintain.py`.
   - Register `ContextSubcommand.RESTYLE` in `dummyindex/context/enums.py` and in the table in `dummyindex/cli/__init__.py`. Add the usage line to `dummyindex/cli/help.py`, `docs/COMMANDS.md` and `docs/guide/07-cli.md`.
   - Tests: `tests/context/domains/restyle/test_run.py`, `tests/cli/test_restyle.py`, `tests/cli/test_cli_doc_sync.py`.

7. **Generated templates (C6).** Rewrite the prose in `dummyindex/context/output/instructions.py`, `dummyindex/context/output/docs.py` (`generate_index_md`), `dummyindex/context/build/conventions.py` (`write_naming_md`), `dummyindex/skills/equip/templates/*.tmpl`, and the scaffolds in `dummyindex/context/domains/proposals/store.py` and `dummyindex/context/domains/audit/workspace.py` to STE. Keep each path, command and placeholder. Add `tests/context/output/test_template_style.py`, which renders into `tmp_path` and asserts no strict violations. Fix the render tests that pin old prose.

8. **Doc-writing prompts (C7).** Add a "Writing standard" section to `dummyindex/skills/council/00-overview.md`. Add one pointer line to `dummyindex/skills/plan/SKILL.md`, `audit/SKILL.md`, `build/SKILL.md`, `memory/SKILL.md` and the council stages `15-conventions.md`, `20-specify.md`, `30-plan.md`, `50-flow-narrative.md` and `65-reconcile.md`. Call `reseed` for each changed `SKILL.md` in `tests/data/skill-budget.txt`. Keep `tests/test_skills_doc_hygiene.py` green.

9. **Update skill step (C5).**
   - Add step "5. Restyle context prose" to `dummyindex/skills/update/SKILL.md`, after the verify step. Change the first hard rule as C5 says. Add the two report rows.
   - Change `docs/guide/09-lifecycle.md` to match. Call `reseed` for `update/SKILL.md` in `tests/data/skill-budget.txt`.
   - Add a hygiene test in `tests/test_skills_doc_hygiene.py` for the step order.

10. **One-time repo doc rewrite (C8).** Rewrite the repo docs to STE in 3 disjoint groups:
    - (a) `docs/guide/*.md`, `docs/reference/*.md`, `docs/COMMANDS.md`, `README.md`.
    - (b) `dummyindex/skills/council/*.md`, `dummyindex/skills/agents/*.md`, `dummyindex/skills/retrieval/*.md`, `dummyindex/skills/audit/agents/*.md`.
    - (c) Each `SKILL.md`, `dummyindex/skills/skill.md` and the other skill markdown outside (b). Group (c) calls `reseed` for the rewritten `SKILL.md` files.
    - Keep each command, flag, path and pinned string.

11. **Repo doc style test (C8).** Add `tests/test_repo_doc_style.py` and `tests/data/repo-style-budget.txt` with each entry at 0. Reuse `lint_text`, `read_ratchet` and `check`.

12. **Managed blocks.** Regenerate this repo's `AGENTS.md` and `.claude/CLAUDE.md` managed blocks. Use the worktree CLI (`.venv` Python, `-m dummyindex install`) with the current `--platform` and `--scope`. The installed `dummyindex` tool still has the old text. Do not edit the blocks by hand. The installer writes user-level state, so the user runs it.

13. **Dogfood restyle.** Run the restyle loop on this repo's `.context/`. This is an LLM run with a token cost, so the user starts it.

## Track B — ultrareview fixes

14. **B1 toolkit `.gitignore`.** In `dummyindex/context/domains/toolkit/host.py`, call a public wrapper of `_ensure_managed_lines` (`dummyindex/context/build/upgrade.py:77`) before `write_stash`, `WriteSession.backup` and `preserve_skill` write. Fix the docstring at `host.py:9-14`. In `upgrade.py:33`, change `toolkit/` to `/toolkit/`, and replace an existing unanchored line. Tests: `tests/context/domains/toolkit/test_gitignore_guard.py` (new) and `tests/context/build/test_upgrade.py`.

15. **B2 scope resolution.** In `dummyindex/context/domains/toolkit/mutate.py` `_resolve_scope_and_kind`, limit the fallback to project-layout matches and raise `ambiguous_item` on more than one match. In `dummyindex/context/domains/toolkit/listing.py` (`_host_mcp`, `_host_skills`), give one entry for an item that is live and in the stash. The live entry wins. In the same `mutate.py`, fix the G5b sites `:98`, `:179` and `:431` to raise `ToolkitError("malformed_config", …)`. Tests: `tests/context/domains/toolkit/test_mutations.py`.

16. **B3 plugin install.** In `dummyindex/context/domains/toolkit/install.py:194-209`, use the argv sequence of `default_plugins._install_one` (`default_plugins.py:608-629`) with `--scope user`. Add `--scope user` to the hint at `:379-385`. In `toolkit_install` (`dummyindex/context/domains/toolkit/facade.py:186`), default a plugin install to user scope. Do not change `toolkit_mutate` (`facade.py:143`). Tests: `tests/context/domains/toolkit/test_install.py`.

17. **B4 features list.** In `dummyindex/context/domains/features_list.py:18-19`, derive `CONFIDENCE_VALUES` from `ConfidenceLevel` and reuse `_validate_feature_id` (`features/helpers.py:22-33`). Add `AMBIGUOUS` to `tests/fixtures/contract/features-list.json`. Tests: `tests/context/domains/test_features_list.py` and `tests/cli/test_features_list_cli.py`.

18. **B5 robustness.**
    - In `dummyindex/context/domains/toolkit/paths.py:108-120`, check containment for write targets only. Use the read path in the `host.py:46-53` accessors.
    - In `host.py:154-162` `read_object`, map `UnicodeDecodeError` to `malformed_config`. In `dummyindex/context/domains/toolkit/bundle.py:61` `load_manifest`, check the item shape.
    - Confirm that `dummyindex/cli/toolkit.py:178-184` prints the envelope.
    - Tests: `tests/context/domains/toolkit/test_containment.py` and `tests/cli/test_toolkit_cli.py`. Task 18 runs after task 14, because both change `host.py`.

## Reused symbols

- `lint_text`, `count_violations`, `StyleViolation` — `docbudget/style.py` (`doc-budget`).
- `scan`, `check`, `update_ratchet`, `read_ratchet`, `measure` — `docbudget/ratchet.py` (`doc-budget`).
- `create_run`, `load_run`, `next_unit`, `mark_done`, `run_status`, `resolve_run_dir` — `domains/fleet.py`.
- `read_meta`, `write_meta`, `Meta` — `build/meta.py`.
- `ALWAYS_ON_OUTPUT_POLICY`, `ALWAYS_ON_TURN_REMINDER` — `output/bootstrap.py` (`agent-instructions`).
- `_citations` — `docguard/citations.py` (`managed-doc-homes`).
- `_ensure_managed_lines` — `build/upgrade.py:77`.
- `_install_one` — `default_plugins.py:608-629` (`install-surface`).
- `_validate_feature_id` — `features/helpers.py:22-33` (`feature-taxonomy`).
- `ConfidenceLevel` — `pipeline/enums.py`.
