# Feature 1 — Structure Graph — Technical Design

**Document type:** Technical Design / RFC
**Companion to:** `plan/feature_1/logical/PRD.md`
**Status:** Draft v1
**Intended reader:** Engineers implementing, reviewing, or extending the structure graph.

---

## 0. How to read this document

This document answers the *how*. It makes specific technical choices, cites the files those choices touch (`module.py:NNN` style), and calls out the trade-offs explicitly. No code blocks. Each section is self-contained; implementers can pick the section they own and work from it.

The document is organized as:

1. Background on the current architecture (references only).
2. High-level architecture of the feature.
3. Schema changes to nodes and edges.
4. Extraction changes per language.
5. Build / pipeline integration.
6. Rendering (viewer) design.
7. Collapse / expand / lift algorithm.
8. CLI, configuration, and cache.
9. Testing strategy.
10. Security, performance, and observability.
11. Migration and backward compatibility.
12. Phased delivery plan.
13. Open technical questions.

---

## 1. Current architecture — what we are building on

The existing pipeline is documented in `ARCHITECTURE.md` and implemented across:

- `graphify/src/pipeline/detect.py` — file discovery and classification.
- `graphify/src/pipeline/extract.py` — AST extraction; dispatches per language; emits `{nodes, edges}` dicts.
- `graphify/src/pipeline/build.py` — `build()` and `build_from_json()` assemble into a NetworkX graph; hyperedges are preserved on `G.graph["hyperedges"]`.
- `graphify/src/pipeline/validate.py` — schema validation.
- `graphify/src/pipeline/cache.py` — per-file SHA256 cache of extraction results.
- `graphify/src/analysis/{cluster,analyze,report,wiki}.py` — post-build analysis and reports.
- `graphify/src/pipeline/export.py` — all output formats (HTML, JSON, SVG, GraphML, Cypher, Obsidian, Canvas).
- `graphify/src/__main__.py` — CLI dispatch.

Node attributes observed today: `id`, `label`, `file_type` (from `FileType` enum: `code`/`document`/`paper`/`image`/`video`), `source_file`, `source_location`.
Edge attributes: `source`, `target`, `relation`, `confidence`, `source_file`, `source_location`, `weight`, `_src`, `_tgt` (direction-preserving).
Relations emitted by the AST extractor: `imports`, `imports_from`, `contains`, `method`, `inherits`, `calls`, `bound_to`, `uses_static_prop`, `references_constant`, `listened_by`, plus `uses` and `semantically_similar_to` from the semantic pass.

The existing `contains` edges already express file→class and file→function containment for module-level declarations; `method` expresses class→method. That is the backbone we extend.

---

## 2. High-level architecture

### 2.1 Guiding principles

- **Additive.** Existing outputs (`graph.json`, `graph.html`, `GRAPH_REPORT.md`, Obsidian vault) are not modified in content by default. The structure graph is a new artifact pair: `structure_graph.json` + `structure_graph.html`.
- **Single extraction pass.** We do not run the pipeline twice. Extraction emits the superset of information both graphs need; rendering picks what it cares about.
- **Filesystem-sourced hierarchy.** Folder and file nodes come from walking paths — not from any LLM or heuristic. The tree is exact.
- **Rendering-only collapse.** Collapsing is entirely a viewer concern. The on-disk `structure_graph.json` is the full, expanded tree. No information is lost by persisting the collapsed state.
- **No new edge semantics.** Hierarchy gets its own containment relation family (see §3.3); lateral edges reuse existing relation names verbatim.

### 2.2 Pipeline placement

The new logic fits into the existing pipeline as two additions and one new export:

```
detect → extract → [+ structure synthesis] → build → cluster → analyze → report
                                                                          ├── export (existing)
                                                                          └── export_structure (new)
```

The "structure synthesis" step runs **after** extraction returns. It takes the collected file paths, the extracted `nodes`/`edges`, and the input root, and it appends folder nodes and `folder_contains` edges. Everything else in the pipeline stays put. The new export module (or new functions inside `export.py`) serializes the structure graph and renders its HTML.

Rationale for a synthesis step rather than changing every language extractor: folder nodes are language-agnostic and path-derived. Putting them in one place keeps language-specific code in `extract.py` focused on what each language actually parses.

---

## 3. Schema changes

### 3.1 Add a `node_kind` attribute

All existing nodes already carry `file_type`, but that field mixes two concerns:

- *Corpus-level type*: code / document / paper / image / video — what kind of file it came from.
- *Structure-level kind*: folder / file / class / function / method / global.

We keep `file_type` unchanged (corpus classification) and add a new optional attribute `node_kind` whose values are one of:

| Value | Meaning | Emitter |
|-------|---------|---------|
| `folder` | A directory between the input root and an extracted file | Structure synthesis |
| `file` | The file node itself | AST extractor |
| `class` | A class-like declaration | AST extractor |
| `function` | A top-level function (parented by a file) | AST extractor |
| `method` | A class member function | AST extractor |
| `global` | A module-level named binding that is not a class/function | AST extractor (new) |
| `concept` | Catch-all for nodes from the semantic pass that are not one of the above | Semantic pass |

Rules:

- `node_kind` is **optional** for backward compatibility with older `graph.json` files.
- When absent, `node_kind` is inferred at load time by the heuristic already in `analyze.py:_is_file_node`. Existing analysis code continues to work with its current inference logic; the viewer uses the explicit field.
- Node IDs remain the same stable-string form produced by `_make_id` in `extract.py`.

### 3.2 Folder node shape

Folder nodes are synthetic and carry:

- `id`: derived from the project-relative path with a `folder:` prefix (e.g. `folder:src_auth` after the `_make_id` normalization). The prefix prevents collision with a file named `src_auth.py`.
- `label`: the folder's display name (the leaf directory name). The *root* folder's label is the input path's basename, or `"."` if the input is the current directory.
- `node_kind`: `"folder"`.
- `file_type`: not set (folders aren't files).
- `source_file`: the project-relative folder path (including trailing slash).
- `source_location`: not set.
- `child_count`: number of direct descendants (files and sub-folders). Useful for the viewer's collapsed badge.

### 3.3 New containment relation

Today, `contains` is used for file→class and file→function; `method` for class→method. To express the *full* hierarchy uniformly, we add a single new relation:

- `folder_contains` — used for folder→folder and folder→file only.

We deliberately **do not** rename `contains` / `method` to avoid churn in consumers, existing reports, and the LLM-facing `skill.md` examples. Aggregating the hierarchy becomes: the structure graph's parent-of edges are exactly the union of `folder_contains ∪ contains ∪ method`. This is a stable, documented rule.

For global variables we emit `contains` (file→global). This parallels the existing file→function pattern and requires no new relation.

### 3.4 Edge attribute additions

All hierarchy-family edges (`folder_contains`, `contains`, `method`) gain a stable attribute:

- `edge_role`: `"hierarchy"` for any hierarchy edge; absent for cross-edges.

This lets the viewer (and future consumers) partition edges without hardcoding relation names. It's a small denormalization that pays off in rendering performance and forward compatibility (new hierarchy relations in future only need to set `edge_role="hierarchy"`).

### 3.5 Schema version bump

`graphify/src/pipeline/validate.py` currently does not carry a schema version in the payload. We add a top-level `schema_version` key to the merged extraction dict (`.graphify_extract.json`) and to `graph.json`. Initial value: `"1.0"` for today's schema, `"1.1"` after this feature ships. The cache loader (see §8.3) consults it.

---

## 4. Extraction changes

### 4.1 Language coverage baseline

graphify already supports 25 languages (see `ARCHITECTURE.md` and `extract.py`'s dispatch map at line 3107). The structure-graph work touches extraction in two places:

1. Tag every emitted node with `node_kind`.
2. Add global-variable extraction per language.

Tagging is mechanical and localized to the three `add_node` paths:

- In the generic `walk()` inside `extract_language()` (around line 687) — tag file nodes as `file`, classes as `class`, functions/methods as `function`/`method`.
- In the inheritance base-class injection paths (around lines 750, 772, 795) — tag as `class` (these are synthetic external-class references).
- In the semantic-pass merge path inside `skill.md` — tag as `concept` by default; if the LLM output already carries a kind, respect it.

Global-variable extraction is genuinely new and is the larger change. We spec it per language family below.

### 4.2 Global variable extraction — language rules

The goal is: capture the *names* that sit at module scope, that are not classes or functions, and that a developer would plausibly reason about ("API_KEY", "DEFAULT_TIMEOUT", "logger"). We are not capturing every assignment — only top-level bindings.

Common filters that apply to all languages:

- Only module-scope (not inside class bodies, not inside functions).
- Skip bindings whose RHS is itself a lambda / arrow function / anonymous function definition — those are functions in disguise and already captured by the function path.
- Optionally skip single-underscore-prefixed names (language-specific "private" convention). Made configurable via an extractor flag `include_private_globals`, default off for Python-style `_name`, left on elsewhere.

Per-language rules:

- **Python (`extract_python`)** — capture top-level `assignment` nodes (tree-sitter node type). Walk the left-hand side: if it is an `identifier`, emit one global; if it is a tuple/pattern, emit one global per identifier in the pattern. Exclude `__all__`, `__version__`, etc. only if their RHS is trivial and the user asked for strict mode.
- **JavaScript / TypeScript (`extract_js`)** — capture top-level `variable_declaration` and `lexical_declaration` (node types for `var`, `let`, `const`). For `export const X = …`, also attach an `exports` edge? No — v1 keeps it simple: just emit the global. `export` is a cross-cutting concern, covered by later features.
- **Go** — capture top-level `var_declaration` and `const_declaration`. Each spec can declare multiple names; emit one global per name.
- **Rust** — capture top-level `static_item` and `const_item`.
- **Java, C#, Kotlin, Scala** — these languages require top-level declarations to live inside a class/object/namespace. For class-level `static final` / `companion object` entries, emit them as *method-like* children of their enclosing class but with `node_kind="global"`. This keeps the tree consistent.
- **C, C++** — capture top-level `declaration` whose type is not a function and whose declarator is an identifier. Skip `extern` declarations (they are references, not definitions).
- **Ruby** — capture top-level assignments, plus `$globals` and constants (`UPPERCASE`).
- **Swift** — top-level `property_declaration` at file scope.
- **PHP** — top-level `const_declaration` and `$` assignments at file scope.
- **Other languages (Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart)** — implement pragmatically; if tree-sitter exposes a top-level assignment / declaration node, use it. If not, skip global extraction for that language in v1 and document the gap.

For each global we emit a node with `node_kind="global"`, `label` = the identifier, a `source_location` pointing at the declaration line, and a `contains` edge from the file node to the global.

Implementation note: **all of this is localized to the walk hooks per language in `extract.py`.** No cross-file logic is needed.

### 4.3 Structure synthesis

A new function — living in a new module `graphify/src/pipeline/structure.py` — consumes:

- the input root path,
- the list of file paths that were actually extracted (`collect_files()` output),
- the merged extraction dict.

It returns an extraction dict with additional folder nodes and `folder_contains` edges appended. Responsibilities:

1. For each extracted file, compute its project-relative path, split into parts, and generate one folder node per ancestor directory between the root and the file (inclusive of root, exclusive of the file).
2. Dedup by folder ID (two files share ancestors).
3. Emit `folder_contains` edges: each folder → its immediate child folder (if any) and each folder → its direct file children.
4. Skip folders with **no** extractable files in their subtree — enforces acceptance criterion AC-7.
5. Assign each folder its `child_count`.

The synthesis must be deterministic: sort nodes by ID, sort edges lexicographically by `(source, target)`. This protects SC-6 (determinism).

### 4.4 Cross-edge policy

No changes. The structure graph uses the same edge set. The synthesis step does not touch edges other than adding `folder_contains`. The viewer distinguishes hierarchy from cross-edges using `edge_role` (see §3.4).

---

## 5. Build / pipeline integration

### 5.1 `build_from_json` changes

`build.py:build_from_json` is already schema-tolerant and idempotent. It does not need structural changes. We do two small edits:

1. On node addition, if `node_kind` is present it flows through as an attribute (already does via `**{k: v for k, v in node.items() if k != "id"}`).
2. On edge addition, if `edge_role` is present it flows through (same reason).

No API break. No signature change.

### 5.2 Who calls the synthesis

The skill (`graphify/markdown/skill.md` Step 3–4) and the CLI wrappers (`graphify/src/__main__.py`) both orchestrate extraction. The synthesis call fits neatly after the merge of AST + semantic extractions and before `build_from_json()`.

To keep the skill's Python snippets small, we expose the synthesis as a single call: `synthesize_structure(extraction, paths, root)` returning the extended extraction dict. The skill's Step 4 snippet grows by one line.

### 5.3 Graph-object lifecycle

A *single* NetworkX graph `G` continues to carry the entire model. We do not produce two NetworkX graphs. The structure graph is a view computed from `G` at export time:

- `G.nodes[n]["node_kind"]` and edge `edge_role` are the partition keys.
- `export_structure()` projects `G` to the node set and edge set it cares about.

Why one graph: Leiden clustering, god-node detection, surprising-connection analysis, and the existing semantic report all benefit from seeing the new folder nodes and globals too (or, for folder nodes, can simply ignore them — see §5.4). Maintaining two disconnected graphs would require duplicating cache, ID, and serialization logic.

### 5.4 Do folder nodes participate in clustering / god-node analysis?

Decision: **no**, by default.

- Clustering (Leiden) runs on the existing induced subgraph that excludes folder nodes. We already have `_is_file_node` filtering in `analyze.py`; we extend it to also skip `node_kind == "folder"`.
- God nodes and surprising-connection detection exclude folders (they would otherwise dominate by degree).
- `GRAPH_REPORT.md` is unchanged.

Folder nodes live in the graph for the structure view only. If a later feature wants to include them in clustering it can flip the filter.

### 5.5 Hyperedge preservation

Existing hyperedges on `G.graph["hyperedges"]` are copied to `structure_graph.json` verbatim. The viewer does not render hyperedges in v1 (they are a feature-2/feature-3 concern). They remain in the JSON for downstream consumers.

---

## 6. Rendering — the structure viewer

### 6.1 Renderer choice

Reuse **vis-network**. Rationale:

- Already loaded by `graph.html`; no new dependency; no new CDN script.
- Supports hierarchical layout natively via `layout.hierarchical` options.
- The existing viewer's sidebar, search, and info panel are re-usable with minor modification.

Alternatives considered:

- **d3-hierarchy + d3-tree.** Produces cleaner tree layouts but requires writing a new sidebar and ignoring vis's dataset model. Rejected for v1; revisit in v2 if layout quality is inadequate.
- **Cytoscape.js.** Larger bundle; overkill for our needs. Rejected.
- **GoJS / yFiles.** Commercial licensing. Rejected.

### 6.2 HTML scaffold

`export_structure_html()` emits a single-file HTML similar to `to_html()` in `export.py` (line 342). It embeds:

- The vis-network bundle reference (same CDN URL as today).
- A style block extended with hierarchy-specific chrome: kind legend, collapse indicators, aggregated-edge badge styling.
- The nodes/edges datasets, JSON-escaped with the same `_js_safe` helper (line 413).
- A layout configuration block that switches vis to hierarchical mode with direction `UD` (up-down), level separation around 140, node separation around 160.

The sidebar reuses the existing search, info panel, and legend scaffolding. The legend gains a "node kinds" section (folder / file / class / function / method / global) alongside the existing community legend.

### 6.3 Node styling (by kind)

To keep the kind visually legible at a glance:

- **folder** — rounded rectangle, muted slate fill, folder-ish iconography via unicode badge.
- **file** — rectangle, accent fill by language family.
- **class** — diamond, tinted by community (same color scheme as the existing graph).
- **function** — circle, tinted by community.
- **method** — smaller circle, tinted by community; indented visually under its class.
- **global** — small square, neutral color; bold border to distinguish from method.

Size scales with degree, same formula as today (`10 + 30 * deg/max_deg`, see `export.py:371`), capped lower for folders to avoid a giant root.

### 6.4 Edge styling

- **Hierarchy edges** — solid, thin, neutral gray; drawn only between parent and its *visible* child. They disappear when the child is collapsed (the collapse visual replaces them).
- **Cross-edges** — colored by relation family (calls = blue, imports = green, inherits = purple, references = orange, semantic = dashed pink, etc.). Confidence maps to dash/solidity, as today (`export.py:398–400`).
- **Aggregated edges** — thicker stroke; a small numeric badge shows the aggregation count; hover reveals the list of component relations.

### 6.5 Default layout parameters

- Direction: `UD` (top-down).
- Level separation: 140 px.
- Node separation: 160 px.
- Tree spacing: 200 px.
- Physics: off (hierarchical layout is inherently static). The existing graph keeps physics on.
- Label visibility: always on for the current default view (file-level); smaller and lazy for deeper levels.

### 6.6 Data model handed to the viewer

`structure_graph.json` contains:

- `nodes`: list of `{id, label, node_kind, parent, source_file, source_location, community, degree, file_type}`. `parent` is the ID of the structural parent (or `null` for the root).
- `edges`: list of `{source, target, relation, confidence, edge_role, weight}`.
- `hyperedges`: passthrough, unused by the viewer in v1.
- `root_id`: the ID of the root folder, so the viewer can start its traversal without searching.
- `schema_version`: `"1.1"`.

`parent` is denormalized from the hierarchy edges at export time. The viewer uses it for constant-time ancestor walks when expanding/collapsing.

---

## 7. Collapse / expand / lift algorithm

This is the single most delicate part of the feature. Specified precisely.

### 7.1 State model

The viewer maintains two sets:

- **Expanded set `E`** — node IDs whose descendants are currently visible. By default: every folder from root down to file level, and no files.
- **Cross-edge set `X`** — the full, immutable cross-edge list loaded from JSON.

Every render pass computes derived state: the *visible node set `V`*, the *visible hierarchy edge set `H`*, and the *lifted / aggregated cross-edge set `C`*. These are recomputed on every collapse/expand action; computation is O(|V| + |X|) and runs in well under 16 ms for 5k-node graphs (the platform target).

### 7.2 Visibility rule

A node `n` is in `V` iff every ancestor of `n` (up to, but not including, `n` itself) is in `E`.

The root is always in `V`. A folder's children are in `V` iff the folder is in `E`. A file's children (classes, methods, functions, globals) are in `V` iff the file is in `E`. And so on recursively.

### 7.3 Lifting rule

For each cross-edge `e = (u, v)`:

1. Let `u'` be the deepest ancestor of `u` that is in `V` (if `u` itself is in `V`, `u' = u`).
2. Let `v'` be the deepest ancestor of `v` that is in `V`.
3. If `u' == v'`, the edge is **hidden** (both endpoints collapsed into the same ancestor; the edge is purely internal to a collapsed subtree).
4. Otherwise, emit a rendered edge `(u', v')` tagged with the original `relation` and `confidence`.

### 7.4 Aggregation rule

After lifting, multiple cross-edges may collapse onto the same `(u', v')` pair. Aggregate them:

- **Count** — how many component edges were aggregated.
- **Dominant relation** — the most common `relation` among components (ties broken alphabetically for determinism).
- **Dominant confidence** — `EXTRACTED` > `INFERRED` > `AMBIGUOUS` (highest wins).
- **Component list** — retained for hover details; not used for rendering.

The aggregated edge's displayed label is the dominant relation plus a `×N` suffix when `N > 1`.

### 7.5 Directed vs undirected

The existing pipeline supports both (via `--directed`). The lifting algorithm preserves direction: the rendered edge's `from`/`to` are derived from `u'`/`v'` in the same order as the original. Aggregation groups edges *with identical `(u', v')` in that order*; the reverse direction aggregates separately.

### 7.6 Auto-expand on search

When the user searches for a label and selects a match:

1. Walk the match's `parent` chain to the root.
2. Add every ancestor to `E`.
3. Re-render.

This guarantees the match is in `V` and visible.

### 7.7 Performance considerations

- The lift pass is linear in `|X|` and involves one hash lookup per endpoint (closest visible ancestor).
- The "closest visible ancestor" computation is memoized per render pass: walk from each node in `X` upward, caching results. Worst-case O(|X| · depth), typically sub-millisecond.
- Aggregation uses a `Map<string, AggregateEdge>` keyed on `"from→to:direction"`.
- Rendering uses vis's `DataSet.update()` in bulk rather than per-node mutations.

### 7.8 Persistence

Collapse state is persisted to `localStorage` under a key derived from the file path of `structure_graph.html`. On next load, if the key exists and the graph's `schema_version` and `root_id` match, restore `E`. Otherwise discard.

---

## 8. CLI, configuration, and cache

### 8.1 CLI flags

Add to the main `/graphify <path>` command:

- `--structure` (opt-in in Phase 1, default-on in Phase 2) — generate `structure_graph.{json,html}`.
- `--no-structure` — suppress generation even when default-on.
- `--structure-depth N` — override the default-view initial expansion depth (folder=0, file=1, class=2, method=3). Default N=1 (files collapsed).
- `--strict-globals` — enable private-global filtering (Python `_x`, JS `#private`, etc.).

No changes to any other existing flag.

### 8.2 Help text

Extend `graphify/src/__main__.py:main()` help output (line 917) with the new flags grouped under a "Structure graph" heading. Mirror the changes into the skill markdown variants so the LLM surfaces them in `/graphify --help` equivalents.

### 8.3 Cache behavior

The per-file AST cache lives in `graphify/src/pipeline/cache.py`. Cached entries are keyed on file path and SHA256 of content. Old cache entries written before this feature lack globals and `node_kind`.

Strategy:

- Introduce a `CACHE_VERSION` constant in `cache.py` and embed it in every cache record.
- On load, a record whose `CACHE_VERSION` is below the current value is treated as a miss. The file is re-extracted and the cache is rewritten.
- The constant is bumped in the same commit that lands this feature, forcing a one-time re-extract on first upgrade.

This avoids a destructive `rm -rf graphify-out/cache/` migration.

### 8.4 Manifest

`graphify-out/manifest.json` continues to track mtime; no change required. If a later feature wants to optimize (e.g. only re-synthesize folder nodes when the folder layout changes), the manifest can track a hash of the file tree shape. Out of scope for v1.

### 8.5 `.graphifyignore`

Honored exactly as today — the ignore matching happens in `detect.collect_files()`; any path excluded there is also absent from the structure graph (AC-8). No new rules.

---

## 9. Testing strategy

### 9.1 Unit tests

New file: `tests/test_structure.py`. Covers:

- Folder derivation given a fixture file list with nested paths (AC-1, AC-2, AC-7, AC-11).
- Global-variable extraction per language, one fixture per language, asserting exact leaf counts (AC-4, AC-5).
- Node `node_kind` tagging — every emitted node has one of the allowed values.
- Synthesis determinism — run twice, compare.
- Containment correctness — every non-root node has exactly one hierarchy parent (SC-3).
- Cross-edge preservation — `cross_edges(structure_json) == cross_edges(graph_json)` (SC-4).

### 9.2 Viewer (snapshot) tests

We do not run a headless browser in CI today. To avoid introducing Playwright, the viewer is tested indirectly:

- A pure-JS unit test file `tests/structure_viewer.spec.html` (loadable in a local browser, used during development) exercises the lift/aggregate function with small fixtures and compares to expected JSON. Not wired into CI in v1.
- The lift/aggregate logic is also implemented in Python in a small helper inside `export.py` for server-side pre-computation sanity checks. This Python implementation is tested in CI (AC-3, AC-5) and the JS implementation must produce identical output on the same fixtures. A small "parity" test runs the Python side and embeds the expected output in a JS-loadable fixture file, which a developer can eyeball.

This pragmatic split keeps the CI surface small while giving us confidence.

### 9.3 Integration tests

Reuse the pipeline harness from `tests/test_pipeline.py`:

- On the existing `tests/fixtures/` corpora, verify `structure_graph.json` is produced, non-empty, and schema-valid.
- Verify the existing outputs (`graph.json`, `GRAPH_REPORT.md`) are byte-identical with and without the new feature disabled — proving additivity.

### 9.4 Regression tests

Run the whole existing test suite (`pytest tests/ -q`). Any failure blocks merge. The schema version bump requires updating fixtures that embed `graph.json` snapshots; do so carefully with per-test diffs in review.

### 9.5 Performance benchmark

Extend `graphify/src/analysis/benchmark.py` (or its test in `tests/test_benchmark.py`) with a "structure graph time delta" measurement. Fail CI if the synthesis step consumes more than 20% of total pipeline wall-clock on the benchmark corpus (SC-8).

---

## 10. Security, performance, observability

### 10.1 Security

- All new labels pass through `runtime/security.py:sanitize_label` — same as today. Folder names and global names are user-supplied strings and are HTML-escaped / control-char-stripped before reaching the viewer.
- Folder paths are validated to live inside the input root before becoming node IDs. `validate_graph_path()` semantics apply.
- No network calls are added.
- `localStorage` keys derived from file paths are URL-encoded to prevent key injection.

### 10.2 Performance targets

- Synthesis: O(|paths| · depth) folder generation + O(|paths|) edge emission. On 500-file repos: sub-100 ms Python time.
- Export JSON: O(|nodes| + |edges|). Sub-200 ms.
- Viewer initial render: under 3 s on a 5k-node graph at default depth (files collapsed).
- Collapse/expand interaction: under 50 ms.

Targets are soft except the 20% pipeline budget (SC-8, CI-enforced).

### 10.3 Observability

- Log synthesis counts: `"structure: N folders, M files, K classes, P methods, Q functions, R globals"`.
- Log any ignored path reason at DEBUG level.
- Same error handling conventions as the rest of the pipeline: exceptions bubble up, no silent swallowing (per `~/.claude/rules/common/coding-style.md`).

---

## 11. Migration and backward compatibility

- **Graph JSON consumers.** The existing `graph.json` schema gains two optional fields (`node_kind`, `edge_role`) and one document-level field (`schema_version`). No existing fields are removed or renamed. Third-party readers that ignore unknown fields continue working.
- **Obsidian / Canvas exports.** Unchanged. They do not rely on `node_kind`.
- **Neo4j / Cypher / GraphML exports.** `export.to_cypher()` reads `file_type` only; it is untouched. GraphML serializes whatever attributes are present, so new fields appear as additional XML attributes — harmless.
- **MCP server (`runtime/serve.py`).** Unchanged. Queries operate on the underlying `graph.json`; new fields pass through transparently.
- **Existing `GRAPH_REPORT.md` content.** Unchanged. God nodes, surprising connections, questions all exclude folder/file nodes as they do today.

Downgrade path: disable via `--no-structure`. Removing the feature is a matter of deleting the new module and flag handling; graph data remains readable by either version.

---

## 12. Phased delivery plan

### Phase 0 — Scaffolding (1 change, low risk)
- Add `node_kind` tagging to the AST extractor (no new nodes yet).
- Add `edge_role` attribute to hierarchy edges.
- Introduce `schema_version` and `CACHE_VERSION`.
- Update `validate.py` to recognize the new fields.
- Tests: every existing node in fixtures now has `node_kind`.

### Phase 1 — Folders and structure synthesis
- Create `graphify/src/pipeline/structure.py` with `synthesize_structure()`.
- Wire the call into the skill and the CLI update path.
- Tests: AC-1, AC-2, AC-7, AC-11.

### Phase 2 — Globals per language
- Implement per-language global extraction (§4.2) one family at a time: Python → JS/TS → Go → Rust → Java/Kotlin/C#/Scala → C/C++ → rest.
- Tests: AC-4, AC-5 per language family.

### Phase 3 — Structure export (JSON)
- Add `export_structure_json()` to `export.py` (or a new `export_structure.py` if the file grows past the 800-line limit in our style guide).
- Wire into the skill's Step 4 snippet and the CLI's update path.
- Tests: SC-4, SC-6, AC-9, AC-10.

### Phase 4 — Structure viewer (HTML)
- Implement hierarchical renderer and collapse/expand/lift.
- Implement aggregated edge rendering.
- Implement search-driven auto-expand.
- Tests: integration — produces a valid HTML that opens without console errors; DOM-level acceptance via a dev-time `.spec.html` fixture.

### Phase 5 — Docs, skill, changelog
- Update `README.md`, `ARCHITECTURE.md`, `skill.md` variants, `CHANGELOG.md`.
- Add a `worked/` example that showcases the structure graph on a known corpus.

### Phase 6 — Default-on rollout
- Flip `--structure` to default-on; keep `--no-structure`.
- Watch user feedback; be ready to revert the default if issues appear.

Each phase ends green (tests pass, docs up to date). Features 2 and 3 depend on Phase 0–3 only; their HTML viewer can be deferred behind Phase 4.

---

## 13. Open technical questions

1. **Parent as an explicit edge or just a JSON field?** Current plan: both. Hierarchy is expressed as edges (for NetworkX consistency) and *also* denormalized on each node as `parent` (for O(1) viewer access). Duplication is acceptable because the relationship is exact and the JSON is derived.
2. **Does the synthesis step live before or after semantic merge?** Plan: after. Folder nodes have no semantic meaning and should not be sent to the LLM pass; running synthesis post-merge avoids polluting semantic prompts.
3. **What do we do when the input path is a single file?** The root "folder" is its parent directory. Acceptable as long as we don't escape above the user-provided path. Enforced by the existing `security.validate_graph_path()`.
4. **Should global variables be included in call-graph inference?** Not in v1. The existing `references_constant` relation already covers the "someone uses this global" case; a dedicated cross-edge from the using function to the global is sufficient.
5. **How do we handle Python's dataclasses / typing.NamedTuple?** Today the AST extractor sees them as classes, which is correct. Their fields are not materialized as methods or globals. That remains the behavior in v1.
6. **How do we handle generated files?** The detector already excludes files matching `.graphifyignore`. The structure graph relies on the same filter. No special-casing.
7. **Do we want a read-only JSON Schema for `structure_graph.json`?** Recommended for v1.1 — helps downstream consumers (AI assistants, doc-gen tools). A `schemas/structure_graph.schema.json` companion file is trivially addable; not blocking for v1.

---

## 14. Appendix — references to the existing code

Pointers for implementers, in the order they will likely touch files:

- `graphify/src/pipeline/extract.py:687` — generic node emission in the AST walker; add `node_kind` here.
- `graphify/src/pipeline/extract.py:864` — function type handling; emit `method` vs `function` `node_kind`.
- `graphify/src/pipeline/extract.py:722` — class handling; emit `class` `node_kind` and propagate through nested classes.
- `graphify/src/pipeline/extract.py:3071` — `extract()` entry point; insert globals pass per language.
- `graphify/src/pipeline/build.py:54` — `build_from_json()`; verify `node_kind` / `edge_role` flow through.
- `graphify/src/pipeline/validate.py` — extend to accept the new optional fields.
- `graphify/src/pipeline/cache.py` — add `CACHE_VERSION` and invalidate old entries.
- `graphify/src/pipeline/structure.py` — new file; `synthesize_structure()`.
- `graphify/src/pipeline/export.py:282` — `to_json()` pattern to mirror for `export_structure_json()`.
- `graphify/src/pipeline/export.py:342` — `to_html()` pattern to mirror for `export_structure_html()`.
- `graphify/src/analysis/analyze.py:11` — `_is_file_node`; extend to also exclude `node_kind == "folder"` from god-node/surprise analysis.
- `graphify/src/__main__.py:917` — CLI help; add the new flags.
- `graphify/markdown/skill.md` Steps 4 and 6 — insert synthesis call and new export call; mirror across platform variants.
- `tests/test_structure.py` — new file; all acceptance tests.
- `tests/test_pipeline.py` — assert additivity.
- `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md` — docs.

---

## 15. Acceptance review checklist (for the implementer)

Before opening a PR for this feature, confirm:

- [ ] Every new or modified module under 800 lines, files focused per §CLAUDE.md.
- [ ] Type annotations on every new function signature.
- [ ] No mutation of input dicts; synthesis returns a new extraction dict.
- [ ] Error handling at every boundary; no silent failures.
- [ ] New tests cover at least 80% of new code.
- [ ] `pytest tests/ -q` green.
- [ ] `bandit -r graphify/` clean on new code.
- [ ] `black`, `isort`, `ruff` clean on new and edited files.
- [ ] `CHANGELOG.md` updated.
- [ ] `README.md`, `ARCHITECTURE.md`, `skill.md` (+ variants) updated.
- [ ] Manual: open `structure_graph.html` on a 50-file fixture, collapse/expand, search, verify lifted edges appear correctly.
