# Checklist — enriched-refresh-manifest-stamp

> Derived from the revised `plan.md` tasks + `spec.md` § Acceptance, after the critique panel.
> Waves run strictly in order; items inside a wave are mutually independent (proof:
> `plan.md` § Wave disjointness). Tick `- [x]` only after verifying.

## Wave 1 — the two seams

- [x] T1 Swap change detection to `map/files.json` fingerprints + guard the manifest fallback against corrupt JSON (`dummyindex/context/build/incremental.py:118-124`, `:363-377`)
- [x] T2 Write `cache/manifest.json` inside `stamp_reconciled`, with `runner.py:272-279`'s warn-don't-raise containment, deriving `manifest_files` the `runner.py:267-270` way (`dummyindex/context/build/reconcile.py:251`)

## Wave 2 — tests (four disjoint files)

- [x] T3 `test_changed_rebuild_uses_files_json_fingerprints` + `test_consecutive_changed_rebuilds_reach_steady_state`, reusing `primed_repo` (`:32-38`) and `_enrich` (`:122-149`), `@pytest.mark.integration`, no frontmattered `.md` in the fixture (`tests/context/build/test_incremental.py`)
- [x] T4 `test_stamp_reconciled_restamps_manifest` + `test_refused_stamp_does_not_touch_manifest`, with the `"2000-01-01T00:00:00+00:00"` sentinel for `generated_at` (`tests/context/build/test_reconcile.py`)
- [x] T5 `test_mtime_row_survives_changed_rebuild_and_clears_on_stamp`, including the non-empty negative control required by `conventions/testing.md:41` (`tests/context/test_drift.py`)
- [x] T6 `test_changed_rebuild_on_curated_repo_succeeds`, reusing that file's `primed_repo` (`:24-29`) and `_curate` (`:32-44`) (`tests/cli/test_rebuild_cli.py`)

## Wave 3 — owner decision

- [x] **GATE** T7 Confirm the `dummyindex context check` semantic change ("changed since last build" → "changed since last reconcile", `cli/check.py:87`) and settle spec Open questions 2 and 3 before the commit body is written

## Wave 4 — acceptance

- [x] A1 `uv run pytest tests/context/build/test_incremental.py -k test_changed_rebuild_uses_files_json_fingerprints` — via dummyindex-verify
- [x] A2 `uv run pytest tests/context/build/test_incremental.py -k test_consecutive_changed_rebuilds_reach_steady_state` — via dummyindex-verify
- [x] A3 `uv run pytest tests/context/build/test_reconcile.py -k test_stamp_reconciled_restamps_manifest` — via dummyindex-verify
- [x] A4 `uv run pytest tests/context/build/test_reconcile.py -k test_refused_stamp_does_not_touch_manifest` — via dummyindex-verify
- [x] A5 `uv run pytest tests/context/test_drift.py -k test_mtime_row_survives_changed_rebuild_and_clears_on_stamp` — via dummyindex-verify

## Wave 5 — landing

- [x] A6 `uv run pytest tests/cli/test_rebuild_cli.py -k test_changed_rebuild_on_curated_repo_succeeds` — via dummyindex-verify
- [x] A7 Full suite green on the CI command: `python -m pytest tests/ -q --tb=short` exits 0 — via dummyindex-verify
- [x] A8 Landing commit uses the `fix:` conventional type (so `scripts/release.py:63-66` emits `### Fixed`) and its body names the `check` semantic change. **No hand-edit of `CHANGELOG.md`.**
- [x] Review the full diff against spec.md and plan.md
