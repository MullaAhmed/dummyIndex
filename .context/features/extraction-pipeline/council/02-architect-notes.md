# Architect notes — extraction-pipeline (stage 2)

## What I changed

- Added a **Bounded context** section at the top: scoped the feature to the three
  pure-function stages (`extract → cluster → to_json`), named the per-stage owner
  directory, its allowed imports, and the downstream-consumer dependency. This was
  the missing frame — the old plan opened with file layout, not boundary.
- Renamed the old "Architecture in three sentences" prose into a named pattern
  section, **"The pattern: a three-stage deterministic backbone,"** each stage now
  a numbered seam with its function at `path:range`.
- Demoted the full Node/Edge/Cache/Edge-cleaning data model to a **summary** that
  defers to `spec.md` for full shapes — cut duplicated relation lists and the
  `DUMMYINDEX_CACHE_DIR`/markdown-frontmatter detail that the spec already carries.
- Rewrote "Key decisions" as **"decided X because Y"** throughout.
- Left `spec.md` untouched. Wrote no source.

## Patterns named

- **Staged pipeline of pure transforms** — `extract` (`pipeline/extract/__init__.py:118-249`)
  → `cluster` (`analysis/cluster.py:59-104`) → `to_json` (`export/graph.py:23-38`).
- **Tree-sitter extraction via one generic driver + per-language config** —
  `_extract_generic` (`generic.py:23-650`) parameterised by `LanguageConfig`
  (`config.py:12-47`); cross-file resolution `_resolve_cross_file_imports`
  (`resolve.py:17-146`).
- **Leiden clustering with Louvain fallback** — `_partition` (`cluster.py:21-52`),
  community split `_split_community` (`cluster.py:107-122`).
- **Content-addressable cache** — `file_hash` (`cache.py:20-40`),
  `load_cached`/`save_cached` (`cache.py:43-108`).
- **Pure-filesystem git detection** — `is_git_repo` (`git.py:24-59`).

All symbol names verified against `.context/map/symbols.json`; all citation files
match the symbol records (line ranges carried from the dev draft, which verified
them against source). Disambiguated `_partition` — two symbols share the name
(`analysis/cluster.py` and `context/domains/memory/roll.py`); the plan cites the
`cluster.py:21-52` one.

## Dependencies surfaced

- **Internal import direction** (matches `folder-organization.md:25-28`):
  `pipeline →` stdlib/tree-sitter only; `analysis → pipeline`; `export` top-level
  transport. Made explicit per-stage in the Bounded context section.
- **Downstream fan-out (the load-bearing one):** every other feature consumes the
  emitted `map/` + `tree.json` + `symbol-graph.json` and never re-parses source —
  so the node/edge schema and `_make_id` derivation are a hard contract; a change
  here breaks all consumers. Stated explicitly in the plan.
- **External optional dep:** graspologic (Leiden) optional → Louvain fallback;
  tree-sitter v2 / 0.23+ mandatory (hard-fail).

## Decisions promoted

- tree-sitter v2 mandatory — *because* the generic driver uses v2 field accessors;
  hard-fail over silent degradation (`__init__.py:61-75`).
- One generic driver + per-language config — *because* grammar quirks are
  data-expressible; documented `extremis` exception to the split rule (`generic.py:10-13`).
- Leiden first, Louvain fallback — *because* graspologic is an optional dep but
  gives better quality (`cluster.py:30-52`).
- Path-excluded content-addressable cache key — *because* same content must hit the
  same entry across cwd/`mv`/abs-vs-rel paths (`cache.py:20-34`).
- Resilience over strictness — *because* one bad file must not abort a whole-repo
  index (`__init__.py:168,205-214`, `git.py:11-14`).
