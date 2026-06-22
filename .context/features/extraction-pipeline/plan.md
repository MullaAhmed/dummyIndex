# Extraction & graph backbone — plan

confidence: INFERRED

## Bounded context

This feature **owns the deterministic backbone**: raw source files in, a
community-tagged symbol graph out, no LLM anywhere in the path. Its boundary is
the three-stage pipeline `extract → cluster → to_json`, each stage a pure
function over the previous stage's output:

- **pipeline** (`dummyindex/pipeline/extract/`, `pipeline/io/`) — owns tree-sitter
  parsing, the content-addressable cache, and filesystem git detection. Imports
  stdlib + tree-sitter only; depends on nothing else in the repo.
- **analysis** (`dummyindex/analysis/cluster.py`) — owns community detection.
  Consumes a NetworkX graph built from pipeline nodes/edges; imports `pipeline` only.
- **export** (`dummyindex/export/graph.py`, `export/common.py`) — owns the
  graph→JSON transport. Top-level (not under `context/`) because it is
  transport-shaped and consumed by two callers (`folder-organization.md:69-73`).

Everything *downstream* of this boundary — the `.context/` build, feature
clustering, flows, the viewer — consumes the `map/` + `tree.json` + `symbol-graph.json`
artefacts this feature emits and never re-parses source. This is the load-bearing
dependency: **if the node/edge schema or id derivation changes here, every
consumer breaks.**

## Where it lives

- `dummyindex/pipeline/extract/` — tree-sitter extraction. `__init__.py`
  (orchestrator: `extract` / `collect_files`), `config.py` (`LanguageConfig`),
  `generic.py` (parametric driver), `common.py` (id/name/body helpers),
  `imports.py` (per-language `_import_<lang>`), `helpers.py` (extra-walk + C/C++
  name resolvers), `language_configs.py` (config instances), `languages/`
  (per-language `extract_<lang>` + `wrappers.py`), `python_rationale.py`
  (docstring/rationale post-pass), `resolve.py` (cross-file resolvers).
- `dummyindex/pipeline/io/` — `cache.py` (content-addressable per-file cache),
  `git.py` (filesystem repo/worktree/submodule detection).
- `dummyindex/analysis/cluster.py` — Leiden/Louvain community detection.
- `dummyindex/export/` — `graph.py` (`to_json`), `common.py` (confidence-score
  defaults, community inversion, diacritic stripping).
- Tests: `tests/pipeline/io/test_git.py`, `tests/pipeline/extract/test_python_rationale.py`.

## The pattern: a three-stage deterministic backbone

The architecture is a **staged pipeline of pure transforms** — each stage a named
seam at `path:range`, every stage re-runnable to byte-identical output:

1. **Extraction (tree-sitter)** — `extract` (`pipeline/extract/__init__.py:118-249`)
   drives a two-pass walk: per-file structural extraction through the **single
   generic driver** `_extract_generic` (`generic.py:23-650`, ~12 languages via
   `languages/wrappers.py`), then cross-file resolution
   (`_resolve_cross_file_imports`, `resolve.py:17-146`) and a global raw-call pass.
   Grammar quirks are *data*, not code branches — they live in `LanguageConfig`
   (`config.py:12-47`). Custom-walk languages (Go, Rust, Julia, …) bypass the
   driver entirely.
2. **Clustering (Leiden)** — `cluster` (`analysis/cluster.py:59-104`) loads the
   nodes/edges into a NetworkX graph and assigns stable, size-descending community
   ids via `_partition` (`cluster.py:21-52`), splitting any community over 25% of
   nodes through `_split_community` (`cluster.py:107-122`).
3. **Export (graph→JSON)** — `to_json` (`export/graph.py:23-38`) serialises the
   community-tagged graph to `symbol-graph.json` in NetworkX node-link form,
   backfilling numeric `confidence_score` from the `ConfidenceLevel` enum.

The two cross-cutting seams that make re-runs cheap and stable:
- **Content-addressable cache** — `file_hash` (`cache.py:20-40`) keys on
  `sha256(content)` with the path *excluded*; `load_cached`/`save_cached`
  (`cache.py:43-108`) store at `.context/cache/{hash}.json` via atomic
  temp-then-`os.replace` with a Windows copy fallback.
- **Pure-filesystem git detection** — `is_git_repo` (`git.py:24-59`),
  submodule/worktree aware, never raises on malformed input.

## Data model (summary; full shapes in spec.md)

- **Node**: `{id, label, file_type, source_file, source_location}`
  (`generic.py:59-65`); export adds `community` + `norm_label` (`graph.py:30-31`).
  `id` is `_make_id`-derived — lowercased, non-alnum collapsed to `_`
  (`common.py:12-16`); file < class < method ids nest by joining parts.
- **Edge**: `{source, target, relation, confidence, source_file, source_location,
  weight}` (`generic.py:69-77`), optional `confidence_score`. `confidence` is the
  `ConfidenceLevel` enum — `EXTRACTED` for same-file structure, `INFERRED`
  (w=0.8) for cross-file and global raw-call resolution (`__init__.py:237-242`,
  `resolve.py:136-139`).
- **Edge cleaning**: an edge survives only if both endpoints are in `seen_ids`,
  except `imports`/`imports_from` which may dangle (`generic.py:642-648`).

## Decisions

- **Decided: tree-sitter v2 API is mandatory** because the generic driver relies
  on v2 node-field accessors — `_check_tree_sitter_version` hard-fails below
  `LANGUAGE_VERSION` 14 / tree-sitter 0.23 rather than degrading silently
  (`__init__.py:61-75`).
- **Decided: one generic driver + per-language config** (not one walk per
  language) because grammar differences are narrow enough to express as
  `LanguageConfig` frozensets/callables (`config.py`), keeping `_extract_generic`
  the single source of structural truth. It is the documented `extremis` exception
  to the >600-line split rule and is deliberately *not* split (`generic.py:10-13`).
- **Decided: Leiden first, Louvain fallback** because graspologic Leiden gives
  better community quality, but is an optional dep — networkx Louvain (seeded `42`,
  `max_level` probed for version compatibility) covers its absence
  (`cluster.py:30-52`). graspologic stdout/stderr is suppressed to protect
  PowerShell 5.1 scroll buffers (`cluster.py:10-18,32-41`).
- **Decided: content-addressable, path-excluded cache key** because the same
  content must hit the same cache entry across cwd changes, `mv`d repos, and
  absolute-vs-relative `source_file` — path-keying would defeat all three
  (`cache.py:20-34`).
- **Decided: resilience over strictness** because one bad file must not abort a
  whole-repo index: per-file parse errors return an `error` payload and are
  skipped *without caching* (`__init__.py:168`); cross-file resolution failures
  are logged and swallowed (`__init__.py:205-214`); git detection never raises
  (`git.py:11-14`).

## Open questions

- `extract`'s return advertises `input_tokens`/`output_tokens` (always `0`) —
  vestigial LLM-era fields kept for caller compatibility; candidates for removal.
- `collect_files`'s `_EXTENSIONS` set (`__init__.py:255-260`) is narrower than
  `_DISPATCH` (`__init__.py:78-113`) — `.ex`, `.jl`, `.dart`, `.v` dispatch but
  are not collected by directory walk; only single explicit-file targets reach
  those extractors.
- `_split_community` runs its second pass on the *whole-graph* subgraph slice, not
  the connected component — interaction with isolates assigned their own
  communities is untested at scale.
