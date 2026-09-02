# Plan — reconcile-guardrails-maintain

> Ordered, file-path-naming tasks. Reuse symbols from `.context/map/symbols.json`;
> every path verified against the working tree.

## Tasks

1. **Config v5.** `dummyindex/context/domains/config.py`: bump
   `CONFIG_SCHEMA_VERSION` to 5, add `_SUPPORTED_SCHEMA_VERSIONS = {1,2,3,4,5}`, add
   `build: BuildPolicy` dataclass `{auto_recouncil: bool = True}` following the exact
   read-migration pattern used for the v3→v4 `default_plugins_enabled` addition
   (`needs_migration`, `read-migrate before validation`). Update the module docstring's
   version history block.
2. **Fleet state domain.** New `dummyindex/context/domains/fleet.py`: frozen dataclasses
   `FleetUnit`, `FleetRun`; `create_run(context_dir, features, estimates) -> FleetRun`,
   `load_run(dir) -> FleetRun`, `next_unit(run) -> FleetUnit | None` (frontier semantics
   reused from `council_batch.next_batch` ordering), `mark_done(run, feature, stage)`,
   `run_status(run)`; all writes atomic via `write_text_atomic`; corrupt-JSON tolerance
   mirroring `drift.py:_manifest_shas`.
3. **Estimator.** In `fleet.py`: `estimate_run(context_dir, features, mode) -> dict`
   composing per-feature node counts from `enrich.build_plan` (reuse; do not duplicate
   traversal) and stage list from `council_batch.active_stages(mode)`. Output labelled
   `estimate:` at print sites.
4. **CLI verb.** New `dummyindex/cli/maintain.py` with subverbs
   `plan|begin|next|done|stamp|status` (argparse shape copied from `cli/gc.py`'s
   multi-subcommand layout). `stamp` delegates to `reconcile.run_stamp` then marks the
   feature done in state. Register in the context command table
   (`cli/__init__.py` seam — same file proposal C touches; coordinate landing).
5. **Anchor auto-heal.** In `cli/reconcile.py::run_stamp` (or the fleet wrapper):
   when the report flags `anchor_orphaned`, re-stamp against HEAD with a loud
   `warning:` line instead of refusing (spec Q1 default), gated behind
   `--heal-orphaned` on `stamp` so scripted callers opt in explicitly.
6. **Build skill contract.** Update `dummyindex/skills/build/SKILL.md` + packaged
   `plan/SKILL.md` closing section: mandatory post-final-wave maintain phase,
   `--no-recouncil` opt-out reading config `build.auto_recouncil`; document that
   skipping prints leftover pending counts.
7. **Build-loop surfacing.** `dummyindex/cli/build_loop/waves.py`: include
   `auto_recouncil` (from resolved config) in `--check/--status` JSON payloads so the
   conductor can honour the flag without re-reading config. No `models.py` change.
8. **Tests** (disjoint files):
   - new `tests/context/domains/test_fleet.py` — create/next/done/status/resume.
   - new `tests/cli/test_maintain.py` — verb wiring incl. scope guard + `--all`.
   - `tests/context/domains/test_config.py` (extend existing) — v5 migration +
     auto_recouncil default/false.
   - `tests/context/build/test_reconcile.py` — orphaned-anchor heal path
     (`--heal-orphaned`) and default refusal unchanged without flag.

## Wave disjointness

| Wave | Items | Files |
|---|---|---|
| 1 | T1 | `domains/config.py` |
| 1 | T2 | `domains/fleet.py` (NEW) |
| 2 | T3 | `domains/fleet.py` — serial after T2, same file |
| 2 | T5 | `cli/reconcile.py` |
| 3 | T4 | `cli/maintain.py` (NEW) + `cli/__init__.py` registry seam |
| 3 | T6 | packaged skills md (disjoint of T4) |
| 3 | T7 | `cli/build_loop/waves.py` |
| 4 | T8a–T8d | one distinct test file each |
