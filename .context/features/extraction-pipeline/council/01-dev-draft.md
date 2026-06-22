# Extraction & graph backbone — plan

confidence: INFERRED

## Where it lives

- `dummyindex/pipeline/extract/` — tree-sitter extraction. `__init__.py` (orchestrator + `extract`/`collect_files`), `config.py` (`LanguageConfig`), `generic.py` (parametric driver), `common.py` (id/name/body helpers), `imports.py` (per-language `_import_<lang>`), `helpers.py` (extra-walk + C/C++ name resolvers), `language_configs.py` (config instances), `languages/` (per-language `extract_<lang>` + `wrappers.py`), `python_rationale.py` (docstring/rationale post-pass), `resolve.py` (cross-file resolvers).
- `dummyindex/pipeline/io/` — `cache.py` (content-addressable per-file cache), `git.py` (filesystem repo/worktree/submodule detection).
- `dummyindex/analysis/cluster.py` — Leiden/Louvain community detection.
- `dummyindex/export/` — `graph.py` (`to_json`), `common.py` (confidence-score defaults, community inversion, diacritic stripping).
- Tests: `tests/pipeline/io/test_git.py`, `tests/pipeline/extract/test_python_rationale.py`.

## Architecture in three sentences

The **pipeline** layer parses each file with tree-sitter (generic driver for ~12 languages, custom walks for the rest), emitting nodes and edges that are cached by content hash so unchanged files are skipped on re-run. The **analysis** layer loads those nodes/edges into a NetworkX graph and runs Leiden (falling back to Louvain) to assign stable, size-ordered community ids, splitting any community that exceeds 25% of the graph. The **export** layer serialises the community-tagged graph to `symbol-graph.json` in NetworkX node-link form, backfilling numeric confidence scores from the `ConfidenceLevel` enum.

## Data model

**Node**: `{id, label, file_type, source_file, source_location}` (`generic.py:59-65`); export adds `community` and `norm_label` (`graph.py:30-31`). `id` is `_make_id`-derived: lowercased, non-alnum collapsed to `_` (`common.py:12-16`); file < class < method ids nest by joining parts.

**Edge**: `{source, target, relation, confidence, source_file, source_location, weight}` (`generic.py:69-77`), optional `confidence_score`. Relations: `contains`, `method`, `inherits`/`extends`/`implements`, `imports`/`imports_from`, `calls`, `uses`, `uses_<helper>`, `bound_to`, `references_constant`, `uses_static_prop`, `listened_by`. `confidence` is the `ConfidenceLevel` enum — `EXTRACTED` for same-file structure, `INFERRED` (w=0.8/score=0.8) for cross-file resolution and global raw-call resolution (`__init__.py:237-242`, `resolve.py:136-139`).

**Cache key**: `sha256(content)` only — path excluded so re-runs from any cwd and `mv`d repos hit the same entries (`cache.py:20-40`). Value stored at `.context/cache/{hash}.json` via atomic temp-then-`os.replace` with a Windows copy fallback (`cache.py:95-105`). `DUMMYINDEX_CACHE_DIR` overrides location (`cache.py:51-56`).

**Edge cleaning**: edges survive only if both endpoints are in `seen_ids`, except `imports`/`imports_from` which may dangle (`generic.py:642-648`).

## Key decisions

- **Tree-sitter v2 API mandatory** — `_check_tree_sitter_version` hard-fails below `LANGUAGE_VERSION` 14 / tree-sitter 0.23 (`__init__.py:61-75`).
- **One generic driver + per-language config** — grammar quirks live in `LanguageConfig` frozensets/callables (`config.py`), keeping `_extract_generic` as the single ~600-line walk; it sits in `extremis` per conventions and is deliberately not split (`generic.py:10-13`).
- **Leiden first, Louvain fallback** — graspologic Leiden for quality; networkx Louvain (seeded `42`, `max_level` probed for version compatibility) when graspologic is absent (`cluster.py:30-52`). graspologic stdout/stderr is suppressed to protect PowerShell 5.1 scroll buffers (`cluster.py:10-18,32-41`).
- **Content-addressable cache** — path-independent so the cache survives cwd changes and repo moves (`cache.py:20-34`).
- **Resilient by design** — per-file parse errors return an `error` payload and are skipped without caching (`__init__.py:168`); cross-file resolution failures are logged and swallowed (`__init__.py:205-214`); git detection never raises on malformed input (`git.py:11-14`).

## Open questions

- `extract`'s return advertises `input_tokens`/`output_tokens` (always `0`) — vestigial LLM-era fields kept for caller compatibility; candidates for removal.
- `collect_files`'s `_EXTENSIONS` set (`__init__.py:255-260`) is narrower than `_DISPATCH` (`__init__.py:78-113`) — e.g. `.ex`, `.jl`, `.dart`, `.v` dispatch but are not collected by directory walk; only single explicit-file targets reach those extractors.
- `_split_community` runs a second pass on the *whole-graph* subgraph slice, not the connected component — interaction with isolates assigned their own communities is untested at scale.
