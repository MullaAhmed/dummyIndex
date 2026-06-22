# Source-doc catalog — plan

confidence: INFERRED

## Where it lives

`dummyindex/context/domains/source_docs/` — the catalog package: `discovery.py` (find docs), `refs.py` (extract + cross-check references), `keys.py` (harvest JSON keys), `catalog.py` (`build_doc_catalog` — the orchestrator), `models.py` (`DocEntry` / `DocCatalog`), `writers.py` / `readers.py` (`INDEX.{json,md}` I/O), `constants.py` (thresholds + banner), `__init__.py` (public surface). Cross-area `DocConfidence` lives in `dummyindex/context/enums.py:12-37`. Doc-text extraction for PDF/office defers to `dummyindex/pipeline/io/detect.py`. The consumer-side renderer is `dummyindex/context/output/docs.py` (`PROJECT.md` description + "Existing documentation" section). Tests: `tests/context/domains/test_source_docs.py`, `tests/context/output/test_docs.py`.

## Architecture in three sentences

`build_doc_catalog` walks each discovered doc, reads its text (markdown direct; PDF/docx/xlsx via `detect.py` converters), extracts backticked code refs, and cross-checks them against the AST symbol set + repo file paths + harvested JSON keys + a framework whitelist to compute `broken_refs`. It then folds broken-ratio, an age bucket (`newest_code_mtime − doc_mtime`), and a broken-count floor into a `high/medium/low` confidence and emits a frozen `DocEntry` per doc. `write_catalog` serializes the sorted `DocCatalog` to `.context/source-docs/INDEX.{json,md}` atomically; the engine is fully deterministic so identical inputs yield byte-identical output.

## Data model

**`DocEntry`** (frozen, `models.py:9-46`): `path`, `abs_path`, `doc_type`, `title`, `headings`, `sha256`, `size_bytes`, `mtime`, `age_delta_seconds`, `age_bucket`, `referenced_count`, `broken_refs`, `broken_ratio`, `confidence`, `is_external`, `source_root`. `to_dict` rounds `broken_ratio` to 4 places (`models.py:42`); `from_dict` tolerates missing keys with defaults.

**`DocCatalog`** (frozen, `models.py:73-103`): `schema_version` (=1, `constants.py:4`), `generated_at` (ISO seconds), `repo_root`, `docs`, `extra_doc_roots`, `default_discovery_used`. `to_dict` adds derived `doc_count` + `by_confidence` (`_confidence_breakdown`, `models.py:106-110`).

**Confidence derivation** (`_classify_confidence`, `catalog.py:64-88`) from tunable thresholds (`constants.py:7-9`): `_HIGH_BROKEN_RATIO=0.10`, `_LOW_BROKEN_RATIO=0.40`, `_MIN_BROKEN_FOR_LOW=4`. Age buckets (`catalog.py:26-32`): `fresh` (doc newer than code, `≤ -1`), `recent` (≤30d), `aging` (≤90d), `stale` (≤180d), `old` (>180d), `unknown` (no code mtime). The `unknown` bucket maps to `high` at low broken-ratio so a first build with no comparable code mtime doesn't mass-demote docs (`catalog.py:86-87`).

**Reference whitelists** (`refs.py:25-79`): `_PROSE_WHITELIST` (English filler in backticks) and `_FRAMEWORK_WHITELIST` (Claude Code tools/hooks, `.context/` artifact filenames, dummyindex schema field names) — both prevent false-positive broken refs. `extra_names` (typically `harvest_json_keys` output) extends this per-repo.

## Key decisions

- **Deterministic, AST-grounded grading** — confidence is computed, not modelled, so the catalog is reproducible and the council can trust it as evidence. Stable sort + sorted JSON + ISO-seconds timestamp make re-runs byte-identical (`catalog.py:189-195`).
- **Conservative ref extraction** — `looks_like_code_ref` would rather miss a real ref than flag English prose as broken (`refs.py:82-94`); fenced code blocks are stripped entirely (`refs.py:193-195`).
- **Tiny-doc floor** — `_MIN_BROKEN_FOR_LOW=4` stops a one-line ADR that names a feature by example from crashing to `low` (`catalog.py:69-75`).
- **Widened path-set** — `file_paths` is the *full* detected set (code + docs + papers + config), not just code, because prose cites READMEs, schema JSON, and generated artifacts; a code-only set drives false `broken_refs` (`catalog.py:113-118`).
- **`DocConfidence.__str__ = str.__str__`** — pins the enum to its value across the Python 3.11 `Enum.__format__` change so `INDEX.md` never leaks `DocConfidence.LOW` (`enums.py:24-30`).
- **Atomic, byte-faithful writes** — tmp-file + `replace` per the data-access convention (`writers.py:109-113`).
- **External docs** keep absolute `path` + `is_external=True` + `abs_path` audit trail; in-repo docs stay repo-relative POSIX (`catalog.py:91-95`, `163-186`).

## Open questions

- `find_broken_refs` rebuilds `file_basenames` on every call (`refs.py:233-235`); for a large `doc_paths` corpus the path-set is re-derived per doc. Acceptable at current scale; a hoisted basename set would cut redundant work.
- The catalog reads each doc's bytes twice — `read_bytes()` for `sha256` plus `extract_doc_text()` re-reading text (`catalog.py:137-143`). Fine for prose-sized files; not for very large converted PDFs.
- `harvest_json_keys` caps at 5000 keys (`keys.py:13`); on repos with huge JSON corpora some legitimate schema field names past the cap could be reported broken. No signal surfaced when the cap is hit.
- Age uses a single `newest_code_mtime` scalar, so a doc edited just before one late code change is judged against that one file, not the subsystem it documents — coarse but cheap.
