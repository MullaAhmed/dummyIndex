# Architect notes — source-docs (stage 2)

## What I changed

- Replaced the loose "Where it lives" prose with a **Bounded context** section that states the one thing this feature owns (grade prose against the AST, persist the verdict) and the two things it explicitly does *not* own (doc-text extraction → `detect.py`; `PROJECT.md` rendering → `output/docs.py`). The boundary is named: the `DocCatalog` dataclass.
- Added a **Pattern catalog** table naming every catalog pattern at `path:range` — discovery / readers / refs / whitelist-feed / confidence-grading / age-bucketing / orchestrator / writers — matching the mandate's discovery/readers/refs/writers/confidence-grading axes.
- Folded the "Architecture in three sentences" blob into a numbered **Flow** (read → cross-check → grade) with line anchors per stage, cutting narrative filler while keeping every load-bearing range.
- Kept the data model intact (verified ranges) and tightened thresholds/buckets/whitelists into the model section.
- Promoted the decisions list, flagging the deterministic-grading decision as the single load-bearing one and tying three decisions to their proving tests.

## Patterns named

All verified against `.context/map/symbols.json` and source:
- Catalog discovery: `discover_default_doc_paths` `discovery.py:35-67`.
- Readers: `extract_doc_text` / `extract_code_refs:191-205` / `looks_like_code_ref:82-121`.
- Refs: `find_broken_refs:208-243` (7-stage precedence), whitelist feed `harvest_json_keys:13-47`.
- Confidence grading: `_classify_confidence:64-88`, age `_classify_age:55-61`.
- Writers: `_render_catalog_md:26-94`, atomic `_atomic_write:109-113`.
- Orchestrator: `build_doc_catalog:98-200`.

## Dependencies surfaced

New explicit **Dependencies** section splitting producer vs consumer:
- **Feeds**: `PROJECT.md` (`output/docs.py:generate_project_md:122`, `_render_doc_section:249`), `architecture/overview`, `features/<id>/docs.md` (per-feature doc sections, top-N capped), and the council (this engine emits the doc-evidence the council trusts).
- **Depends on**: `pipeline/io/detect.py` (office/PDF conversion), `enums.py:DocConfidence`, and the AST symbol set + full `file_paths` set fed into `find_broken_refs`.

## Decisions promoted

- Deterministic AST-grounded grading (flagged load-bearing; `catalog.py:191-199`).
- Conservative ref extraction (`refs.py:82-121`, fence strip `193-195`).
- Tiny-doc floor `_MIN_BROKEN_FOR_LOW=4` (`catalog.py:64-88`).
- `unknown` age → `high` at low ratio (`catalog.py:86-87`).
- Widened path-set (`catalog.py:113-118`).
- `DocConfidence.__str__ = str.__str__` 3.11 pin (`enums.py:24-30`, proven by `test_doc_confidence_str_is_value_not_enum_repr`).
- Atomic byte-faithful writes (`writers.py:109-113`) and external-doc absolute-path / in-repo POSIX split (`catalog.py:91-95`, `163-186`).

Forbidden content avoided: no astronautics, no unlocated patterns, no invented rationale; spec.md and source untouched.
