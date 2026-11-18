# Checklist — All authored .context docs and repo docs follow ASD-STE100; dummyindex-update rewrites all context prose to STE

> Waves run in order. Items in one wave touch different files and run in parallel.
> Tick `- [x]` only after you verify the item. No live-testing or production steps.

## Wave 1 — foundations and independent fixes

- [x] T1 STE lint rules, STYLE scope, `reseed`, ruleset header and transition (`docbudget/style.py`, `docbudget/constants.py`, `docbudget/ratchet.py`, `cli/check.py`, `build/enriched_refresh.py`, `.context/style-budget.txt`, `tests/context/domains/docbudget/`, `tests/cli/test_check_budget.py`)
- [x] T2 `STE_DOC_STANDARD` and policy text (`output/bootstrap.py`, `skills/skill.md`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `tests/cli/test_cli_doc_sync_policy_canary.py`, `tests/context/output/test_claude_md.py`)
- [x] T3 fleet run `kind` (`domains/fleet.py`, `tests/context/domains/test_fleet.py`)
- [x] T4 restyle snapshot package and public `citations` (`domains/restyle/`, `docguard/citations.py`, `tests/context/domains/restyle/test_snapshot.py`)
- [x] T14 B1 toolkit `.gitignore` guard and `/toolkit/` anchor (`toolkit/host.py`, `build/upgrade.py`, `tests/context/domains/toolkit/test_gitignore_guard.py`, `tests/context/build/test_upgrade.py`)
- [x] T15 B2 scope fallback, live/stash dedupe, mutate G5b sites (`toolkit/mutate.py`, `toolkit/listing.py`, `tests/context/domains/toolkit/test_mutations.py`)
- [x] T16 B3 plugin install argv, hint and install-only user-scope default (`toolkit/install.py`, `toolkit/facade.py`, `tests/context/domains/toolkit/test_install.py`)
- [x] T17 B4 features list confidence set and id rule (`domains/features_list.py`, `tests/fixtures/contract/features-list.json`, `tests/context/domains/test_features_list.py`, `tests/cli/test_features_list_cli.py`)

## Wave 2 — meta stamp, templates, prompts, toolkit robustness

- [x] T5 `restyled_ruleset` in `Meta`, kept by the re-stamp (`build/meta.py`, `tests/context/build/test_meta.py`)
- [x] T7 STE generated templates, scaffolds and template lint test (`output/instructions.py`, `output/docs.py`, `build/conventions.py`, `proposals/store.py`, `audit/workspace.py`, `skills/equip/templates/*.tmpl`, `tests/context/output/test_template_style.py`)
- [x] T8 writing standard section, pointer lines and skill-budget re-record (plan task 8 files) — via agent:dummyindex-docs-specialist
- [x] T18 B5 read-safe containment and `malformed_config` mapping (`toolkit/paths.py`, `toolkit/host.py`, `toolkit/bundle.py`, `cli/toolkit.py`, `tests/context/domains/toolkit/test_containment.py`, `tests/cli/test_toolkit_cli.py`)

## Wave 3 — restyle command

- [x] T6 restyle run domain and wire-only CLI (`domains/restyle/run.py`, `cli/restyle.py`, `context/enums.py`, `cli/__init__.py`, `cli/help.py`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `tests/context/domains/restyle/test_run.py`, `tests/cli/test_restyle.py`)

## Wave 4 — update skill

- [x] T9 update skill step 5, hard rule, report rows and skill-budget re-record (`skills/update/SKILL.md`, `docs/guide/09-lifecycle.md`, `tests/test_skills_doc_hygiene.py`, `tests/data/skill-budget.txt`)

## Wave 5 — one-time repo doc rewrite

- [x] T10a STE rewrite of `docs/guide/*.md`, `docs/reference/*.md`, `docs/COMMANDS.md`, `README.md` — via agent:dummyindex-docs-specialist
- [x] T10b STE rewrite of `skills/council/*.md`, `skills/agents/*.md`, `skills/retrieval/*.md`, `skills/audit/agents/*.md` — via agent:dummyindex-docs-specialist
- [x] T10c STE rewrite of each `SKILL.md`, `skills/skill.md` and other skill markdown, with skill-budget re-record (`tests/data/skill-budget.txt`) — via agent:dummyindex-docs-specialist

## Wave 6 — repo doc style test

- [x] T11 repo doc style test and ratchet at 0 (`tests/test_repo_doc_style.py`, `tests/data/repo-style-budget.txt`)

## Wave 7 — acceptance

- [x] Acceptance: each new strict rule flags its sample, and the same words in backticks give no flag
- [x] Acceptance: `ing-form` and `passive` samples print `advice:` lines and `check --style` exits 0
- [x] Acceptance: CRLF + BOM input gives the same lint result as LF input
- [x] Acceptance: a long frontmatter `description:` gives no violation
- [x] Acceptance: a new `context propose` scaffold and a new audit scaffold give no strict violations
- [x] Acceptance: a `# ruleset 0` style ratchet passes `check --style` with a re-seed hint, and `--update-ratchet` writes `# ruleset 1`
- [x] Acceptance: `check --style` on a fixture scans flows, playbooks, proposals and audits, and skips `HOW_TO_USE.md`, `INDEX.md`, `naming.md`, `equipment/*.md`
- [x] Acceptance: rendered `AGENTS.md`, managed `CLAUDE.md` and Codex guidance contain `ASD-STE100` and not `caveman style`
- [x] Acceptance: `restyle done` exits 1 and names the token for a lost citation, numeral or `not`
- [x] Acceptance: `restyle done` passes when a doc changes `don't` to `do not`
- [x] Acceptance: after `restyle done`, the doc `mtime_ns` equals the snapshot value
- [x] Acceptance: `restyle begin` exits non-zero when an unfinished restyle run exists
- [x] Acceptance: `restyle stamp` writes `restyled_ruleset`, and `restyle plan` then prints `already restyled`
- [x] Acceptance: the enriched refresh re-stamp keeps `restyled_ruleset`
- [x] Acceptance: `restyle stamp` leaves `features/INDEX.json`, `cache/doc-basis.json` and the reconcile anchor byte-identical
- [x] Acceptance: `reseed` raises a word-ratchet entry and `update_ratchet` does not
- [x] Acceptance: an old maintain `state.json` without `kind` loads as a maintain run
- [x] Acceptance: the generated-template test passes with no strict violations
- [x] Acceptance: a hygiene test asserts that `update/SKILL.md` names `context restyle` after the verify step
- [x] Acceptance: `tests/test_repo_doc_style.py` passes and each `repo-style-budget.txt` entry is 0
- [x] Acceptance B1: a stash write adds `/toolkit/`, and `git check-ignore` does not match `.context/features/toolkit/spec.md`
- [x] Acceptance B2: a user-only match with `--allow-project-fallback` gives no user-scope edit, and a live + stashed item resolves with `--kind`
- [x] Acceptance B3: the install argv is `marketplace add`, then `install`, with no `--marketplace`
- [x] Acceptance B3: the hint has `--scope user`, and `toolkit_mutate` keeps project scope
- [x] Acceptance B4: an `AMBIGUOUS` feature and an `auth_flow` feature both list, and `skipped` is 0
- [x] Acceptance B5: `toolkit list --json` exits 0 with a symlinked `settings.json`, and a UTF-16 `.mcp.json` gives `malformed_config`
- [x] Acceptance: the full test suite passes
- [x] Review the branch diff — via /code-review

## Wave 8 — user gates

- [ ] **GATE** T12 regenerate the `AGENTS.md` and `.claude/CLAUDE.md` managed blocks with the worktree CLI (plan task 12)
- [ ] **GATE** T13 dogfood `dummyindex context restyle` on this repo's `.context/` (LLM spend, the user starts it)
