# Checklist — Fix CLAUDE.md onboarding-dangling and Stop-gate reconcile-blindness bugs

> Work wave-by-wave, top-to-bottom. Items in a wave touch disjoint files and may
> run in parallel; a wave starts only when the previous is fully ticked. Tick
> `- [x]` only after verifying. NOTE: `installer/install.py` is split across
> Wave 1 (task 5) and Wave 2 (task 4) on purpose — same file must not run in
> parallel.

## Wave 1 — independent primitives (disjoint files)
- [x] Create `dummyindex/context/output/claude_md.py`: `ClaudeMdReconcileResult` + `reconcile_claude_md` with inode-safety, all-block stripping, no-`UnbalancedMarkersError`-escape, idempotent merge, write-then-delete, `write_text_atomic` (plan task 1) — via python-implementer
- [x] Add `drifted_features` (last, defaulted) to `DriftReport`; forward from `compute_drift` at both returns; extend `has_drift`/`compute_badge`/`render_drift_summary` with de-dup vs `by_feature()` (`dummyindex/context/drift.py`, plan task 6) — via python-implementer
- [x] Export `is_non_source_path` (context OR tool paths) from `dummyindex/context/build/reconcile.py` (plan task 7) — via python-implementer
- [x] Replace the `"dummyindex" in content` probe with a `_SKILL_REGISTRATION`-sentinel check (`dummyindex/installer/install.py:171`, plan task 5) — via python-implementer

## Wave 2 — wiring + gate hardening (depend on Wave 1; disjoint files)
- [x] Reduce `migrate_claude_md_location` to a wire-only wrapper over `reconcile_claude_md` (`dummyindex/cli/migrate.py`, plan task 2) — via python-implementer
- [x] Wire `build_all` to `reconcile_claude_md` (`dummyindex/context/build/runner.py:19,262-263`, plan task 3) — via python-implementer
- [x] Wire BOTH `_auto_init_project` branches (full-build + enriched-preserved) to `reconcile_claude_md` and drop the stale import (`dummyindex/installer/install.py`, plan task 4) — via python-implementer
- [x] Harden the Stop gate — F6 (block on `drifted_features` + directive wording), F11 (shared predicate), F9 (scoped advisory), F10 (subagent-edit signal) (`dummyindex/context/reconcile_gate.py` + `dummyindex/context/domains/memory/transcript.py`, plan task 8) — via python-implementer

## Wave 3 — tests (depend on the code they cover; disjoint test files)
- [x] Unit tests for every `reconcile_claude_md` branch incl. inode/markers/idempotency/write-failure (`tests/context/output/test_claude_md.py`, plan task 9) — via python-tester
- [x] Integration test: fresh install/build seeded with a root `CLAUDE.md` (with/without block) + enriched re-install branch (`tests/context/output/test_claude_md_build.py`, plan task 10) — via python-tester
- [x] User-scope skill-registration test (sentinel present vs bare word) (`tests/test_install.py`, plan task 11) — via python-tester
- [x] `refresh-indexes` legacy-layout + CLAUDE.md consolidation test (`tests/cli/test_migrate.py`, plan task 12) — via python-tester
- [x] Gate real-stamped-anchor block test (no monkeypatch; rewrite the booby-trapped silence test), F9/F10/F11 cases, and `drifted_features` propagation (`tests/context/test_reconcile_gate.py` + `tests/context/test_drift.py`, plan task 13) — via python-tester

## Wave 4 — review, verify, acceptance
- [x] Review the full diff — via /code-review
- [x] Run the verify gate: full suite green on the test command, all new tests marked — via /dummyindex-verify
- [x] Acceptance sign-off: confirm every `## Acceptance` criterion in `spec.md` is met (especially the red-before-green gate test and the no-data-loss CLAUDE.md invariants)
