# Plan — Wire legacy root CLAUDE.md migration into the fresh-install/bootstrap path

Grounding: every path and signature below was opened and verified in source
during planning (and re-verified by the critique panel). Scope expanded by
user decision 2026-08-25: `context rebuild` folds too (Surface 3).

## Reused symbols (verified)

- `migrate_claude_md_location(out_root: Path) -> None` —
  `dummyindex/cli/migrate.py:74`. Wire-only wrapper; prints
  `  migration: {message}` to stdout, warnings to stderr.
- `reconcile_claude_md(out_root: Path) -> ClaudeMdReconcileResult` —
  `dummyindex/context/output/claude_md.py:96`; frozen result dataclass at :57;
  closed-alphabet `ClaudeMdAction` at :33.
- `is_project_instruction_path(path, project_root, *, instruction_paths=None)
  -> bool` — `dummyindex/codex_guidance.py:111`; conservative component-match.
- Test scaffolding to mirror: `_ingested()` copytree+init pattern
  (`tests/cli/test_migrate.py:34`; seed legacy root AFTER it returns — :73-89
  models the order); `_make_repo_with_source` (`tests/test_install.py:1615`);
  codex auto-init test (:1667); enriched seeder shape `_make_enriched_context`
  (`tests/context/output/test_claude_md_build.py:114`) — duplicate locally,
  no cross-module test imports.

## Tasks (wave-ordered)

### Wave 1

1. **Shared predicate.** In `dummyindex/cli/migrate.py`, add NEW wire-only
   `has_foldable_legacy_claude_md(out_root: Path) -> bool`: True iff
   `(out_root / "CLAUDE.md").exists()` AND not
   `is_project_instruction_path(out_root / "CLAUDE.md", out_root)` — with a
   docstring stating both guard rationals (no-create for Codex-only trees;
   never delete an active Codex instruction file). Local import of
   `codex_guidance` matching the module's style (:84).

### Wave 2 (three disjoint consumer files, parallel)

2. **Bootstrap wiring.** `dummyindex/cli/bootstrap.py`: after the codex/both
   write block, before `return 0` (:74): if platform is `claude|both` AND
   `has_foldable_legacy_claude_md(out_root)` → `migrate_claude_md_location`
   inside one `try/except (OSError, UnicodeError, ValueError)` printing a
   stderr warning. Exit code unchanged. Local-import style (:11-16).
3. **Installer wirings.** `dummyindex/installer/install/project_init.py`:
   enriched branch condition becomes `use_claude or
   has_foldable_legacy_claude_md(project_root)` around the existing reconcile
   block (:95-100); full-build branch adds a post-`build_all` guarded fold
   when not `use_claude`, print in neighboring style (:98), defensive
   exception posture like surrounding best-effort prints.
4. **Rebuild wiring.** `dummyindex/cli/rebuild.py`: guarded fold after EVERY
   success exit — changed-skipped (:60), enriched-preserved (:63),
   changed-rebuilt (:71), full build (:100). Fold before each `return 0`;
   same warn-and-continue posture as Task 2. Rebuild must still never CREATE
   guidance (predicate guarantees no creation).

### Wave 3 (three disjoint test files, parallel)

5. **Bootstrap tests.** NEW `tests/cli/test_bootstrap_migration.py`; every
   test `@pytest.mark.integration`. Trees via `_ingested()`
   (`tests/cli/test_migrate.py:34`); seed legacy root AFTER `_ingested()`.
   Platform spelling `agents` in codex-side cases (deprecated alias prints an
   order-dependent once-per-process notice); exact stdout-substring
   assertions only. Cases = spec Acceptance 1–6 (fold, malformed-marker
   degradation, no-root silence, agents-no-fold, both-platform,
   codex-fallback-doc guard).
6. **Installer tests.** Extend `tests/test_install.py` near :1667:
   fresh-repo codex-only fold; no-root negative regression guard (mirrors
   :1686); enriched-preserved codex reinstall fold via locally duplicated
   curated-context seeder. Explicit `@pytest.mark.integration`.
7. **Rebuild tests.** NEW `tests/cli/test_rebuild_migration.py`; explicit
   integration markers; copytree+init tree, seed AFTER build; cases:
   `--changed` folds legacy root on rebuilt path AND on enriched-preserved
   path AND on skipped path; bare rebuild on a non-enriched tree folds; no-
   root runs print no `migration:` line; codex-fallback-doc root untouched.

### Wave 4

8. **Acceptance run** — execute spec Acceptance commands (`uv run pytest -q`,
   `uv run ruff check .`) and confirm every criterion maps to a task 5–7 test.

## Wave disjointness

| Wave | Item | Writes |
|---|---|---|
| 1 | Task 1 | dummyindex/cli/migrate.py |
| 2 | Task 2 | dummyindex/cli/bootstrap.py |
| 2 | Task 3 | dummyindex/installer/install/project_init.py |
| 2 | Task 4 | dummyindex/cli/rebuild.py |
| 3 | Task 5 | tests/cli/test_bootstrap_migration.py (NEW) |
| 3 | Task 6 | tests/test_install.py |
| 3 | Task 7 | tests/cli/test_rebuild_migration.py (NEW) |
| 4 | Task 8 | nothing (verification) |

Inverse map: no file under two items of one wave. Wave 2 consumers depend on
the wave-1 symbol (import-time), hence separate waves. Wave 3 reads wave-2
outputs, writes disjoint files. Task 8 reads all, runs alone last.
