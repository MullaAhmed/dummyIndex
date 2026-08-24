# Checklist — Wire legacy root CLAUDE.md migration into the fresh-install/bootstrap path

## Wave 1 — shared guard predicate

- [x] Add `has_foldable_legacy_claude_md(out_root: Path) -> bool` to
      dummyindex/cli/migrate.py (exists-guard + not-active-Codex-instruction
      guard; docstring states both rationals)

## Wave 2 — consumer wiring (disjoint files)

- [ ] Fold in `context bootstrap` run(): platform claude|both AND predicate →
      `migrate_claude_md_location(out_root)` before `return 0`, warn-and-
      continue posture (dummyindex/cli/bootstrap.py)
- [ ] Installer auto-init folds: enriched branch condition `use_claude or
      predicate`, full-build post-build guarded fold when not use_claude,
      neighboring print style (dummyindex/installer/install/project_init.py)
- [ ] Fold after every successful `context rebuild` exit — changed-skipped,
      enriched-preserved, changed-rebuilt, full build — never creating
      guidance (dummyindex/cli/rebuild.py)

## Wave 3 — tests (disjoint files)

- [ ] New integration module for bootstrap Acceptance 1–6: fold,
      malformed-marker degradation, no-root silence, agents-no-fold,
      both-platform, codex-fallback-doc guard; seed AFTER `_ingested()`;
      substring assertions only (tests/cli/test_bootstrap_migration.py — NEW)
- [ ] Installer cases near tests/test_install.py:1667: fresh-repo codex-only
      fold, no-root negative guard, enriched-preserved codex reinstall fold;
      explicit integration markers (tests/test_install.py)
- [ ] New integration module for rebuild folding on all four success exits +
      no-root silence + Codex-fallback-doc untouched (tests/cli/test_rebuild_migration.py — NEW)

## Wave 4 — acceptance

- [ ] `uv run pytest -q` green (full suite)
- [ ] `uv run ruff check .` passes
