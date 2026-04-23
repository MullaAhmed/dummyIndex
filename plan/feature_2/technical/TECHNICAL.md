# Feature 2 — Flow Hypergraph — Technical Design

**Document type:** Technical Design / RFC
**Companion to:** `plan/feature_2/logical/PRD.md`
**Status:** Draft v1
**Intended reader:** Engineers implementing, reviewing, or extending the flow hypergraph.
**Depends on:** Feature 1 (Structure Graph) for clean `node_kind` tagging; not a hard dependency but strongly recommended to implement first.

---

## 0. How to read this document

This document answers the *how*. No code. Specific file:line references point at existing modules. Each section stands on its own.

Organization mirrors `feature_1/technical/TECHNICAL.md`:

1. Background on existing call-graph and hyperedge infrastructure.
2. High-level architecture.
3. Schema changes.
4. Entry-point detection per language / framework.
5. Flow derivation algorithm.
6. Flow naming (LLM pass).
7. Pipeline integration.
8. Renderer / viewer design.
9. CLI, configuration, cache.
10. Testing strategy.
11. Security, performance, observability.
12. Migration and backward compatibility.
13. Phased delivery plan.
14. Open technical questions.
15. Appendix — references.

---

## 1. What we are building on

The existing AST extractor already emits `calls` edges during the call-graph pass (see `graphify/src/pipeline/extract.py:929` onwards — "Call-graph pass"). Edges carry `relation="calls"`, `confidence ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`, `source_file`, `source_location`, and `weight`.

Hyperedges are a first-class primitive:

- `build_from_json()` (`build.py:83–85`) preserves `extraction["hyperedges"]` on `G.graph["hyperedges"]`.
- `cache.py:123–168` round-trips hyperedges through the per-file AST cache.
- `attach_hyperedges()` (`export.py:271–279`) deduplicates and merges hyperedge lists across invocations.
- `to_json()` (`export.py:282–297`) serializes them into `graph.json` under a top-level `"hyperedges"` key.
- `_hyperedge_script()` (`export.py:61–101`) renders them as shaded regions in the existing viewer.
- `report.py:101–109` already prints them in `GRAPH_REPORT.md`.
- `watch.py:22, 77` handles hyperedges in incremental updates.

The hyperedge data model today is minimal: `{id, label, nodes: [node_id, ...], confidence, confidence_score?}`. That shape is insufficient for flow semantics (no entry, no terminals, no sequence). We extend it in §3.

The semantic extractor (not shown in detail above) can emit hyperedges via the Claude subagent pass. Flow hyperedges are produced by a new deterministic module; LLM involvement is scoped strictly to naming.

---

## 2. High-level architecture

### 2.1 Principles

- **Additive.** `graph.html` / `graph.json` / `GRAPH_REPORT.md` continue to work unchanged. Hyperedges added by this feature are consumed by the existing renderer as shaded regions (no visual breakage). A dedicated `flow_graph.html` provides the rich view.
- **Deterministic first, semantic second.** Flow topology is derived by pure static analysis. LLM calls are confined to naming and are bounded (one batched call per run) and cached.
- **One graph in memory.** Flows become hyperedges on the same NetworkX graph `G` that carries everything else.
- **Source-of-truth separation.** Flow *content* (nodes, sequence, terminals) is derived from `G`. Flow *names* are stored in a companion file (`graphify-out/.graphify_flow_names.json`) so users can override them (via `flows.yaml`) without regenerating the graph.

### 2.2 Pipeline placement

```
detect → extract → [structure synthesis] → build → cluster → analyze → [+ flow synthesis] → [+ flow naming] → report → export
```

Flow synthesis runs after clustering (flows may cite community membership in their metadata) and before report generation (so `GRAPH_REPORT.md` can include a "Flows" section).

### 2.3 Module layout

Two new modules:

- `graphify/src/analysis/flows.py` — flow synthesis and confidence aggregation. Pure, no I/O, no LLM.
- `graphify/src/analysis/flow_naming.py` — LLM interaction. I/O-bearing, cacheable, fails soft.

One new export module (or new functions in `export.py` if it stays under 800 lines):

- `graphify/src/pipeline/export_flows.py` — `export_flow_json()` and `export_flow_html()`.

This keeps `extract.py` and `build.py` untouched except for the schema extensions (§3). `analysis/` is already the home of post-build processing, so flows belong there (consistent with `cluster.py`, `analyze.py`, `report.py`, `wiki.py`).

---

## 3. Schema changes

### 3.1 Hyperedge schema extension

The existing hyperedge shape `{id, label, nodes, confidence, confidence_score?}` is extended with:

- `kind`: discriminator — `"flow"` for flow hyperedges; reserved `"feature"` for Feature 3; omitted or `"generic"` for legacy hyperedges.
- `entry_nodes`: list of node IDs that serve as entry points (usually one; a merged flow can have several).
- `exit_nodes`: list of terminal node IDs (leaf, I/O, depth-limit, cycle).
- `sequence`: ordered list of edge references `[{source, target, relation, confidence, source_location}]`. Source order within functions; DFS order across functions.
- `alt_paths`: optional list of alternative sub-sequences that were detected but not taken as canonical.
- `depth`: maximum traversal depth actually reached.
- `salience`: float ≥ 0, computed by the pipeline; used for ranking and the default `--flow-limit` cap.
- `entry_kind`: one of `http_route | cli_command | scheduled_job | event_handler | test | library_export | internal`.
- `confidence`: inherited minimum of member edges, already part of the base schema.
- `description`: optional 1–2 sentence summary from the naming pass.

All new fields are **optional** to keep the schema backward compatible with the existing `hyperedges` array and with legacy `graph.json` files.

### 3.2 Node attribute additions

Each function/method node gains an optional `flow_memberships`: a list of flow IDs. This denormalizes the hyperedge→node relation for O(1) viewer lookup. Populated only in the exported JSON — not in the in-memory `G` — to keep `G` a single source of truth.

### 3.3 Edge attribute additions

`calls` edges gain an optional `flow_roles`: list of `{flow_id, step_index}` — so the semantic viewer can highlight, for a given selected flow, the edges and their ordering position. Optional; computed only at export time.

### 3.4 Schema version

Bump from `1.1` (introduced in Feature 1) to `1.2`. `validate.py` accepts all new fields as optional. The cache loader is untouched — flow synthesis runs post-build and is not cached per-file.

---

## 4. Entry-point detection

Entry-point detection is the most language- and framework-specific part of the feature. We centralize the detection logic in `flows.py` behind a small extensible registry.

### 4.1 Detection strategy

Given the graph `G` after build:

1. **Iterate function/method nodes.** Candidates are `node_kind ∈ {"function", "method"}` (Feature 1 terms) or anything whose label matches `X()` / `.Y()` / bare function name.
2. **For each candidate, apply per-language detectors** (see §4.2). Detectors inspect the node's attributes (`label`, `source_file`, `source_location`) and the node's incoming/outgoing edges (in particular the presence of `contains` edges from files whose extension matches the language).
3. **Assign an entry kind.** If none match, fall through to the generic "internal entry" heuristic: zero in-degree on `calls` edges *and* is referenced (via `imports`, `imports_from`, or `exported`) from outside its defining file.
4. **Compute salience** using the ranking table in §4.3.
5. **Retain** candidates that exceed the salience floor (default 0.1 — configurable).

### 4.2 Per-language detectors

Each detector is a pure function `(node_data, graph) -> entry_kind | None`. The registry in `flows.py` is a list of detector functions applied in priority order. New frameworks plug in by appending a detector.

Default detectors ship for:

- **Python**
  - Flask: presence of `@app.route`, `@blueprint.route` — detectable via a docstring / decorator annotation captured by the extractor.
  - Django: `urls.py` pattern refs; function/method referenced from `urlpatterns`.
  - FastAPI: `@app.{get,post,put,delete,patch}` decorators.
  - Click/argparse: `@click.command`, functions named `main` with a `__name__ == "__main__"` guard.
  - Celery: `@shared_task`, `@task`.
  - pytest: functions named `test_*` at module scope.
  - `__main__.py` files: their top-level functions are CLI entries.

- **JavaScript / TypeScript**
  - Express: `app.{get,post,…}`, `router.{get,post,…}`.
  - Fastify, Koa, NestJS: `@Controller`, `@Get`, etc.
  - Next.js: handlers in `pages/api/*`, route handlers in `app/**/route.ts`.
  - Jest / Mocha: `test()`, `it()`, `describe()` at module scope.
  - Node CLI: `bin/` folder exports; `#!/usr/bin/env node` headers.

- **Go**
  - `net/http`: `http.HandleFunc`, `mux.HandleFunc`, `gin.Default().GET(...)`, `chi.Router` methods.
  - Cobra CLI: `cmd.RunE` field assignments; functions registered via `cobra.Command{Run: ...}`.
  - `func TestXxx(t *testing.T)`: test entries.

- **Rust**
  - Actix: `#[get("/path")]` etc.
  - Axum: route functions registered via `.route()`.
  - Clap: `#[derive(Parser)]` on structs; functions called from derived `parse()` / `match args.command`.
  - `#[test]`: test entries.

- **Java / Kotlin / Scala**
  - Spring: `@RestController`, `@RequestMapping`, `@GetMapping` etc.
  - Ktor / Micronaut / Play: framework-specific route annotations.
  - JUnit: `@Test`.
  - Main methods: `public static void main(String[] args)`.

- **Ruby**
  - Rails: `config/routes.rb` references; `ApplicationController` subclasses.
  - Sinatra: `get "/path" do ... end` block handlers.
  - RSpec: `describe`/`it` blocks.

- **C# / .NET**
  - ASP.NET: `[HttpGet]`, `[Route]`, `[ApiController]`.
  - xUnit / NUnit: `[Fact]`, `[Test]`.

- **C/C++**
  - `int main(int argc, char **argv)`.

- **PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Dart, Vue, Svelte** — detectors implemented where framework prevalence justifies it; otherwise rely on `int main`-style patterns plus "internal entry" fallback.

Detectors are data-driven where possible: they read annotations extracted by the tree-sitter pass. For languages where the current extractor doesn't capture annotations (e.g. Rust attribute macros), a small extension is added to `extract.py` under the relevant language block to record annotations as node metadata (`annotations: [str]`). This is a two-line change per language.

### 4.3 Salience ranking

Salience is a deterministic scalar used to rank flows for the default `--flow-limit` cap.

```
salience = entry_weight × log2(1 + participant_count) × (1 + cross_module_bonus)
```

- `entry_weight`: HTTP route = 1.0, CLI command = 0.9, scheduled job = 0.8, event handler = 0.7, test = 0.4, library export = 0.6, internal = 0.5.
- `participant_count`: number of distinct nodes in the flow.
- `cross_module_bonus`: 0 if the flow stays in one file; 0.1 per additional file up to 0.5.

The exact formula is stable and documented; any changes are versioned in `flows.py` with a comment.

### 4.4 Ambiguity handling

A function-name call that resolves to multiple candidate targets (common with duck typing / interface dispatch) is already flagged `AMBIGUOUS` by the call-graph pass. Flow synthesis treats ambiguous edges as follows:

- Include the first candidate in the canonical sequence.
- Record the other candidates under `alt_paths` for that sequence step.
- Downgrade flow confidence to `AMBIGUOUS` if any step is ambiguous.

---

## 5. Flow derivation algorithm

### 5.1 Inputs

- The built graph `G` (after clustering).
- The entry-point set derived in §4.
- Configuration: `max_depth` (default 10), `flow_limit` (default 100), `merge_overlap_threshold` (default 0.95).

### 5.2 Pseudocode (high level)

1. For each entry point `E`:
   a. Initialize `visited = {E}`, `sequence = []`, `terminals = []`.
   b. Source-order DFS from `E` along outgoing `calls` edges:
      - If the child is already in `visited`, record cycle-break and continue with siblings.
      - If the child is an I/O terminator (see §5.3), append the edge to `sequence`, add child to `terminals`, and continue with siblings.
      - Otherwise append the edge, mark visited, recurse.
      - At `max_depth`, append edge, add child to `terminals` with a `"depth_limit"` reason, do not recurse.
   c. If `sequence` is empty, add `E` itself as a trivial terminal.
   d. Build a flow hyperedge: `{id, nodes: list(visited), entry_nodes: [E], exit_nodes: terminals, sequence, depth: observed, confidence: min(confidences), alt_paths, entry_kind, salience}`.
2. Collect all flows into a list.
3. Apply the merge step (§5.4).
4. Rank by salience; retain the top `flow_limit`.
5. Assign stable IDs (§5.5) and write to `G.graph["hyperedges"]`.

### 5.3 I/O terminator detection

I/O detection uses a per-language name pattern table:

- Python: `requests.*`, `urllib.*`, `httpx.*`, `asyncpg.*`, `psycopg.*`, `sqlalchemy.*.execute`, `logging.*`, `open(...)`, `subprocess.*`, `boto3.*`, `redis.*`.
- JS/TS: `fetch`, `axios.*`, `pg.Client.query`, `mongoose.Model.*`, `console.*`, `fs.*`, `child_process.*`.
- Go: `http.Client.*`, `db.Exec`, `db.Query`, `log.*`, `os.Open`, `exec.Command`.
- Rust: `reqwest::*`, `sqlx::query`, `log::*`, `std::fs::*`, `std::process::*`.
- Java: `RestTemplate`, `WebClient`, JDBC `Statement.execute*`, SLF4J `Logger.*`.
- (Others similar; table lives in `flows.py`.)

These are heuristics; ambiguity downgrades confidence rather than blocks flow emission.

### 5.4 Flow merge rules

After the per-entry-point pass, we merge redundant flows:

- **Full-equivalence merge**: two flows `A`, `B` where `A.nodes == B.nodes` and the sequences are identical → merge into one flow with both entry points added to `entry_nodes`. (Happens when a shared entry leads to two different external annotations, e.g. a function decorated as both an HTTP route and a CLI subcommand.)
- **High-overlap merge**: `|A.nodes ∩ B.nodes| / |A.nodes ∪ B.nodes| ≥ 0.95` → keep the flow with higher salience; fold the other's entry into `entry_nodes`.
- **Subset collapse**: if `A.nodes ⊂ B.nodes` and `A.sequence` is a prefix of `B.sequence`, drop `A` (it is an internal sub-traversal of `B`).

Merges are applied iteratively until stable.

### 5.5 Flow ID generation

`flow_id = "flow:" + sha1(entry_kind || entry_node_id || canonical_sequence)[:12]`

Canonical sequence is the sorted list of `(source, target)` pairs. Using a hash of the canonical sequence guarantees:

- Byte-identical IDs across re-runs on unchanged code (SC-4).
- A renamed or moved function (different node ID) yields a different flow ID — intentional; users can rebind via `flows.yaml`.

### 5.6 Determinism guarantees

- Every iteration over `G.nodes` / `G.edges` sorts by ID before iterating.
- DFS tie-breaking at a branch uses edge `source_location` then edge target ID.
- Merge rules are applied in a fixed order.
- The final flow list is sorted by `(salience desc, flow_id asc)`.

---

## 6. Flow naming (LLM pass)

### 6.1 Goal

Turn `flow:a7c4…` into `Login flow`. Keep it cheap, bounded, and stable.

### 6.2 Prompt structure

One batched prompt per run. Content:

- For each unnamed flow (up to `flow_limit`):
  - Entry kind.
  - Entry node label + source file + docstring (if any; already extracted by graphify).
  - Top 3 participants by degree within the flow.
  - First 5 edges of the sequence (to convey direction).
  - Terminal node labels.
- Response format: strict JSON array of `{flow_id, name (2–5 words), description (≤ 200 chars), confidence_self}`.

The prompt instructs:

- Names must be unique within the run; duplicates are rejected and the model is asked to retry.
- Names must be 2–5 English words, no emoji, no markdown, no quotes.

### 6.3 Cache key

`cache_key = sha256(serialize({flow_id, entry_kind, entry_label, top_participants, first_edges, terminals}))`

Cache is persisted at `graphify-out/.graphify_flow_names.json`. A cache hit on every flow means zero LLM cost on re-run.

### 6.4 Override file

`graphify-out/flows.yaml` is an optional user file. If present, keys are flow IDs and values are `{name, description?}`. Overrides win over cache and LLM output. The override file is written once by graphify on first run with auto-generated names so users can edit in place.

### 6.5 Fail-soft behavior

If the LLM call fails (no API key, network error, invalid JSON), flows retain their provisional IDs (`flow:a7c4…`) as names. The pipeline continues. A warning logged; report flags the naming gap.

### 6.6 Cost envelope

With `flow_limit = 100`, a prompt with 100 flow summaries is comfortably under 8k input tokens. One model call. This matches the cost profile of existing semantic labeling in graphify.

---

## 7. Pipeline integration

### 7.1 Call sites

- **Skill (`graphify/markdown/skill.md`)**: a new step is inserted between Step 4 (build + analyze) and Step 6 (exports). The step imports `from graphify.flows import synthesize_flows, name_flows`, calls `synthesize_flows(G)`, calls `name_flows(G, flows, cache_path)`, and calls `attach_hyperedges(G, flows)`.
- **CLI watch/update paths (`runtime/watch.py`, `analysis/wiki.py` incremental updates)**: flow synthesis is re-run whenever a new semantic pass completes. Because flows are derived, no flow-specific cache invalidation is needed — inputs change, output changes.

### 7.2 Cluster interaction

Flows do not influence Leiden clustering. Leiden runs on the pairwise graph only. Hyperedges are inspected post-clustering for reporting and visualization.

### 7.3 Report integration

`report.py:101–109` already renders hyperedges. We extend its hyperedge section with per-flow metadata:

- A "Flows" subsection lists the top 10 by salience.
- Each entry shows name, entry kind, participant count, and confidence tag.
- A pointer: "See `flow_graph.html` for interactive exploration."

This keeps `GRAPH_REPORT.md` scannable on the CLI.

### 7.4 Data artifacts

Outputs produced by this feature:

- `graphify-out/flow_graph.json` — full flow catalog with sequences, alt-paths, overlap index.
- `graphify-out/flow_graph.html` — dedicated viewer.
- `graphify-out/.graphify_flow_names.json` — internal cache.
- `graphify-out/flows.yaml` — user override file, written once with defaults on first run.
- `graphify-out/graph.json` — unchanged in structure, augmented with flow hyperedges in its `hyperedges` array.

### 7.5 Incremental update

When the watcher re-runs extraction on changed files, the call graph may change. Flow synthesis re-runs deterministically on the full graph; cache hits on unchanged flow content keep LLM cost at zero. A flow whose sequence changed gets a new flow ID (per §5.5); the old ID is removed. If the user had a name override for the old ID, graphify emits a stale-override warning in `GRAPH_REPORT.md` inviting the user to re-bind.

---

## 8. Renderer / viewer design

### 8.1 Renderer

vis-network, same CDN as existing graphs. The layout choice here is **timeline-like directed**: top-to-bottom or left-to-right, with the entry node pinned at origin and terminals at the far end. For shorter flows, a vertical "swim lane" by file name is used (each file is a horizontal lane; nodes sit in their file's lane, in call order).

### 8.2 HTML structure

Three-panel layout:

- **Left panel — flow list.** Sortable, filterable, with confidence chips, entry-kind icons, and overlap indicator.
- **Center panel — selected flow canvas.** Shows the full ordered sequence. Nodes carry the same color scheme as the semantic graph (community color). Edges show `relation` labels if configured.
- **Right panel — inspector.** Selected-node info (same shape as existing `graph.html` info panel) plus "Flows this node is in" with clickable chips to switch flows.

### 8.3 Overlap visualization

When a flow is selected, shared nodes (present in ≥ 2 flows) are outlined in an accent color. Hovering a shared node shows all flows it participates in.

Optionally, an "overlap matrix" toggle reveals a small matrix view: rows are flows, columns are nodes, cells are filled where the node participates.

### 8.4 Dataset shape handed to the viewer

`flow_graph.json` shape (top-level keys):

- `schema_version`: `"1.2"`.
- `flows`: list of flow objects (from §3.1, enriched for rendering).
- `nodes`: subset of `G`'s nodes that participate in any flow, with rendering attributes.
- `edges`: subset of `G`'s edges referenced by any flow sequence.
- `overlap_index`: `{node_id: [flow_id, …]}` — precomputed for O(1) lookup.
- `metrics`: per-flow metrics (fan-out, cross-file count, confidence, salience).

### 8.5 Cross-linking

The existing semantic viewer's sidebar and the Feature-1 structure viewer's sidebar both gain a "Flows" section for the currently selected node. Each flow chip deep-links into `flow_graph.html` with a query parameter (`?flow=flow:a7c4…`) that the flow viewer reads on load.

---

## 9. CLI, configuration, cache

### 9.1 CLI flags

- `--flows` (default on after Phase 6) — enable flow synthesis.
- `--no-flows` — disable.
- `--flow-limit N` — cap (default 100).
- `--flow-depth N` — max traversal depth (default 10).
- `--flow-name-model MODEL` — override the model used for naming (defaults to the platform's default).
- `--no-flow-names` — skip LLM naming; use provisional IDs.
- `--flows-yaml PATH` — use a custom overrides file path.

### 9.2 Help text

Help output in `__main__.py:main()` gains a "Flow hypergraph" section.

### 9.3 Cache

- Per-file AST cache unchanged.
- Flow naming cache lives in `.graphify_flow_names.json` and is versioned via the same `CACHE_VERSION` constant used by Feature 1.

### 9.4 `.graphifyignore`

Honored transitively — flows do not traverse into ignored files, because those files are not in `G` in the first place.

---

## 10. Testing strategy

### 10.1 Unit tests (`tests/test_flows.py`)

- Entry-point detection per framework (small fixture per framework).
- Source-order DFS determinism (fixture with multiple branches; assert canonical sequence).
- Cycle break (fixture with recursion).
- I/O terminator detection (fixture with a DB call + logging + HTTP client).
- Merge rules (fixture pairs matching full-equivalence, high-overlap, subset).
- Ambiguity handling (fixture with a function-name collision across files).
- Salience ranking stability.
- Flow ID determinism.

### 10.2 Naming tests (`tests/test_flow_naming.py`)

- Cache hit path: no model call when inputs unchanged.
- Cache miss path: mocked model returns structured JSON; assert names applied.
- Invalid model output: fallback to provisional IDs; warning logged.
- Override file: overrides win over cache and model.

### 10.3 Integration tests (`tests/test_pipeline.py` extension)

- Pipeline with `--flows` produces `flow_graph.{json,html}`.
- Pipeline with `--no-flows` leaves existing outputs unchanged (byte-compare `graph.json` modulo hyperedges).
- Pipeline with `--flows` adds exactly the expected hyperedges to `graph.json`.

### 10.4 Regression tests

- All existing tests pass.
- `tests/test_hypergraph.py` extended to cover flow hyperedges specifically.

### 10.5 Performance benchmark

- `tests/test_benchmark.py` extended with a flow-synthesis timing measurement; fails CI if ≥ 15% of pipeline time (SC-6).

### 10.6 Manual acceptance

- Run on `worked/karpathy-repos/` and inspect `flow_graph.html` visually against the reviewer's mental model.

---

## 11. Security, performance, observability

### 11.1 Security

- Flow names pass through `runtime/security.py:sanitize_label`.
- The override YAML is parsed with `yaml.safe_load` only. Any load-time exception is surfaced, not swallowed.
- No new network endpoints. The LLM call uses the existing model integration.

### 11.2 Performance

- Entry-point detection: O(|V|). Sub-second on 10k-node graphs.
- DFS per entry point: O(|V| + |E|) worst case, bounded by `max_depth`. Typical ≤ 100 ms per entry.
- Merge pass: O(F² log F) worst case for F = number of pre-merge flows; typically F ≤ 500, easily sub-100 ms.
- LLM pass: one call, ~8 kB prompt, ~4 kB response. Bounded by the model's latency; typically 5–15 s wall-clock.
- Viewer: `flow_graph.json` is slim (hyperedges reference IDs; no node/edge duplication); first paint under 3 s.

### 11.3 Observability

- Log counts: detected entries per kind, flows pre-merge, flows post-merge, LLM cache hits/misses.
- Log any flow that triggered the `AMBIGUOUS` downgrade and the reason.
- All errors bubble up — no silent swallow (per global coding rules).

---

## 12. Migration and backward compatibility

- `graph.json` schema additions are all optional. Existing consumers ignoring unknown keys continue working.
- Legacy hyperedges without `kind` default to `"generic"` at read time.
- Neo4j / GraphML / Cypher exports: hyperedges have historically not been serialized to these formats (they are a graph-level metadata concept). Unchanged. A future version may add a dedicated flow representation; out of scope v1.
- MCP server (`runtime/serve.py`): new queries will be added in v1.1 — e.g. `list_flows`, `get_flow`, `flows_for_node` — but are not required for v1.

Downgrade path: `--no-flows`. Or manually delete `flow_graph.{json,html}` and strip flow hyperedges from `graph.json`'s `hyperedges` array (trivially filterable by `kind == "flow"`).

---

## 13. Phased delivery plan

### Phase 0 — Schema + registry scaffolding
- Extend hyperedge schema (§3.1); update `validate.py`.
- Create `flows.py` registry stub, no detectors yet.
- Tests: schema round-trips.

### Phase 1 — Entry-point detection
- Implement per-language detectors for top 4 frameworks (Flask, Express, Spring, Rails) and plain `main()`/test patterns.
- Tests: AC-1, AC-2, AC-5, AC-6.

### Phase 2 — Flow derivation
- Source-order DFS, cycle break, I/O terminator, depth bound.
- Merge rules.
- Deterministic flow ID.
- Tests: AC-3, AC-4, AC-9, AC-10, SC-4.

### Phase 3 — LLM naming + cache + overrides
- Single batched prompt.
- Cache under `.graphify_flow_names.json`.
- `flows.yaml` override.
- Tests: AC-7, AC-8.

### Phase 4 — Report + existing viewer integration
- `GRAPH_REPORT.md` gets a Flows section.
- Existing `graph.html` shades flow hyperedges using the already-present hyperedge script (AC-12).
- Structure viewer (Feature 1) and semantic viewer both show flow memberships in node info panels (AC-13).

### Phase 5 — Dedicated flow viewer
- `flow_graph.json` export.
- `flow_graph.html` renderer with left list / center canvas / right inspector.
- Overlap highlights and shared-node counts.
- Search and filter (AC-14).
- `flow_limit` and salience ranking (AC-15).

### Phase 6 — Docs, skill, changelog, translations
- `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, all `skill*.md` variants.

### Phase 7 — Default-on rollout with `--no-flows` escape hatch.

---

## 14. Open technical questions

1. **Granularity of `sequence`**: store full (source, target, relation) tuples, or just edge IDs and dereference? Plan: store full tuples to keep `flow_graph.json` self-contained; dereference in the main `graph.json` copy.
2. **Flow hyperedges in Obsidian export**: should each flow become a community-style overview note? Propose: yes in v1.1, no in v1.
3. **Flows that consist entirely of `INFERRED` call edges**: show them? Propose: yes, but with a prominent confidence chip and a toggle to hide them.
4. **Flows whose entry point is only reachable from tests**: should those be classified as `test` regardless of their own annotation? Propose: yes — dominance by caller type.
5. **Multi-language flows (e.g., Python backend calling a Node subprocess)**: attempt to stitch? Propose: defer to v2; record the subprocess call as a terminal in v1.
6. **Overlap index encoding for large graphs**: list-per-node gets heavy above ~100 flows; consider bitsets or a CSR-like encoding. Profile first; switch only if needed.
7. **Should `GRAPH_REPORT.md` gain a dedicated `Flows` top-level section, separate from `Hyperedges`?** Propose: yes. Hyperedges section becomes the generic catch-all; Flows gets prominence.

---

## 15. Appendix — references into existing code

- `graphify/src/pipeline/extract.py:929` — call-graph pass; produces the `calls` edges that flow derivation consumes.
- `graphify/src/pipeline/build.py:83–85` — hyperedge round-trip; flow hyperedges attach via the same path.
- `graphify/src/pipeline/cache.py:123–168` — hyperedge cache round-trip (unchanged; flows are post-build).
- `graphify/src/pipeline/export.py:271–279` — `attach_hyperedges`; flows attach here.
- `graphify/src/pipeline/export.py:282–297` — `to_json`; flows appear in the `hyperedges` array.
- `graphify/src/pipeline/export.py:61–101` — existing hyperedge shading script used by the semantic viewer.
- `graphify/src/analysis/report.py:101–109` — hyperedge section in `GRAPH_REPORT.md`; extended with Flows subsection.
- `graphify/src/runtime/watch.py:22,77` — incremental-update hyperedge paths.
- `graphify/src/analysis/flows.py` — **new** module: detectors, derivation, merge, ID generation.
- `graphify/src/analysis/flow_naming.py` — **new** module: LLM pass + cache + override.
- `graphify/src/pipeline/export_flows.py` — **new** module (or new functions in `export.py`): `export_flow_json`, `export_flow_html`.
- `tests/test_flows.py`, `tests/test_flow_naming.py` — **new** tests.
- `tests/test_hypergraph.py` — extended coverage.

---

## 16. Acceptance review checklist (for implementer)

- [ ] New modules conform to 800-line ceiling; each function under 50 lines where practical.
- [ ] Type annotations on every public signature.
- [ ] No mutation of input lists; synthesis returns new lists.
- [ ] Flow ID is deterministic; test asserts byte-identical IDs on unchanged input.
- [ ] Salience formula documented inline.
- [ ] LLM cache paths covered by tests.
- [ ] `flows.yaml` override path covered by tests.
- [ ] `pytest tests/ -q` green; 80%+ coverage on new code.
- [ ] `bandit -r graphify/` clean.
- [ ] `black`, `isort`, `ruff` clean.
- [ ] `CHANGELOG.md` updated.
- [ ] Manual: open `flow_graph.html` on at least two corpora; overlap correctly surfaced; search works.
