# Reality-check verifier — plan

confidence: INFERRED

## Where it lives

- `dummyindex/cli/reality_check.py` — the wire-only CLI dispatcher for
  `dummyindex context reality-check`: parses `--feature`/`--json`/`--demote`, resolves the
  context root, calls the domain, prints, returns an exit code
  (`dummyindex/cli/reality_check.py:8-75`).
- `dummyindex/context/domains/reality_check.py` — the whole engine: claim extraction,
  verification, path resolution, report writers, and confidence demotion/promotion.
- `tests/context/domains/test_reality_check.py` — the test surface (claim extraction,
  per-kind verification, path-resolution precedence, demote/promote idempotency, CLI).

## Architecture in three sentences

Claim extraction runs four regexes (`_CALL_RE`, `_USES_RE`, `_HAS_METHOD_RE`,
`_FILE_LINE_RE`) over each canonical doc and dedupes structured `Claim` records keyed on
`(kind, subject, object)` (`reality_check.py:74-88`, `reality_check.py:188-217`).
Verification then resolves each claim against the deterministic AST artefacts loaded once
up front — symbol names + paths from `map/symbols.json`, call/uses edges (resolved by node
`label`, normalized the same way as claims) from `features/symbol-graph.json`, file paths
from `map/files.json`, and the feature's own `files` list — assigning `verified`,
`contradicted`, or `ambiguous` (`reality_check.py:139-185`, `reality_check.py:220-304`,
`reality_check.py:437-523`). `_summarize` tallies the verdicts into an immutable
`RealityReport` that the CLI writes and, with `--demote`, uses to mutate confidence
(`reality_check.py:419-431`).

## Data model

**`_reality-check.json` schema** (`schema_version = 1`, `reality_check.py:60`,
`reality_check.py:127-136`): `{schema_version, feature_id, claims_total, verified,
contradicted, ambiguous, claims[]}`, each claim `{text, source_file, kind, subject, object,
status, reason}` (`reality_check.py:101-110`). For `file:line` claims, `object` holds the
line number as a string (`reality_check.py:95-97`). Verdict rules:

- **calls/uses** — both bare names must exist in `symbols.json`. Missing + repo-rooted (or
  undotted) → `contradicted`; missing + stdlib/third-party-rooted → `ambiguous` (absence
  isn't proof). Both exist + edge in graph → `verified`; both exist, no edge → `ambiguous`
  (`reality_check.py:233-263`, `_is_external_reference` at `reality_check.py:355-377`).
- **has_method** — class + method both in symbols → `verified`, else `contradicted`
  (`reality_check.py:265-273`).
- **file:line** — resolve the path (4-step precedence: exact `files.json` → literal on disk
  → feature's own docs → basename match disambiguated by the feature's `files`, ambiguous on
  a multi-hit; `reality_check.py:307-352`), then check the cited line is within the file's
  line count (`reality_check.py:275-302`).

**Confidence demotion** (`reality_check.py:599-695`): `DEMOTED_FROM_KEY =
"confidence_demoted_from"` stores the pre-demotion value. `demote_feature_on_contradiction`
sets `confidence = AMBIGUOUS` and stashes the prior (only if it's a valid `ConfidenceLevel`
and no stash exists yet), then mirrors into `INDEX.json`; idempotent once already
`AMBIGUOUS`. `promote_feature_on_clean` is the exact inverse: only acts on a clean report
when the feature is `AMBIGUOUS` *and* a valid stash exists, restoring + popping it. Both
write via the atomic tmp-file-then-`replace` helper (`reality_check.py:592-596`).

## Key decisions

- **spec.md is exempt from line-checking** — it is intent-level; only `plan.md`/`concerns.md`
  (and legacy essay docs during the v0.14 window) carry verifiable claims
  (`reality_check.py:1-11`, `reality_check.py:62-71`).
- **Absence ≠ falsehood for external refs** — stdlib/third-party-rooted tokens are reported
  `ambiguous`, never `contradicted`, because `map/symbols.json` can't disprove them
  (`reality_check.py:355-377`). Repo-rooted or undotted misses stay real contradictions.
- **Deterministic path resolution** — fixed precedence, candidate lists always `sorted`,
  multi-hit basenames are `ambiguous` rather than an arbitrary pick
  (`reality_check.py:307-352`).
- **Self-healing confidence loop** — demote/promote are exact inverses, gated to be
  idempotent and non-destructive, with the prior value stashed for restoration
  (`reality_check.py:610-678`).
- **Tolerant IO** — every loader degrades to an empty set on missing/malformed artefacts
  rather than failing the whole check (`reality_check.py:437-523`); writes are atomic and
  byte-faithful (`reality_check.py:592-596`).
- **Exit codes follow the CLI-boundary convention** — `0` clean, `1` contradictions, `2`
  bad args / missing context (`dummyindex/cli/reality_check.py:36-75`).

## Open questions

- The legacy essay docs (`architecture.md`, `implementation.md`, `data-model.md`,
  `security.md`, `product.md`) are still scanned for the v0.14 transition
  (`reality_check.py:63-71`); once all features are re-councilled this list can shrink to
  `plan.md` + `concerns.md`.
- Call-edge resolution depends on `symbol-graph.json` node `label` fields normalizing the
  same way as parsed claims (`reality_check.py:474-484`); a label-format change in the graph
  builder would silently turn `verified` calls into `ambiguous`.
- Verdict `status` strings are bare literals rather than an enum, unlike the codebase's
  closed-alphabet convention (`coding-practices.md` "Enum constants, never bare strings");
  noting as a possible future tightening.
