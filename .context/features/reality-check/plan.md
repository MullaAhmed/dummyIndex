# reality-check — plan

`confidence: INFERRED`

> Architect note: the deterministic backbone (`map/symbols.json`) is STALE — it still
> indexes the pre-refactor single file `context/domains/reality_check.py` and contains
> no symbols for the package modules below. Every `path:range` here was verified against
> the **real source on disk** (the code wins), not the map. Run
> `dummyindex context rebuild --changed` to re-index the package; `feature.json` still
> lists both the old file and the new modules.

## Bounded context

One domain, one job: **fact-check curated prose against the deterministic backbone and
the real tree, then optionally self-heal the index's confidence.** It owns no source
truth — it is a *read-mostly auditor* over three upstream artefacts (symbols, call graph,
file paths) plus the feature's own docs, and it writes back to exactly one place: a
feature's `confidence` (and its mirror in `INDEX.json`).

The package is a textbook **concern-seam split** of a former single file (pure
move-refactor; public import path `dummyindex.context.domains.reality_check` unchanged).
Six modules layered strictly **models → extract → verify → render → confidence**, with
`__init__` as the façade:

| Module | Concern | Depends on |
| --- | --- | --- |
| `models.py` (55 ll) | data only — `Claim`, `RealityReport`, `SCHEMA_VERSION` (`models.py:7`) | — (leaf) |
| `extract.py` (70 ll) | doc text → claims (regex layer) | `models` |
| `verify.py` (384 ll) | claims + backbone → verdicts (orchestrator) | `models`, `extract`, `dev_pick` |
| `render.py` (66 ll) | report → JSON+MD on disk (sink) | `models` |
| `confidence.py` (111 ll) | report → confidence demote/promote (effect) | `models`, `render`, `pipeline.enums` |
| `__init__.py` (101 ll) | public façade + contract docstring | all of the above |

## Architecture: the extract → verify → confidence-mirror pipeline

`reality_check_feature` (`verify.py:21-67`) is the **orchestrator**. It loads the four
upstream artefacts **once** (`verify.py:35` and the loaders at `verify.py:287-384`), then
for each doc in `_CANONICAL_DOCS` (`extract.py:13-21`) runs `_extract_claims`
(`extract.py:41-70`) and `_verify_claim` (`verify.py:70-154`) per claim. Three stages:

1. **claim-extraction** (`extract.py`) — four regexes (`_CALL_RE`/`_USES_RE`/
   `_FILE_LINE_RE`/`_HAS_METHOD_RE`, `extract.py:24-38`) turn prose into typed `Claim`s,
   deduped on `(kind, subject.lower, object.lower)` (`extract.py:41-70`).
2. **verify** (`verify.py`) — `_verify_claim` dispatches by `claim.kind`, returning a
   *new* `Claim` via `_with_status` (`verify.py:246-256`); nothing mutates in place.
   `_summarize` (`verify.py:269-281`) folds verdicts into an immutable `RealityReport`.
3. **confidence-mirror** (`confidence.py`) — reads only `report.has_contradictions` and
   `report.feature_id`; flips the feature's `confidence` and mirrors it into
   `INDEX.json` (`confidence.py:97-111`). This is the only write-back into the index.

`render.py` is an orthogonal **sink** off stage 2 (serialize the report); it is also
reused by `confidence.py` for its atomic JSON write — see Dependencies.

## Data model

Two **frozen dataclasses** (immutable by construction), each with `to_dict()`:

- `Claim` (`models.py:11-29`): `object` doubles as the line-number string for `file:line`
  claims (a deliberate field-overload, `models.py:17`).
- `RealityReport` (`models.py:33-55`): counts + a `tuple[Claim, ...]`; the
  `has_contradictions` property (`models.py:43-44`) is the **single decision input** for
  both the CLI exit code and the demote/promote branch.

Read-side loaders (all in `verify.py`, all fault-tolerant — see decisions):
`_load_symbols` → `(names, name→path)` from `map/symbols.json` (`verify.py:287-305`);
`_load_call_edges` from `features/symbol-graph.json` (`verify.py:308-343`);
`_load_file_paths` from `map/files.json` (`verify.py:346-360`); `_load_feature_files`
delegates to `dev_pick.read_feature_files` (`verify.py:363-373`).

Write-side: both reports are written through `render._atomic_write`
(write-`.tmp`-then-`replace`, `render.py:62-66`), reused by `confidence.py` for the
`feature.json`/`INDEX.json` updates.

## Dependencies

Upstream artefacts consumed (read-only): `map/symbols.json`, `features/symbol-graph.json`,
`map/files.json`, the feature's `*.md` docs.

Code dependencies that cross a module/layer boundary:

- **`verify.py:15` → `dummyindex.context.domains.dev_pick.read_feature_files`** — the one
  *cross-domain* edge. reality-check leans on dev-pick to enumerate a feature's files.
- **`confidence.py:13` → `dummyindex.pipeline.enums.ConfidenceLevel`** — a *cross-layer*
  edge into `pipeline`. Verdicts and stash comparisons use the enum, not string literals
  (`confidence.py:47-48` compares `prior == ConfidenceLevel.AMBIGUOUS`).
- **`confidence.py:16` → `.render._atomic_write`** — intra-package reuse; `render` is the
  shared write primitive, so the layering is models → render ← {verify, confidence}.

Downstream consumer: the CLI dispatcher `dummyindex/cli/reality_check.py:8-75` (unchanged)
imports the public surface **lazily inside `run`** (`cli/reality_check.py:16-22`) — keeps
import cost off the CLI's cold path. No cycles: `models` is a clean leaf; `__init__`
re-exports but nothing imports `__init__` internally.

Public surface is `__init__.__all__` (`__init__.py:91-101`); the contract docstring
(`__init__.py:1-54`) is the human-facing spec of the whole pipeline.

## Decisions (decided X because Y)

- **Decided: absence ≠ falsehood for out-of-repo referents** — because the backbone only
  indexes repo symbols, so a docstring citing `os.environ` or a third-party call must not
  be flagged. `_is_external_reference` (`verify.py:205-227`) and the basename-ambiguity
  branch of `_resolve_cited_path` (`verify.py:194-202`) downgrade unknowns to `ambiguous`.
  This is the load-bearing correctness property of the whole domain.
- **Decided: deterministic path precedence** — because the same doc must always yield the
  same verdict. `_resolve_cited_path` (`verify.py:157-202`) never indexes an unsorted set:
  `candidates = sorted(...)` (`verify.py:187-189`), multi-match disambiguation intersects
  with `feature_files` (`verify.py:196`).
- **Decided: edges matched by normalized label, not id** — because claim tokens and graph
  node labels are shaped differently. `_load_call_edges` strips `()`/leading-dot/dotted-
  prefix per node label (`verify.py:330-334`) to match `_bare_name`'s output
  (`verify.py:258-266`), so claims and edges compare like-for-like.
- **Decided: demote/promote are strict inverses and idempotent** — because a council loop
  may run reality-check repeatedly. Re-demoting an already-`AMBIGUOUS` feature is a no-op
  that preserves the stash (`confidence.py:47-48`); promote fires only with a valid stash
  on a clean report (`confidence.py:73-87`). All writes mirror into `INDEX.json`
  (`confidence.py:97-111`).
- **Decided: every IO loader degrades, never raises** — because a broken backbone should
  produce a degraded report, not a crash. Missing/corrupt JSON → empty
  (`verify.py:290-295`, `confidence.py:42-45`).
- **Decided: CLI imports the package lazily** (`cli/reality_check.py:16-22`) — keeps the
  domain's import graph (which reaches into `pipeline` and `dev_pick`) off the CLI's hot
  path.

## Open questions

- Legacy essay docs (`architecture.md`, `implementation.md`, `data-model.md`,
  `security.md`, `product.md`) are still scanned (`extract.py:13-21`) per the v0.14
  transition note in `__init__.py:7-11`; whether to drop them once all features are
  re-councilled is unsettled.
- `_load_call_edges` reads `links` then falls back to `edges` (`verify.py:336`) — the dual
  key signals an unsettled graph schema upstream in `symbol-graph.json`.
- The stale `map/symbols.json` means a reality-check run *against this repo* would resolve
  package symbols via on-disk fallback, not the index. Re-running `rebuild --changed`
  before the next council pass would close the gap.
