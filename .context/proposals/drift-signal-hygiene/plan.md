# Plan — Classify mtime noise out of drift, add drift ack CLI, JSON output, and a labeled badge split

> Ordered, file-path-naming tasks. Cite reused symbols from
> `.context/map/symbols.json` where you can reuse instead of writing new.

## Tasks

1. **Basis map writer.** In `dummyindex/context/build/reconcile.py`, extend
   `stamp_reconciled` (the function behind `context reconcile-stamp`) to also write
   `.context/cache/doc-basis.json` atomically (reuse `write_text_atomic` from
   `dummyindex/context/domains/atomic_io.py`). Content: for each feature with members,
   `{feature_id: {rel_path: <git blob sha or sha256>}}` computed from the working tree
   at stamp time. Reuse the containment pattern from `runner.py`'s manifest writer.
   Off-git repos: the stamp path already no-ops — the basis write must live inside that
   same gate (no git → no basis file). Refused stamps must not touch the file; extend
   the `StampResult` docstring to state when basis is/isn't written.
2. **Basis reader + classification.** In `dummyindex/context/drift.py`: add
   `_read_doc_basis(context_dir)` mirroring `_manifest_shas`; extend the row loop in
   `compute_drift` so a source whose sha equals its basis entry increments
   `suppressed_count` and produces no row. Fallback order: basis → manifest → report.
   Add `suppressed_count: int = 0` to `DriftReport`.
   Include a `basis_version: 1` key in `doc-basis.json` per the data-access
   schema-versioning convention.
3. **Ack store domain.** New module `dummyindex/context/domains/drift_acks.py`:
   `read_acks(context_dir)`, `append_ack(...)`, `clear_acks(...)` over
   `.context/cache/drift-acks.json` (atomic writes; corrupt-JSON tolerance mirrors the
   `_load_memo` pattern in `dummyindex/context/domains/gc/anchor.py` — return empty on
   parse failure, never raise).
4. **Ack CLI verb.** Register `drift-ack` across the full context-verb seam: `cli/__init__.py` `_HANDLERS`,
   `context/enums.py::ContextSubcommand`, and the usage tables in `cli/help.py` (the
   seam proposal C/E also touch — coordinate landing)
   with flags `--feature --path --reason --list --clear`. Wire-only: parse, delegate to
   the domain, print; follow the CLI thin-wrapper conventions used by `gc.py`.
5. **JSON output for plan-update.** Add `--json` to `dummyindex/cli/plan_update.py`
   rendering the envelope defined in spec §Contracts from the `DriftReport` + ack/basis
   counts. Plain-mode stdout unchanged.
6. **Badge split.** Update `compute_badge` in `dummyindex/context/drift.py` to the
   labeled format `[ctx: E edited · A anchored]`; keep `[ctx ✓]`. Confirm
   `dummyindex/cli/statusline.py` only prints the cached string (no regex assumptions)
   and adjust if it does.
7. **Summary relabel.** `render_drift_summary`: add a new "### Edited since docs" section header (mtime rows currently render
   headerless — this is an addition, not a rename); append the suppression note line when `suppressed_count > 0`.
8. **Tests** (disjoint files):
   - `tests/context/test_drift.py` — basis suppression + fallback chain cases.
   - new `tests/context/domains/test_drift_acks.py` — append/list/clear/expiry.
   - `tests/context/build/test_reconcile.py` — stamp writes basis; refused stamp
     doesn't.
   - new `tests/cli/test_plan_update_json.py` — envelope keys + plain-mode unchanged.
   - `tests/cli/statusline` (or nearest existing badge test home) — labeled format.

## Wave disjointness

| Wave | Items | Files written |
|---|---|---|
| 1 | T1 | `context/build/reconcile.py`, (+its test file in W2) |
| 1 | T2 | `context/drift.py` |
| 1 | T3 | `context/domains/drift_acks.py` (NEW) |
| 2 | T4 | `cli/__init__.py` registry seam, new `cli/drift_ack.py` |
| 2 | T5 | `cli/plan_update.py` |
| 2 | T6 | `context/drift.py` (badge fn) — **serial after T2**, same file |
| 2 | T7 | `context/drift.py` — same-file, fold into T6 task at build time |
| 3 | T8a–T8e | one distinct test file each |

Correction applied at checklist derivation: T2/T6/T7 share `context/drift.py`, so they
are one serial item per wave ordering (see `checklist.md` waves).
