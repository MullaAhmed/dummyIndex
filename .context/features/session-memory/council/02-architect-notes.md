# Architect notes — session-memory (stage 2)

## What I changed

- Replaced the loose "Where it lives" intro with an explicit **Bounded context**
  section stating the one invariant the feature is drawn around (mechanics vs.
  prose) and naming what is in/out of the boundary (the `usage` domain and the
  `/dummyindex-remember` skill are out).
- Added a **Dependency direction** section: upstream (`build/manifest`,
  `atomic_io`), downstream (only the `.claude/settings.json` hooks via the two CLI
  dispatchers — no in-tree Python callers), the deliberate non-edge to `usage`,
  the one-source-three-sinks fan-out of `read_session_signal`, and an explicit
  **no-cycles** note for drift → reconcile_gate (verified: gate imports drift, not
  vice-versa, `reconcile_gate.py:31`).
- Promoted the latent patterns into a dedicated **Patterns named** section, each
  anchored at `path:range` — the two the mandate called out (tiered-store roll;
  emit-only hook signal) plus stand-down, block-once memo, three-oracle
  staleness, and source-drift attribution.
- Promoted Key decisions → numbered **Decisions** with the boundary decision (#1)
  and the layering decision (#2) marked as load-bearing.
- Cut filler: folded the redundant `__init__` re-export sentence into the
  file list; tightened the three-sentence architecture; kept the stale-doc flag
  but reframed it as a code-wins open question rather than prose.

## Patterns named

- Tiered-store roll (cascade-by-date) — `roll.py:43-106`, partition
  `roll.py:21-36`, date key `parse.py:50-53`.
- Emit-only hook signal (decide → render → exit 0) — `nudge.py:101-129`,
  `emit.py:32-60`, `plan_update.py:53-79`, `breadcrumb.py:120-131`.
- Stand-down detection — `detect.py:7-14` (gated `emit.py:33`, `nudge.py:113`,
  `breadcrumb.py:125`).
- Block-once via persisted memo — `nudge.py:33-65`, `reconcile_gate.py:185-226`.
- Three-oracle staleness — `drift.py:144-175,355-369`,
  `reconcile_gate.py:229-238,284-295`.
- Source-drift attribution — `reconcile_gate.py:39,241-270`.

## Dependencies surfaced

- Upstream: `context/build/manifest.read_manifest` (`drift.py:34,338-352`),
  `atomic_io.write_text_atomic` (`atomic_io.py:11-24`).
- Downstream: SessionStart / PreCompact / Stop hooks, reached only through
  `cli/memory.py` + `cli/plan_update.py`.
- Deliberate non-edge: `transcript.py` refuses to import `usage`
  (`transcript.py:5-8`) — preserves acyclic `context → analysis` layering at the
  cost of cross-transcript dedup.
- Shared reader: `read_session_signal` (`transcript.py:84-121`) → breadcrumb,
  nudge, gate.
- No cycles: `reconcile_gate.py:31` imports `DriftReport`/`compute_drift` from
  `drift.py`; drift has no back-reference.

## Decisions promoted

1. Markdown-first, mechanics-only CLI (the boundary) — `memory/__init__.py:1-5`.
2. Stdlib-only reader over `usage` to keep layering acyclic — `transcript.py:5-8`.
3. Three-oracle staleness reconciliation — `reconcile_gate.py:229-238,284-295`.
4. Hooks never fail; atomic writes — `cli/memory.py:94,101,107`,
   `atomic_io.py:11-24`.
5. Stand down for `remember` — `detect.py:7-14`.
6. Block-once, opt-out, submodule-aware gate — `reconcile_gate.py:42-76,315-329`.
7. Source-drift attribution gates the block — `reconcile_gate.py:241-270`.

## Verification

All path:range citations checked against source (corrected three emit.py
citations the prior plan/spec had at offset-view line numbers: render at
`emit.py:32`, gate at `:33`, core at `:50-51`). The stale-doc claim
(`SessionMemoryError`) confirmed absent — `grep` over the domain finds no such
symbol; kept as a code-wins flag. spec.md left untouched; no source edited.
