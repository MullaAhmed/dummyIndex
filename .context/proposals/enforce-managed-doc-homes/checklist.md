# Checklist — enforce-managed-doc-homes

> Wave N groups are mutually independent (disjoint files) and dispatch in parallel;
> waves run strictly in order. Tick `- [x]` only after the item's test is observed green.

## Wave 1 — foundations (independent files)
- [x] T0 — `context/git.py` git-fact seam (`is_git_repo`/`is_tracked`/`run_git`) + `tests/context/test_git.py` (model `run_git` on `build/git_delta.py:_run_git`; no cross-domain private imports)
- [x] T0b — `context/config.py`: add typed `doc_guard_enabled: bool = True` + `doc_guard_allow: tuple = ()`, bump `CONFIG_SCHEMA_VERSION` 2→3, value-preserving `migrate_config_in_place` step, cheap tolerant `(enabled, allow_globs)` accessor + tests
- [x] T1 — `domains/docguard/{__init__,constants,enums,errors,models,classify}.py` classifier + `tests/context/domains/docguard/test_classify.py` (matrix incl. `docs/superpowers/plans`, negative controls, pairing, awkward-slug)

## Wave 2 — consumers (depend on Wave 1; disjoint files)
- [x] T2 — `domains/docguard/migrate.py` + add `write_proposal_json` to `proposals/store.py` + `test_migrate.py` (transactional pre-validate; non-git branch-first; tracked `git mv` / untracked `Path.replace`+`add`; `--force` fills-missing-only; status `done`, no template checklist; symlink/containment skips)
- [x] T3 — `domains/docguard/decision.py` + `cli/guard_doc_write.py` + `tests/cli/test_guard_doc_write_e2e.py` (Write-only; never `exit 2`; fail-open everywhere; allowlist + config gate; no subprocess; interpolated deny reason)

## Wave 3 — CLI + hook wiring (depend on Wave 2; disjoint files)
- [x] T4 — `cli/migrate_docs.py` (`--root/--yes/--force/--json`, dry-run default) + `tests/cli/test_migrate_docs_cli.py` (snapshot-moves-nothing, sorted listing, `--json` key sets, e2e `--yes`)
- [x] T5 — `context/hooks.py` + `cli/hooks.py`: add PreToolUse `Write` guard entry (built from `_SILENT_GATE` so `_guard_body` inserts the global guard); extend `HookStatus`+`all_installed`+`status()`+`uninstall`; **update the breaking exact-assertion tests** in `tests/context/test_hooks.py` + add scrub/preservation/idempotency tests

## Wave 4 — central registration (depends on both CLIs existing)
- [x] T6 — `context/enums.py` add `MIGRATE_DOCS`/`GUARD_DOC_WRITE` to `ContextSubcommand`; register both verbs in the `context` dispatcher + `cli/help.py`; write `.context/playbooks/migrate-stray-docs.md` ("commit the move alone") + `HOW_TO_USE.md` pointer; extend `tests/cli/test_subcommand_help.py`

## Wave 5 — integration + acceptance
- [x] T7 — **GATE** run the full suite (`conventions/testing.md`) and walk every spec `## Acceptance` box against real CLI output on a throwaway fixture repo; tick only on observed green
- [x] Acceptance: `migrate-docs --yes` on a fixture relocates strays history-preserved (`R` in index), writes valid `proposal.json`, and `gc status` lists each migrated workspace
- [x] Acceptance: `guard-doc-write` denies a fresh `Write` to `docs/specs/x-design.md`, allows managed/user-doc/allowlisted paths, and fails open (exit 0) on every malformed input — never `exit 2`
- [x] Acceptance: `hooks install` wires the `Write` guard idempotently (byte-stable), preserves foreign user hooks, and `all_installed` includes it
