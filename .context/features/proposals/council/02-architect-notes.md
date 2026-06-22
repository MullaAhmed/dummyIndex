# Architect notes — proposals (stage 2)

## What I changed

- Added an explicit **Bounded context** section up front: this feature scans/models/persists
  the `.context/proposals/<slug>/` seed and nothing else — no planning, dispatch, or
  lifecycle. Sharpened the "seed, don't own" boundary so downstream enrichment
  (`reused_symbols`, `## Wave N`, status transitions) is visibly out of scope.
- Renamed the loose "Architecture in three sentences" prose to cite concrete seams:
  `_VALUE_FLAGS propose.py:23`, `resolve_context_root propose.py:19`,
  `write_text_atomic store.py:18`, `cli/__init__.py:116` router entry.
- Replaced the flat "Key decisions" bullet soup with a **Patterns named at path:range**
  section (six located patterns) + a tightened **Decisions** section. Cut filler /
  duplicated rationale; every pattern now carries a `path:range`.
- Added a first-class **Dependencies** section (upstream / downstream / cycles).

## Patterns named

- Strict-layering / CLI-boundary I/O — `store.py:11` (docstring), exit-code mapping in `propose.py`.
- Copy-on-write update — `apply_consistency store.py:111-139` (`dataclasses.replace`).
- Single-chokepoint validation / security boundary — `validate_slug store.py:36-51`,
  routed by `proposals_root store.py:54-56` + `proposal_dir store.py:59-61`.
- Idempotent sentinel block — `_inject_consistency store.py:206-215`, markers `store.py:27-28`.
- Tolerant deserialization — `Proposal.from_dict models.py:39-53`.
- Graceful degradation — `_related_features scan.py:35-43` (swallows `FileNotFoundError`).

All ranges verified against `.context/map/symbols.json` (definition lines match).

## Dependencies surfaced

- **Upstream:** `query` domain (`scan.py:11`) — sole ranking engine; `atomic_io.write_text_atomic`
  (`store.py:18`); `cli/common.resolve_context_root` (`propose.py:19`).
- **Downstream (feeds build loop):** `build_loop/waves.py` parses `checklist.md`
  (`waves.py:14`) and reads spec+plan as the dispatch grounding set
  (`_grounding_paths waves.py:132-138`); `status.py:143-153` reads `proposal.json`;
  `/dummyindex-plan` writes prose + `reused_symbols` + waves; `/dummyindex-build` drives the checklist.
- **Cycles:** none — clean one-directional fan-out. Flagged the load-bearing seam: the
  plan/spec this feature only *seeds* becomes build's ground truth.

## Decisions promoted

- Deterministic no-LLM scan (`scan.py:1-6,11`).
- Slug as the single security boundary (`store.py:36-51`).
- Idempotent consistency injection (`store.py:27-28,206-215`).
- Atomic CLI-only I/O.
- Self-parsing CLI (`propose.py:8-12,23`).
- "Seed, don't own" — forward-schema seams left empty deliberately.

Spec.md and source left untouched. Open questions preserved (proposals_root visibility,
bare FileNotFoundError asymmetry, status-transition owner).
