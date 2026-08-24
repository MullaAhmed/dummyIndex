# Checklist — drift-signal-hygiene

> Derived from `plan.md` tasks + `spec.md` § Acceptance. Waves run strictly in order;
> items inside a wave are file-disjoint (proof: `plan.md` § Wave disjointness).

## Wave 1 — domain layer (disjoint files)

- [x] T1 `stamp_reconciled` writes `cache/doc-basis.json` (atomic, sha fallback,
      refused stamp untouched) — `dummyindex/context/build/reconcile.py`
- [x] T3 ack store: `read_acks/append_ack/clear_acks` over
      `cache/drift-acks.json`, atomic + corrupt-tolerant —
      `dummyindex/context/domains/drift_acks.py` (NEW)

## Wave 2 — classification + surfaces (drift.py items are serial within this wave)

- [x] T2 basis reader + row suppression + `suppressed_count` field —
      `dummyindex/context/drift.py`
- [x] T6+T7 labeled badge `[ctx: E edited · A anchored]` + summary relabel +
      suppression note; verify statusline consumer — `dummyindex/context/drift.py`,
      check `dummyindex/cli/statusline.py` (after T2)

## Wave 3 — CLI surfaces (disjoint files)

- [x] T4 `context drift-ack` verb (`--feature --path --reason --list --clear`) —
      new `dummyindex/cli/drift_ack.py` + registry seam in `cli/__init__.py`
- [x] T5 `plan-update --json` envelope (documented keys; plain mode unchanged) —
      `dummyindex/cli/plan_update.py`

## Wave 4 — tests (one distinct file each)

- [x] T8a basis suppression + fallback chain — `tests/context/test_drift.py`
- [x] T8b append/list/clear/expiry — `tests/context/domains/test_drift_acks.py` (NEW)
- [x] T8c stamp writes basis / refused stamp doesn't —
      `tests/context/build/test_reconcile.py`
- [x] T8d JSON envelope keys + plain-mode byte-identical —
      `tests/cli/test_plan_update_json.py` (NEW)
- [x] T8e labeled badge format — existing badge/statusline test home

## Wave 5 — acceptance

- [x] A1 pytest `-k basis` green — via dummyindex-verify (4 passed)
- [x] A2 pytest `-k ack` green incl. expiry-on-edit — via dummyindex-verify (166 passed)
- [x] A3 `--json` keys exact; plain output unchanged on clean repo — via
      dummyindex-verify (test_plan_update_json 4 passed)
- [x] A4 badge shape test green — via dummyindex-verify (26 badge/statusline passed)
- [x] A5 full suite `python -m pytest tests/ -q --tb=short` green — 3189 passed,
      2 skipped (opt-in behavior_arms + optional graspologic); ruff clean
- [x] A6 landing commit uses `feat:` type; body names the badge format change and the
      two new cache artifacts. No hand-edit of `CHANGELOG.md`.
