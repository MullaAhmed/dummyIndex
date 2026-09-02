# Plan — fleet-runner

> Ordered, file-path-naming tasks; reuse over net-new. All paths verified.

## Tasks

1. **Domain.** New `dummyindex/context/domains/fleetrun.py`:
   - frozen dataclasses `FleetUnit`, `Budget`, `FleetRunState`;
   - `init_run(context_dir, units, budget_usd, max_parallel, branch_template,
     rulings) -> FleetRunState` writing `RUN-MANIFEST.md` + `state.json` under
     `.context/fleet/run-<id>/` (atomic via `write_text_atomic`,
     `dummyindex/context/domains/atomic_io.py`);
   - `load_run(dir)` (loud failure on corrupt state), `next_units(state, disjoint_map)`
     implementing priority + parallel cap + member-file disjointness + gated skip +
     budget halt; `checkpoint(...)`, `add_spend(...)`, `merge_order(state)`.
   - Disjointness input frozen at init into state.json per-unit `paths[]` (from
     intake JSON entries or optional `member_files`; absent/empty → conservative
     serial + init-time warning). No checklist parsing (`buildloop/checklist.py::
     parse_checklist` items carry no paths — net-new text extraction rejected).
     Freezing at init means later plan edits never mutate a running fleet, and
     state.json stays the single source of truth. Concurrency: monotonic `revision`
     field + read-modify-write retry loop on write conflict (atomic_io replace is
     last-writer-wins). Corrupt state fails loud WITH printed repair/re-init
     instructions (deliberate divergence from gc/anchor.py's tolerant precedent,
     justified: fleet state is the only recovery path by design). Init writes
     RUN-MANIFEST.md first, state.json last; load_run refuses dirs lacking it.
     Deterministic next(): sort key `(priority, unit_id)`; tie traversal stable.
     Zero units or duplicate (id, slug): init refuses. Branch template default is
     neutral `{run}/{id}-{slug}` (caller passes their own).
2. **CLI verb family.** New `dummyindex/cli/fleet.py`: subverbs
   `init|next|checkpoint|spend|merge-order|status` following `cli/gc.py` layout
   (verb dispatch + lazy domain import). Full registration seam: `cli/__init__.py`
   `_HANDLERS`, `context/enums.py::ContextSubcommand`, `cli/help.py` usage tables
   (same seam as B/C/D — coordinate landing order).
3. **Packaged skill + shipping registration.** New
   `dummyindex/skills/fleet/SKILL.md` — host babysitter procedure: intake production
   (Linear MCP stays host-side), grouping rules, planning forks, worktree-isolated
   orchestrators with ground-rules block (invoke build skill; conventional commits +
   magic words; stage only owned files; foreground verification; child reports as
   final output), dormant-agent probe, resume-from-state-only, opt-in merge phase.
   Zero hardcoded repo/team/project identifiers — all from run manifest or flags.
   Shipping: add `skills/fleet/*.md` to pyproject `[tool.setuptools.package-data]`,
   add `("fleet", "dummyindex-fleet")` to `installer/common.py::_SIBLING_SKILLS`,
   update derived installer/doc-sync tests (`tests/test_install_link.py`,
   `tests/test_skills_doc_hygiene.py`, cli doc-sync/update-skill-doc tests).
4. **Tests** (disjoint files):
   - new `tests/context/domains/test_fleetrun.py`;
   - new `tests/cli/test_fleet_cli.py`;
   - fixtures: two minimal proposals with explicit `member_files` in `proposal.json`
     (overlapping and disjoint sets) under `tests/fixtures/fleetrun/`.

## Wave disjointness

| Wave | Items | Files |
|---|---|---|
| 1 | T1 | `domains/fleetrun.py` (NEW) |
| 1 | T4f | fixtures (disjoint) |
| 2 | T2 | `cli/fleet.py` (NEW), `context/enums.py`, `cli/__init__.py`, `cli/help.py` |
| 3 | T3 | packaged `skills/fleet/SKILL.md` (NEW), `pyproject.toml`, `installer/common.py`, installer doc-sync tests |
| 4 | T4a–T4c | one distinct test file each |
