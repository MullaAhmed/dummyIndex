# Source-doc catalog — plan

confidence: INFERRED

## Bounded context

This feature owns one thing: grading prose docs against the current AST and persisting the verdict. It does *not* own doc-text extraction (`pipeline/io/detect.py`) or the `PROJECT.md` rendering (`output/docs.py`). The boundary is the `DocCatalog` dataclass. Everything inside `domains/source_docs/` produces it. Everything outside consumes it.

**Package** `dummyindex/context/domains/source_docs/` (one module per phase, per the folder-organization convention):

- `discovery.py` — *catalog discovery*: well-known files/dirs + root `*.md`/`*.rst` (`discover_default_doc_paths:58-97`).
- `refs.py` — *readers + refs*: doc-text/title/heading extraction, ref extraction, broken-ref cross-check.
- `keys.py` — *refs* (whitelist feed): `harvest_json_keys:15-51` harvests repo JSON schema keys.
- `catalog.py` — the *confidence-grading* orchestrator: `build_doc_catalog:99-202`.
- `models.py` — `DocEntry` / `DocCatalog` frozen dataclasses.
- `writers.py` / `readers.py` — *writers*: `INDEX.{json,md}` atomic I/O.
- `constants.py` — thresholds + advisory banner; `__init__.py` — public surface.

**Cross-area touch-points** (kept out of the package on purpose):
- `dummyindex/context/enums.py:12-37` — `DocConfidence` (shared enum, not source-docs-local).
- `dummyindex/pipeline/io/detect.py` — PDF/office → markdown conversion (upstream of the reader).
- `dummyindex/context/output/docs.py` — `PROJECT.md` description + "Existing documentation" renderer (downstream consumer).

Tests: `tests/context/domains/test_source_docs.py`, `tests/context/output/test_docs.py`.

## Pattern catalog (named at path:range)

| Pattern | Symbol | Location |
|---|---|---|
| **Catalog discovery** | `discover_default_doc_paths` | `discovery.py:58-97` |
| **Reader** (text) | `extract_doc_text` / `extract_title_and_headings` | `refs.py` |
| **Reader** (refs) | `extract_code_refs` (strips fences, keeps backticked code-shaped tokens) | `refs.py:278-293` |
| **Ref shape gate** | `looks_like_code_ref` (conservative — prefers a miss to a false flag) | `refs.py:166-205` |
| **Ref cross-check** | `find_broken_refs` (7-stage match precedence) | `refs.py:295-367` |
| **Whitelist feed** | `harvest_json_keys` (cap 5000) | `keys.py:15-51` |
| **Confidence grading** | `_classify_confidence` | `catalog.py:65-89` |
| **Age bucketing** | `_classify_age` | `catalog.py:56-62` |
| **Orchestrator** | `build_doc_catalog` | `catalog.py:99-202` |
| **Writer** (md table) | `_render_catalog_md` | `writers.py:28-100` |
| **Writer** (atomic) | `_atomic_write` (tmp + `replace`) | `writers.py:115-120` |

## Flow (one orchestrator, three stages)

`build_doc_catalog` (`catalog.py:99-202`) runs each discovered doc through three stages.

1. **Read** — `read_bytes()` gives `sha256` and `stat`. Then `extract_doc_text` reads markdown directly. PDF, docx, and xlsx go through `detect.py`. Then `extract_title_and_headings` and `extract_code_refs` run (`catalog.py:138-145`).
2. **Cross-check** — `find_broken_refs` matches each backticked token against AST symbols, repo file paths, JSON keys, then the framework whitelist. `broken_ratio = len(broken)/len(refs)`, or `0.0` when there are no refs (`catalog.py:146-153`).
3. **Grade** — fold `broken_ratio`, the age bucket (`newest_code_mtime − doc_mtime`), and a broken-count floor into `high/medium/low`. Emit a frozen `DocEntry` (`catalog.py:156-190`).

Entries sort by confidence, then path (`catalog.py:192`). `write_catalog` serializes the `DocCatalog` to `.context/source-docs/INDEX.{json,md}` atomically. Identical inputs give byte-identical output.

## Data model

**`DocEntry`** (frozen, `models.py:15-52`): `path`, `abs_path`, `doc_type`, `title`, `headings`, `sha256`, `size_bytes`, `mtime`, `age_delta_seconds`, `age_bucket`, `referenced_count`, `broken_refs`, `broken_ratio`, `confidence`, `is_external`, `source_root`. `to_dict` rounds `broken_ratio` to 4 places (`models.py:47`). `from_dict` tolerates missing keys with defaults.

**`DocCatalog`** (frozen, `models.py:80-116`): `schema_version` (=1, `constants.py:5`), `generated_at` (ISO seconds), `repo_root`, `docs`, `extra_doc_roots`, `default_discovery_used`. `to_dict` adds derived `doc_count` and `by_confidence` (`_confidence_breakdown`, `models.py:112-116`).

**Tunable thresholds** (`constants.py:8-10`): `_HIGH_BROKEN_RATIO=0.10`, `_LOW_BROKEN_RATIO=0.40`, `_MIN_BROKEN_FOR_LOW=4`.

**Age buckets** (`_classify_age`, `catalog.py:56-62`):
- `fresh`: `≤ -1s`, doc newer than code.
- `recent`: ≤30d.
- `aging`: ≤90d.
- `stale`: ≤180d.
- `old`: >180d.
- `unknown`: no code mtime.

**Whitelists** (`refs.py:26-79`): `_PROSE_WHITELIST` (English filler in backticks) and `_FRAMEWORK_WHITELIST` (Claude Code tools/hooks, `.context/` artifact filenames, dummyindex schema field names). `extra_names` (typically `harvest_json_keys` output) extends both per repo.

## Dependencies surfaced

**Feeds (this feature is the producer):**
- **`PROJECT.md`** ← `output/docs.py:generate_project_md:130` prefers the highest-confidence non-`low` README's first paragraph for the description. It appends an "Existing documentation" section (`_render_doc_section:260`). A grading change here moves the blurb.
- **`architecture/overview`** — source-docs is the doc-evidence layer. The architecture narrative cites it when describing how the index judges its own prose.
- **`features/<id>/docs.md`** — per-feature doc sections (`_render_doc_section`) surface the same catalog signals, scoped to a feature. Capped at top N (test `test_feature_docs_caps_at_top_n`).
- **The council** consumes this catalog as trusted evidence. This engine emits its doc-confidence.

**Depends on (this feature is the consumer):**
- `pipeline/io/detect.py` — office→markdown sidecars + on-demand PDF text. A converter change shifts extracted ref tokens.
- `enums.py:DocConfidence` — shared enum. The `__str__` pin (below) lives there, not here.
- `.context/map/symbols.json` / detected `file_paths` — the AST symbol set and full path-set that `find_broken_refs` matches against.

## Key decisions (promoted)

- **Deterministic, AST-grounded grading — never modelled.** Confidence is *computed*, so the catalog is reproducible and trusted as evidence. Stable sort, sorted JSON, and an ISO-seconds timestamp give byte-identical re-runs (sort at `catalog.py:192`, timestamp at `:196-198`). This is the load-bearing decision. Everything else serves it.
- **Conservative ref extraction.** `looks_like_code_ref` would rather miss a real ref than flag English prose as broken (`refs.py:82-121`). Fenced blocks are stripped entirely before tokenizing (`refs.py:281-282`). False *broken* flags erode trust faster than missed refs.
- **Tiny-doc floor (`_MIN_BROKEN_FOR_LOW=4`).** It stops a one-line ADR that names a feature by example from dropping to `low` (`_classify_confidence:65-89`).
- **`unknown` age maps to `high` at low broken-ratio.** A first build with no comparable code mtime must not mass-demote every doc (`catalog.py:85-88,155-157`).
- **Widened path-set.** `file_paths` is the *full* detected set, not code-only: code, docs, papers, and config. Prose cites READMEs, schema JSON, and generated artifacts. A code-only set drives false `broken_refs` (`build_doc_catalog:108-118`).
- **`DocConfidence.__str__ = str.__str__`.** Pins the enum to its value across the Python 3.11 `Enum.__format__` change. `INDEX.md` never leaks `DocConfidence.LOW` (`context/enums.py:26-31`). Verified by `test_doc_confidence_str_is_value_not_enum_repr`.
- **Atomic, byte-faithful writes.** Tmp file plus `replace` per the data-access convention (`writers.py:115-120`). A concurrent reader never sees a half-written `INDEX`.
- **External docs** keep absolute `path`, `is_external=True`, and `abs_path` as an audit trail. In-repo docs stay repo-relative POSIX, per the no-absolute-leakage convention (`catalog.py:92-97`, `165-185`).

## Open questions

- `find_broken_refs` rebuilds `file_basenames` per call (`refs.py:320`). On a large `doc_paths` corpus, the path-set is re-derived per doc. Acceptable at current scale. A hoisted basename set would cut redundant work.
- Each doc's bytes are read twice: `read_bytes()` for `sha256`, plus `extract_doc_text()` re-reading text (`catalog.py:138-145`). Fine for prose. Not fine for very large converted PDFs.
- `harvest_json_keys` caps at 5000 keys (`keys.py:15`). On huge JSON corpora, legitimate schema names past the cap can be reported broken. No signal surfaces when the cap is hit.
- Age uses a single `newest_code_mtime` scalar. A doc is judged against the one latest-touched file, not the subsystem it documents. Coarse but cheap.
