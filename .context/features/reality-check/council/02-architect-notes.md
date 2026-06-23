# 02 — Architect notes (stage 2, reality-check)

## What I changed

- Replaced the loose "Where it lives / Architecture in three sentences" prose with a
  **bounded-context** statement (read-mostly auditor; one write-back target) and a
  per-module concern/dependency **table** — every line range re-verified against real
  source on disk, since `map/symbols.json` is stale (see below).
- Renamed the architecture section to the named pipeline **extract → verify →
  confidence-mirror**, with `render` called out as an orthogonal sink rather than a
  fourth stage.
- Added a dedicated **Dependencies** section (the draft buried deps inside prose and
  undercounted them — see below).
- Rewrote "Key decisions" as **decided-X-because-Y** so each rationale is explicit.
- Kept the draft's two genuine open questions; added a third (the stale map).
- `spec.md` untouched.

## Patterns named (and where they live)

- **Concern-seam package split** — `models / extract / verify / render / confidence /
  __init__`; strict layering models → extract → verify → render → confidence.
- **extract → verify → confidence-mirror pipeline** — orchestrated by
  `reality_check_feature` (`verify.py:21-67`); stages at `extract.py:41-70`,
  `verify.py:70-154`, `confidence.py:26-111`.
- **Façade** — `__init__.__all__` (`__init__.py:91-101`) is the only public surface;
  import path unchanged across the refactor.
- **Immutable transform** — `_with_status` (`verify.py:246-256`) returns a new `Claim`;
  both dataclasses frozen (`models.py:11-55`).
- **Shared write primitive** — `render._atomic_write` (`render.py:62-66`) reused by
  `confidence.py:16`.

## Dependencies surfaced

- The draft called the cross-domain dep "the one" — it is **not** the only boundary edge.
  Three exist:
  - `verify.py:15` → `dummyindex.context.domains.dev_pick.read_feature_files` (cross-domain).
  - `confidence.py:13` → `dummyindex.pipeline.enums.ConfidenceLevel` (cross-LAYER, into
    `pipeline` — the draft missed this entirely).
  - `confidence.py:16` → `.render._atomic_write` (intra-package reuse).
- No cycles: `models` is a leaf; nothing imports `__init__` internally.
- Downstream: CLI `cli/reality_check.py:8-75` imports lazily (`16-22`).

## Decisions promoted

- Lazy CLI import (`cli/reality_check.py:16-22`) promoted from an unremarked detail to a
  decision: it keeps the `pipeline`/`dev_pick`-reaching import graph off the CLI cold path.
- Enum-not-literal confidence comparison (`confidence.py:47-48`) made explicit — the draft
  said `"AMBIGUOUS"` as a string; the code compares the `ConfidenceLevel` enum.

## Flags (code wins over docs)

- **`map/symbols.json` is STALE.** It still indexes the deleted single file
  `context/domains/reality_check.py` and has **zero** symbols for the package modules.
  Verified by reading the real files on disk; every cited range matches the source.
  Recommend `dummyindex context rebuild --changed` before the next council/reality-check
  pass. `feature.json` lists both old and new paths.
- Minor: the draft's external-heuristic span "`verify.py:205-243`" conflates
  `_is_external_reference` (`205-227`) with `_repo_module_names` (`230-244`); the plan now
  cites them separately.
