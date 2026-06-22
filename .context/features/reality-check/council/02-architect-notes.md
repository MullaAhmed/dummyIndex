# Architect notes — reality-check (stage 2)

## What I changed

- Added a **Bounded context** section up front: read-mostly grounding fact-checker that
  emits leaf artefacts (`_reality-check.{json,md}`) and whose only outward-feeding write is
  the `confidence` mirror — clarifies what the rest of the engine does/doesn't read back.
- Recast the "Architecture in three sentences" prose into an explicit **two-stage pipeline**
  (regex extraction → AST verification) with the four regexes split to individual
  `path:range` citations.
- Promoted the implicit patterns into a **Patterns named** section, each pinned at
  `path:range`.
- Fixed drift: extractor is `_extract_claims` (not "claim extraction runs four regexes"),
  verifier is `_verify_claim`, summarizer `_summarize`; constant is `SCHEMA_VERSION`
  (`reality_check.py:60`), not a `schema_version` symbol. Corrected loader range to
  `437-538` and the index-mirror helper to `681-695`.
- Cut filler ("the whole engine", restated verdict prose) and the redundant byte-faithful IO
  decision (folded into the Tolerant-IO pattern + atomic-write citation).

## Patterns named

- Claim-extraction → AST-verification split — `_extract_claims` (`reality_check.py:188-217`,
  AST-free) vs `_verify_claim` (`reality_check.py:220-304`); backbone loaded once in
  `reality_check_feature` (`reality_check.py:139-185`).
- External-reference guard — `_is_external_reference` (`reality_check.py:355-377`) →
  ambiguous-vs-contradicted gate (`reality_check.py:233-263`).
- Deterministic path resolution — `_resolve_cited_path` (`reality_check.py:307-352`).
- Self-healing confidence loop — exact-inverse `demote_feature_on_contradiction`
  (`reality_check.py:610-645`) / `promote_feature_on_clean` (`reality_check.py:648-678`)
  sharing `DEMOTED_FROM_KEY` (`reality_check.py:605`), atomic via `_atomic_write`
  (`reality_check.py:592-596`), mirrored via `_mirror_confidence_to_index`
  (`reality_check.py:681-695`).
- Tolerant IO — loaders `reality_check.py:437-538`.

## Dependencies surfaced

- Consumes: `map/symbols.json`, `features/symbol-graph.json`, `map/files.json`, feature
  `files`, on-disk source — all via tolerant loaders.
- Produces: `_reality-check.{json,md}`; with `--demote`, `confidence` in `feature.json` +
  `features/INDEX.json`.
- Runs at council **Phase 3.5** (post specify/plan/critique), enabling the
  "fix docs → re-run" feedback loop.
- Coupling risk: verdict correctness hostage to `symbol-graph.json` `label` normalization.

## Decisions promoted

- spec.md line-check exemption; absence ≠ falsehood for external refs; multi-hit basenames
  ambiguous (never guessed); demote/promote gated idempotent inverses; CLI-boundary exit
  codes 0/1/2 — each retained with `path:range`.
- Kept the bare-string `status` vs enum convention gap as an Open question, now pinned to
  `coding-practices.md:32`.
