# Source-doc catalog — plan

confidence: INFERRED

## Bounded context

This feature owns one thing: **grading prose docs against the current AST and persisting the verdict.** It does *not* own doc-text extraction (delegated to `pipeline/io/detect.py`) nor the consumer rendering into `PROJECT.md` (delegated to `output/docs.py`). The boundary is the `DocCatalog` dataclass: everything inside `domains/source_docs/` produces it; everything outside consumes it.

**Package** `dummyindex/context/domains/source_docs/` (one module per phase, per the folder-organization convention):

- `discovery.py` — *catalog discovery*: well-known files/dirs + root `*.md`/`*.rst` (`discover_default_doc_paths:35-67`).
- `refs.py` — *readers + refs*: doc-text/title/heading extraction, ref extraction, broken-ref cross-check.
- `keys.py` — *refs* (whitelist feed): `harvest_json_keys:13-47` harvests repo JSON schema keys.
- `catalog.py` — the *confidence-grading* orchestrator: `build_doc_catalog:98-200`.
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
| **Catalog discovery** | `discover_default_doc_paths` | `discovery.py:35-67` |
| **Reader** (text) | `extract_doc_text` / `extract_title_and_headings` | `refs.py` |
| **Reader** (refs) | `extract_code_refs` (strips fences, keeps backticked code-shaped tokens) | `refs.py:191-205` |
| **Ref shape gate** | `looks_like_code_ref` (conservative — prefers a miss to a false flag) | `refs.py:82-121` |
| **Ref cross-check** | `find_broken_refs` (7-stage match precedence) | `refs.py:208-243` |
| **Whitelist feed** | `harvest_json_keys` (cap 5000) | `keys.py:13-47` |
| **Confidence grading** | `_classify_confidence` | `catalog.py:64-88` |
| **Age bucketing** | `_classify_age` | `catalog.py:55-61` |
| **Orchestrator** | `build_doc_catalog` | `catalog.py:98-200` |
| **Writer** (md table) | `_render_catalog_md` | `writers.py:26-94` |
| **Writer** (atomic) | `_atomic_write` (tmp + `replace`) | `writers.py:109-113` |

## Flow (one orchestrator, three stages)

`build_doc_catalog` (`catalog.py:98-200`) runs each discovered doc through:

1. **Read** — `read_bytes()` for `sha256` + `stat`, then `extract_doc_text` (markdown direct; PDF/docx/xlsx via `detect.py`), then `extract_title_and_headings`, then `extract_code_refs` (`catalog.py:137-151`).
2. **Cross-check** — `find_broken_refs` matches each backticked token against AST symbols → repo file paths → JSON keys → framework whitelist; `broken_ratio = len(broken)/len(refs)` or `0.0` (`catalog.py:144-152`).
3. **Grade** — fold `broken_ratio` + age bucket (`newest_code_mtime − doc_mtime`) + a broken-count floor into `high/medium/low`, emit a frozen `DocEntry` (`catalog.py:153-191`).

Entries sort by confidence then path (`catalog.py:191`); `write_catalog` serializes the `DocCatalog` to `.context/source-docs/INDEX.{json,md}` atomically. Identical inputs ⇒ byte-identical output.

## Data model

**`DocEntry`** (frozen, `models.py:9-46`): `path`, `abs_path`, `doc_type`, `title`, `headings`, `sha256`, `size_bytes`, `mtime`, `age_delta_seconds`, `age_bucket`, `referenced_count`, `broken_refs`, `broken_ratio`, `confidence`, `is_external`, `source_root`. `to_dict` rounds `broken_ratio` to 4 places (`models.py:42`); `from_dict` tolerates missing keys with defaults.

**`DocCatalog`** (frozen, `models.py:73-103`): `schema_version` (=1, `constants.py:4`), `generated_at` (ISO seconds), `repo_root`, `docs`, `extra_doc_roots`, `default_discovery_used`. `to_dict` adds derived `doc_count` + `by_confidence` (`_confidence_breakdown`, `models.py:106-110`).

**Tunable thresholds** (`constants.py:7-9`): `_HIGH_BROKEN_RATIO=0.10`, `_LOW_BROKEN_RATIO=0.40`, `_MIN_BROKEN_FOR_LOW=4`.

**Age buckets** (`_classify_age`, `catalog.py:55-61`): `fresh` (`≤ -1s`, doc newer than code), `recent` (≤30d), `aging` (≤90d), `stale` (≤180d), `old` (>180d), `unknown` (no code mtime).

**Whitelists** (`refs.py:25-79`): `_PROSE_WHITELIST` (English filler in backticks) + `_FRAMEWORK_WHITELIST` (Claude Code tools/hooks, `.context/` artifact filenames, dummyindex schema field names). `extra_names` (typically `harvest_json_keys` output) extends both per-repo.

## Dependencies surfaced

**Feeds (this feature is the producer):**
- **`PROJECT.md`** ← `output/docs.py:generate_project_md:122` prefers the highest-confidence non-`low` README's first paragraph for the project description and appends an "Existing documentation" section (`_render_doc_section:249`). A grading change here moves the project blurb.
- **`architecture/overview`** — source-docs is the doc-evidence layer the architecture narrative cites when describing how the index judges its own prose.
- **`features/<id>/docs.md`** — per-feature doc sections (`_render_doc_section`) surface the same catalog signals scoped to a feature; capped top-N (test `test_feature_docs_caps_at_top_n`).
- **The council** consumes this catalog as evidence: this is the engine that emits the doc-confidence the council trusts.

**Depends on (this feature is the consumer):**
- `pipeline/io/detect.py` — office→markdown sidecars + on-demand PDF text. A converter change shifts extracted ref tokens.
- `enums.py:DocConfidence` — shared enum; the `__str__` pin (below) lives there, not here.
- `.context/map/symbols.json` / detected `file_paths` — the AST symbol set + full path-set that `find_broken_refs` matches against.

## Key decisions (promoted)

- **Deterministic, AST-grounded grading — never modelled.** Confidence is *computed*, so the catalog is reproducible and the council can trust it as evidence. Stable sort + sorted JSON + ISO-seconds timestamp ⇒ byte-identical re-runs (`catalog.py:191-199`). This is the load-bearing decision; everything else serves it.
- **Conservative ref extraction.** `looks_like_code_ref` would rather miss a real ref than flag English prose as broken (`refs.py:82-121`); fenced blocks are stripped entirely before tokenizing (`refs.py:193-195`). False *broken* flags erode trust faster than missed refs.
- **Tiny-doc floor (`_MIN_BROKEN_FOR_LOW=4`).** Stops a one-line ADR that names a feature by example from crashing to `low` (`_classify_confidence:64-88`).
- **`unknown` age maps to `high` at low broken-ratio.** A first build with no comparable code mtime must not mass-demote every doc (`catalog.py:86-87`).
- **Widened path-set.** `file_paths` is the *full* detected set (code + docs + papers + config), not code-only, because prose cites READMEs, schema JSON, and generated artifacts; a code-only set drives false `broken_refs` (`build_doc_catalog:113-118`).
- **`DocConfidence.__str__ = str.__str__`.** Pins the enum to its value across the Python 3.11 `Enum.__format__` change so `INDEX.md` never leaks `DocConfidence.LOW` (`enums.py:24-30`). Verified by `test_doc_confidence_str_is_value_not_enum_repr`.
- **Atomic, byte-faithful writes.** tmp-file + `replace` per the data-access convention (`writers.py:109-113`) — a concurrent reader never sees a half-written `INDEX`.
- **External docs** keep absolute `path` + `is_external=True` + `abs_path` audit trail; in-repo docs stay repo-relative POSIX, per the no-absolute-leakage convention (`catalog.py:91-95`, `163-186`).

## Open questions

- `find_broken_refs` rebuilds `file_basenames` per call (`refs.py:233-235`); on a large `doc_paths` corpus the path-set is re-derived per doc. Acceptable at current scale; a hoisted basename set would cut redundant work.
- Each doc's bytes are read twice — `read_bytes()` for `sha256` plus `extract_doc_text()` re-reading text (`catalog.py:137-143`). Fine for prose; not for very large converted PDFs.
- `harvest_json_keys` caps at 5000 keys (`keys.py:13`); on huge JSON corpora legitimate schema names past the cap can be reported broken, and no signal surfaces when the cap is hit.
- Age uses a single `newest_code_mtime` scalar, so a doc is judged against the one latest-touched file, not the subsystem it documents — coarse but cheap.
