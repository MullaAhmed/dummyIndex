# Existing docs that touch `community-22`

_Pointer list — the canonical entries (with confidence + broken-references) live in `../../source-docs/INDEX.md`. **Treat doc claims as hypotheses; verify against `feature.json` + `../../map/symbols.json` before quoting.**_

- [`docs/internal/audits/audits/2026-06-13-full-audit-log.md`](../../../docs/internal/audits/audits/2026-06-13-full-audit-log.md) (**DocConfidence.MEDIUM** — Full audit — 2026-06-13 (overnight autonomous run)) _matched on:_ `path:tests/test_skills_doc_hygiene.py`
  - ⚠ broken refs: `docs/audits/2026-06-13-evidence/raw-findings.json`, `docs/audits/2026-06-13-REPORT.md`
- [`CHANGELOG.md`](../../../CHANGELOG.md) (**DocConfidence.LOW** — Changelog) _matched on:_ `symbol:instructions.py`
  - ⚠ broken refs: `.context/equipment.json`, `checklist.md`, `stop_hook_active`, … +120 more
- [`docs/internal/audits/01-dead-broken-incomplete.md`](../../../docs/internal/audits/01-dead-broken-incomplete.md) (**DocConfidence.LOW** — 01 — Dead / broken / incomplete audit) _matched on:_ `symbol:sample_repo`
  - ⚠ broken refs: `NotImplementedError`, `languages/objc.py`, `build/maps.py`, … +22 more
