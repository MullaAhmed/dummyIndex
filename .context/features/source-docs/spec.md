# Source-doc catalog — spec

confidence: INFERRED

## Intent

Catalog the prose docs checked into a repo (README, CHANGELOG, `docs/`, ADR/RFC, `ARCHITECTURE.md`, `SECURITY.md`, `BRIEF.md`, any root `*.md`, plus `--docs` roots) and **grade each one against the current AST** so a downstream agent knows which docs to trust. Docs drift faster than code; this engine produces the `.context/source-docs/INDEX.{json,md}` catalog whose `confidence` / `broken_refs` / `age_bucket` signals warn readers before they quote a stale doc. This is the very engine that emits the doc-evidence the council consumes.

The grading is **deterministic** (no LLM): a doc's backticked code references are cross-checked against the symbol set + file paths + harvested JSON keys; a doc that cites vanished symbols is demoted (`dummyindex/context/domains/source_docs/__init__.py:1-18`).

## User-visible behavior

The catalog is two artifacts under `.context/source-docs/`, written atomically (`writers.py:14-27`):

- **`INDEX.json`** — `DocCatalog.to_dict()` (`models.py:88-99`): `schema_version`, `generated_at`, `repo_root`, `default_discovery_used`, `extra_doc_roots`, `doc_count`, `by_confidence` (`{high, medium, low}` tally), and `docs[]` — one `DocEntry` each.
- **`INDEX.md`** — human table rendered by `_render_catalog_md` (`writers.py:28-100`): an advisory banner, a `high · medium · low` count line, a `| Doc | Type | Confidence | Broken refs | Age |` table, then a "Low-confidence docs" section listing each low doc's broken refs (capped at 10, `writers.py:85-92`) and how many days it predates the newest code.

Per-doc signals (`DocEntry`, `models.py:15-52`):

- **`confidence`** — `"high" | "medium" | "low"` (`DocConfidence`, `context/enums.py:13-31`). Derived by `_classify_confidence` (`catalog.py:65-89`) from broken-ref ratio + age bucket + broken-ref count:
  - `low` when `broken_ratio ≥ 0.40` **and** `broken_count ≥ 4` (`constants.py:8-9`); or when `age_bucket ∈ {stale, old}` with any broken ref and `broken_count ≥ 4`.
  - `high` when `broken_ratio ≤ 0.10` and `age_bucket ∈ {fresh, recent}`, or `≤ 0.10` with `age_bucket == unknown` (no code mtime to compare).
  - `medium` otherwise. The `broken_count ≥ 4` floor protects tiny docs: a 1-ref doc whose one ref is broken stays `medium`, not `low` (`catalog.py:77-83`).
- **`broken_refs`** — tuple of backticked tokens that match no current symbol, file path, basename, framework name, or harvested key (`refs.py:295-326`). `broken_ratio = len(broken) / len(refs)` or `0.0` when no refs (`catalog.py:153`).
- **`age_bucket`** — `fresh | recent | aging | stale | old | unknown` from `age_delta = newest_code_mtime − doc_mtime` against thresholds at -1s / 30d / 90d / 180d / ∞ (`catalog.py:23-30`, `_classify_age` `:56-62`). `unknown` when there is no code mtime (`catalog.py:155-161`).
- Plus `path` (repo-relative POSIX, or absolute when `is_external`), `abs_path`, `doc_type`, `title`, `headings`, `sha256`, `size_bytes`, `mtime`, `referenced_count`, `is_external`, `source_root`.

Entries sort by confidence (high→low) then path, so re-runs on identical input are byte-identical (`catalog.py:189-191`).

Discovery: with no `--docs`, `discover_default_doc_paths` returns existing well-known files/dirs plus every root-level `*.md`/`*.rst`, deduplicated and sorted (`discovery.py:58-97`). Only `_DOC_EXTENSIONS` (`.md .mdx .rst .txt .pdf .html .htm .docx .xlsx`) are catalogued (`discovery.py:43-48`); office files are converted to markdown sidecars upstream and PDFs extracted on demand (`refs.py:218-242`, `detect.py:165-251`).

The catalog also feeds `PROJECT.md`: `generate_project_md` prefers the highest-confidence non-`low` README's first paragraph for the project description and appends an "Existing documentation" section (`output/docs.py:130-203`, `_render_doc_section` `:260-298`).

## Contracts

Public surface (`__init__.py:30-42`, all verified in `.context/map/symbols.json`):

- `build_doc_catalog(doc_paths: Iterable[Path], *, repo_root: Path, symbol_names: frozenset[str], file_paths: frozenset[str], newest_code_mtime: Optional[float], extra_doc_roots: Sequence[Path] = (), default_discovery_used: bool = True, extra_names: frozenset[str] = frozenset(), now: Optional[datetime] = None) -> DocCatalog` (`catalog.py:99-202`).
- `discover_default_doc_paths(repo_root: Path) -> list[Path]` (`discovery.py:35-67`).
- `harvest_json_keys(json_paths: Iterable[Path], *, limit: int = 5000) -> frozenset[str]` (`keys.py:15-51`).
- `extract_code_refs(text: str) -> tuple[str, ...]` (`refs.py:278-293`).
- `find_broken_refs(refs: Sequence[str], *, symbol_names: frozenset[str], file_paths: frozenset[str], extra_names: frozenset[str] = frozenset()) -> tuple[str, ...]` (`refs.py:295-326`).
- `looks_like_code_ref(token: str) -> bool` (`refs.py:166-205`).
- `read_catalog(context_dir: Path) -> Optional[DocCatalog]` (`readers.py:11-17`).
- `write_catalog(context_dir: Path, catalog: DocCatalog) -> tuple[Path, Path]` (`writers.py:14-27`).
- `DocCatalog` / `DocEntry` frozen dataclasses with `to_dict` / `from_dict` round-trip (`models.py:15-116`).
- `DocConfidence(str, Enum)` with `__str__ = str.__str__` so the member renders as `"low"`, never `DocConfidence.LOW`, under f-strings on Python 3.11+ (`enums.py:13-31`).
- `context/enums.py` also carries the codebase-scan alphabets, which share `DocConfidence`'s `__str__ = str.__str__` pin for the same reason: `ScanNodeKind` (`entry cron agent model tool service store external`), `ScanEdgeKind` (`calls reads writes triggers`), `ScanEvidence` (`EXTRACTED INFERRED` — per-node provenance: kept verbatim from the deterministic seed vs. added/reshaped by the authoring council stage, `enums.py:74-91`), and `ScanViolationSeverity` (`error warning` — whether a `scan-check` violation flips the exit code or is reported-only, `enums.py:93-105`). They are closed sets so the scan viewer can map a kind to a column, a colour, and a glyph without special-casing — and so an unknown kind is a validation error rather than an unstyled box.
- `output/docs.py`'s artifact catalog describes `features/graph.json` as the curated codebase scan and `features/graph.html` as its self-contained viewer (open directly; no server, no network).

## Examples

- Match precedence in `find_broken_refs` (`refs.py:246-284`): exact file-path → sub-path suffix (`api/users.py` matches `src/api/users.py`) → basename → normalized symbol (strips `()` / leading `.`) → dotted-tail (`parser.parse_body` matches when `parse_body` is known) → `_FRAMEWORK_WHITELIST` (Claude Code tools, hook events, `.context/` artifact names, dummyindex schema fields, `refs.py:33-79`) → caller `extra_names` (precedence walk in `find_broken_refs` + `_ref_matches`, `refs.py:295-367`).
- `extract_code_refs` strips fenced ```` ``` ```` blocks first, then keeps only backticked tokens passing `looks_like_code_ref` (file-path / dotted / call / snake_case / CamelCase shapes; rejects prose-whitelist words and any token with a space) (`refs.py:278-293`, `166-205`).
- `_classify_confidence(0.50, "recent", broken_count=5) → low`; `_classify_confidence(0.0, "fresh", broken_count=0) → high`; `_classify_confidence(1.0, "recent", broken_count=1) → medium` (tiny-doc floor) (`catalog.py:65-89`).

## Reconcile 2026-08-23

Catalog logic is unchanged at HEAD — no commit in the build train touched
`domains/source_docs/`; this pass only refreshed drifted line anchors (the
office/PDF text extraction living in `refs.py` grew, shifting every downstream
function by ~85 lines). The committed catalog was regenerated by the backbone
rebuild at `f8a8a33` (`INDEX.json` `generated_at` 2026-08-23T09:49:37Z,
33 docs: 12 high / 9 medium / 12 low). Placement: the foreign `benchmarks/`,
`tests/benchmarks/`, and `results/` trees stay unclaimed (see `concerns.md`).
