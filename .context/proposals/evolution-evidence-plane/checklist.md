# Checklist — Evolution evidence plane

> Waves run in order; items inside a wave touch disjoint files. Tick only after the named tests pass.
> Code rule: no long comments. Fixtures only; no live host sessions.

## Wave 1 — units
- [ ] Add `observe/enums.py`, `observe/models.py`, `observe/keys.py`, `observe/security.py` with `tests/context/domains/test_observe_units.py` (plan task 1)

## Wave 2 — lock, local ledger, importer
- [ ] Add `observe.lock` to the allowlist in `evolve_promotion.py`; add `observe/ledger.py` and `observe/importer.py` with `tests/context/domains/test_observe_import.py` (plan task 2)

## Wave 3 — stage-2 interface + scan_hosts rewire
- [ ] Add `observe/attribution.py` and `observe/__init__.py` with `tests/context/domains/test_observe_attribution.py` (plan task 3)
- [ ] Rewire `dummyindex/context/domains/evidence.py`; update `tests/context/domains/test_evidence.py` (plan task 4)

## Wave 4 — hook + doc
- [ ] Register the async Stop entry in `dummyindex/context/hooks.py`; extend `tests/context/test_hooks.py` (plan task 5)
- [ ] Reconcile `.context/features/evolution/concerns.md` (plan task 6)

## Wave 5 — acceptance
- [ ] Acceptance (`test_hooks.py`): one async `evolve evidence` Stop hook, no `timeout`, muted streams; `async` survives the JSON round trip
- [ ] Acceptance (`test_hooks.py`): reinstall skips Stop; old managed Stop refreshed; co-located user hook survives; uninstall removes the hook
- [ ] Acceptance (`test_evidence.py`): human correction counted locally; `gc/evidence/` and `gc/learning/` stay empty on a fresh fixture
- [ ] Acceptance (`test_evidence.py`): no file under `.context/gc/` holds the sha256 of the raw session ID or correction text
- [ ] Acceptance (`test_evidence.py`): schema-1 migration keeps `exposure`, keeps `read_ledger()` events and cursors, adds no duplicates on rerun
- [ ] Acceptance (`test_evidence.py`): fake clock stops after 1 of 3 files with `complete: false`; rerun completes
- [ ] Acceptance (`test_evidence.py`): unchanged size and mtime opens nothing; mtime-only touch re-reads
- [ ] Acceptance (`test_evidence.py`): held `observe.lock` returns `skipped: locked`; `DUMMYINDEX_EVOLUTION=off` writes nothing; lineage tests unchanged
- [ ] Acceptance (`test_observe_units.py`): per-key `keyed_id`; key created once and re-read; POSIX 0600; every C7 range and pattern; `retention_days` fallback
- [ ] Acceptance (`test_observe_import.py`): injected, meta, internal and tool-result-only rows never become corrections
- [ ] Acceptance (`test_observe_import.py`): U+200B tool result quarantines; buffer resets at the next human turn
- [ ] Acceptance (`test_observe_import.py`): Read at turn 1 then correction at turn 2 gives the candidate with a fully stamped row
- [ ] Acceptance (`test_observe_import.py`): `Skill` item; ignored non-allowed paths; win32 backslash and drive-case match
- [ ] Acceptance (`test_observe_import.py`): turns continue across imports; forked copies add no duplicates
- [ ] Acceptance (`test_observe_attribution.py`): packet order, skips, 1,000-char truncation, expiry on a missing transcript
- [ ] Acceptance (`test_observe_attribution.py`): `record_attribution` validation including `path#rule`
- [ ] Acceptance (`test_observe_attribution.py`): no raw session ID on disk; `session_tool_calls` is `None` without the transcript; stub passes `durable_evidence` with only stub keys
- [ ] Acceptance: plan task 7 pytest selection and ruff pass; `test_evolve.py`, `test_evolve_learning.py`, `test_evolve_cli.py` unchanged and green
