# Reality-check verifier — plan

confidence: INFERRED

## Bounded context

A read-mostly fact-checker that runs **after** the council writes a feature's canonical
docs (council Phase 3.5, post-`specify`/`plan`/`critique`). It consumes the deterministic
extraction backbone — `map/symbols.json`, `features/symbol-graph.json`, `map/files.json`,
the feature's own `files` list, and source on disk — and emits two report artefacts plus an
optional confidence mutation. It verifies *grounding* (do the cited symbols, call edges, and
`file:line` citations exist?), never *behaviour*. It owns no schema the rest of the engine
reads back: `_reality-check.{json,md}` are leaf outputs; the only write that feeds other
views is the `confidence` mirror into `feature.json` + `features/INDEX.json`.

## Where it lives

- `dummyindex/cli/reality_check.py` — wire-only dispatcher for `dummyindex context
  reality-check`. Parses `--feature`/`--json`/`--demote`, resolves the context root, calls
  the domain, prints, returns the exit code (`dummyindex/cli/reality_check.py:8-75`).
  Unknown args → `2` (`dummyindex/cli/reality_check.py:36-38`).
- `dummyindex/context/domains/reality_check.py` — the engine: claim extraction,
  verification, path resolution, report writers, confidence demote/promote.
- `tests/context/domains/test_reality_check.py` — claim extraction, per-kind verification,
  path-resolution precedence, demote/promote idempotency, CLI behaviour.

## Two-stage pipeline (extract → verify)

**Stage 1 — claim extraction (regex, no AST).** `_extract_claims` runs four module-level
patterns over each canonical doc and dedupes structured `Claim` records keyed on
`(kind, subject.lower, object.lower)` (`reality_check.py:188-217`):

- `_CALL_RE` → `calls` (`reality_check.py:74-77`)
- `_USES_RE` → `uses` (`reality_check.py:78-81`)
- `_FILE_LINE_RE` → `file:line`; `object` holds the line number as a string
  (`reality_check.py:82-84`)
- `_HAS_METHOD_RE` → `has_method` (`reality_check.py:85-88`)

Docs scanned come from `_CANONICAL_DOCS` (`reality_check.py:62-71`) — `plan.md`,
`concerns.md`, plus five legacy essay docs kept for the v0.14 transition. Extracted claims
start with placeholder `status="ambiguous"` (`reality_check.py:200-206`).

**Stage 2 — verification (AST, loaded once).** `reality_check_feature` loads the backbone
artefacts up front, then `_verify_claim` resolves each claim and stamps a verdict via
`_with_status` (`reality_check.py:139-185`, `reality_check.py:220-304`). `_summarize` tallies
the verdicts into an immutable `RealityReport` (`reality_check.py:419-431`). Call-edge match
relies on `symbol-graph.json` node `label` fields normalizing the same way claims do
(`reality_check.py:458-494`).

## Patterns named

- **Claim-extraction → AST-verification split** — extraction is pure-regex and
  AST-free (`_extract_claims`, `reality_check.py:188-217`); verification is the only stage
  that touches symbol/graph/file artefacts (`_verify_claim`, `reality_check.py:220-304`).
  The two never interleave: all backbone loads happen once in `reality_check_feature` before
  any claim is judged (`reality_check.py:139-185`).
- **External-reference guard** — `_is_external_reference` (`reality_check.py:355-377`) gates
  the calls/uses verdict: a missing symbol that is stdlib/third-party/import-rooted is
  `ambiguous` (absence ≠ proof); a missing repo-rooted or undotted name is `contradicted`
  (`reality_check.py:233-263`).
- **Deterministic path resolution** — `_resolve_cited_path` (`reality_check.py:307-352`)
  applies a fixed 4-step precedence with `sorted` candidate lists; multi-hit basenames
  resolve to `ambiguous`, never an arbitrary pick.
- **Self-healing confidence loop (exact-inverse demote/promote)** —
  `demote_feature_on_contradiction` (`reality_check.py:610-645`) and
  `promote_feature_on_clean` (`reality_check.py:648-678`) are gated inverses sharing the
  `DEMOTED_FROM_KEY` stash (`reality_check.py:605`); both write atomically via `_atomic_write`
  (`reality_check.py:592-596`) and mirror through `_mirror_confidence_to_index`
  (`reality_check.py:681-695`).
- **Tolerant IO** — every loader (`_load_symbols`/`_load_call_edges`/`_load_file_paths`/
  `_load_feature_files`, `reality_check.py:437-538`) degrades to empty on missing/malformed
  artefacts rather than failing the run.

## Data model

**`_reality-check.json`** (`SCHEMA_VERSION = 1`, `reality_check.py:60`): `{schema_version,
feature_id, claims_total, verified, contradicted, ambiguous, claims[]}`; each claim
`{text, source_file, kind, subject, object, status, reason}`
(`RealityReport.to_dict`/`Claim.to_dict`, `reality_check.py:101-110`,
`reality_check.py:127-136`). Verdict rules:

- **calls / uses** — both bare names must exist in `symbols.json`. Missing + repo-rooted (or
  undotted) → `contradicted`; missing + external-rooted → `ambiguous`. Both exist + edge in
  graph → `verified`; both exist, no edge → `ambiguous` (`reality_check.py:233-263`).
- **has_method** — class + method both in symbols → `verified`, else `contradicted`
  (`reality_check.py:265-273`).
- **file:line** — `_resolve_cited_path` then a line-count bound check
  (`reality_check.py:275-302`, `reality_check.py:307-352`).

**Confidence demotion** — `DEMOTED_FROM_KEY = "confidence_demoted_from"` stores the
pre-demotion value. Demote sets `confidence = AMBIGUOUS` and stashes the prior only when it's
a valid `ConfidenceLevel` and no stash exists; idempotent once already `AMBIGUOUS`. Promote
is the strict inverse, acting only on a clean report against an `AMBIGUOUS` feature *with* a
valid stash, restoring + popping it (`reality_check.py:610-678`).

## Dependencies surfaced

- **Consumes (read):** `map/symbols.json` (names + paths), `features/symbol-graph.json`
  (call/uses edges by node `label`), `map/files.json`, the feature's `feature.json` `files`
  list, and source on disk. All via tolerant loaders (`reality_check.py:437-538`).
- **Produces (write):** `features/<id>/_reality-check.{json,md}` (`write_report`,
  `reality_check.py:540-548`); with `--demote`, the `confidence` field of `feature.json` +
  the matching row in `features/INDEX.json`.
- **Runs at:** council **Phase 3.5**, after the doc-authoring stages — so the docs it
  fact-checks already exist, and a contradiction can feed back into the persona's
  "fix docs → re-run" loop.
- **Coupling risk:** verification correctness is hostage to `symbol-graph.json` `label`
  formatting (see Open questions).

## Key decisions

- **spec.md is exempt from line-checking** — it is intent-level; only the line-checkable
  docs in `_CANONICAL_DOCS` carry verifiable claims (`reality_check.py:1-11`,
  `reality_check.py:62-71`).
- **Absence ≠ falsehood for external refs** — external-rooted misses are `ambiguous`, never
  `contradicted`, because `map/symbols.json` can't disprove them
  (`_is_external_reference`, `reality_check.py:355-377`).
- **Multi-hit basenames are ambiguous, not guessed** — fixed precedence + `sorted`
  candidates keep resolution deterministic (`reality_check.py:307-352`).
- **Demote/promote are gated, idempotent, non-destructive inverses** — prior value stashed
  for restoration (`reality_check.py:610-678`).
- **Exit codes follow the CLI-boundary convention** — `0` clean, `1` contradictions,
  `2` bad args / missing context (`dummyindex/cli/reality_check.py:36-75`).

## Open questions

- The five legacy essay docs (`architecture.md`, `implementation.md`, `data-model.md`,
  `security.md`, `product.md`) are still scanned for the v0.14 transition
  (`reality_check.py:62-71`); once all features are re-councilled this list shrinks to
  `plan.md` + `concerns.md`.
- Call-edge resolution depends on `symbol-graph.json` `label` fields normalizing the same way
  parsed claims do (`reality_check.py:458-494`); a label-format change in the graph builder
  would silently turn `verified` calls into `ambiguous`.
- Verdict `status` is bare string literals, not an enum — against the closed-alphabet
  convention (`coding-practices.md:32` "Enum constants, never bare strings"); a candidate
  future tightening, not a current bug.
