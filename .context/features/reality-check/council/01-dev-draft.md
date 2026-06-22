# reality-check — plan

`confidence: INFERRED`

## Where it lives

The logic is a package `dummyindex/context/domains/reality_check/` (formerly the single file `reality_check.py` — pure move-refactor, public import path unchanged). Six modules, layered data → extract → verify → render/confidence:

- `__init__.py:56-101` — public re-exports + the docstring that documents the whole contract. `__all__` (`__init__.py:91-101`) is the stable surface.
- `models.py:10-55` — `Claim` and `RealityReport` frozen dataclasses, `SCHEMA_VERSION` (`models.py:7`). Data only, each with `to_dict()`.
- `extract.py:13-70` — the `_CANONICAL_DOCS` tuple (`extract.py:13-21`), four claim regexes (`_CALL_RE`/`_USES_RE`/`_FILE_LINE_RE`/`_HAS_METHOD_RE`, `extract.py:24-38`), and `_extract_claims` (`extract.py:41-70`) which dedupes on `(kind, subject.lower, object.lower)`.
- `verify.py:21-385` — the orchestrator `reality_check_feature` (`verify.py:21-67`), `_verify_claim` (`verify.py:70-154`), path resolution `_resolve_cited_path` (`verify.py:157-202`), the external/repo-root heuristics (`verify.py:205-243`), `_summarize` (`verify.py:269-281`), and the four JSON loaders (`verify.py:287-384`).
- `render.py:10-66` — `write_report` (`render.py:10-18`), `render_report_md` (`render.py:21-59`), `_atomic_write` (`render.py:62-66`).
- `confidence.py:26-111` — `demote_feature_on_contradiction`, `promote_feature_on_clean`, `_mirror_confidence_to_index`, keyed on `DEMOTED_FROM_KEY` (`confidence.py:21`).

CLI dispatcher `dummyindex/cli/reality_check.py:8-75` (unchanged) imports the public surface lazily inside `run` (`cli/reality_check.py:16-22`).

## Architecture in three sentences

`reality_check_feature` (`verify.py:21-67`) loads four artefacts once — symbols, call edges, file paths, the feature's own files — then reads each doc in `_CANONICAL_DOCS`, runs `_extract_claims`, and verifies every claim against that loaded state. `_verify_claim` (`verify.py:70-154`) dispatches by `claim.kind`, returning a *new* `Claim` via `_with_status` (`verify.py:246-255`) — nothing is mutated in place. `_summarize` folds the verdicts into an immutable `RealityReport`, which `render.py` serializes and `confidence.py` reads to demote/promote the feature.

## Data model

Two frozen dataclasses, both append-only JSON via `_atomic_write` (write-to-`.tmp`-then-`replace`, `render.py:62-66`):

- `Claim` (`models.py:10-29`): `object` doubles as the line-number string for `file:line` claims (`models.py:17`).
- `RealityReport` (`models.py:32-55`): counts + a `tuple[Claim, ...]`; `has_contradictions` (`models.py:42-44`) drives both the CLI exit code and the demote path.

Read-side: `_load_symbols` → `(names, name→path)` from `map/symbols.json` (`verify.py:287-305`); `_load_call_edges` resolves graph edges by node `label` from `features/symbol-graph.json` (`verify.py:308-343`); `_load_file_paths` from `map/files.json` (`verify.py:346-360`); `_load_feature_files` delegates to `read_feature_files` (`verify.py:363-373`, the one cross-domain dependency, `verify.py:15`).

## Key decisions

- **Absence ≠ falsehood for out-of-repo referents.** `_is_external_reference` (`verify.py:205-227`) and the basename-ambiguity branch of `_resolve_cited_path` (`verify.py:194-202`) downgrade unknowns to `ambiguous`. This is the load-bearing correctness property — it's why a docstring citing `os.environ` or a third-party call doesn't get flagged.
- **Deterministic path precedence.** `_resolve_cited_path` (`verify.py:157-202`) never indexes an unsorted set: `candidates = sorted(...)` (`verify.py:187-189`), and multi-match disambiguation intersects with `feature_files`. Same input → same verdict.
- **Edges matched by normalized label, not id.** `_load_call_edges` strips `()`/leading-dot/dotted-prefix on each node label (`verify.py:330-334`) so the edge set is shaped like `_bare_name` output (`verify.py:258-266`) — claims and edges compare apples to apples.
- **Demote/promote are strict inverses and idempotent.** Re-demoting an already-`AMBIGUOUS` feature is a no-op preserving the stash (`confidence.py:47-48`); promote only fires with a valid stash on a clean report (`confidence.py:73-87`). All writes mirror into `INDEX.json` (`confidence.py:97-111`).
- **Every IO loader is fault-tolerant.** Missing/corrupt JSON degrades to empty rather than raising (`verify.py:290-295`, `confidence.py:42-45`) — a broken backbone yields a degraded report, not a crash.

## Open questions

- The legacy essay docs (`architecture.md`, `implementation.md`, `data-model.md`, `security.md`, `product.md`) are still scanned (`extract.py:13-21`) per the v0.14 transition note in `__init__.py:7-11`; whether to drop them once all features are re-councilled is unsettled.
- `_load_call_edges` reads `links` then falls back to `edges` (`verify.py:336`) — the dual key suggests an unsettled graph schema.
