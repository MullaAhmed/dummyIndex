# Feature 3 — Feature Hypergraph — Technical Design

**Document type:** Technical Design / RFC
**Companion to:** `plan/feature_3/logical/PRD.md`
**Status:** Draft v1
**Intended reader:** Engineers implementing, reviewing, or extending the feature hypergraph.
**Depends on:** Feature 1 (Structure Graph) for clean `node_kind` tagging, Feature 2 (Flow Hypergraph) for flow participation signals. If either is absent, feature synthesis runs in degraded mode with a clear warning.

---

## 0. How to read this document

This document answers the *how*. No code. Specific file:line references point at existing modules; "new" modules are marked. Sections stand alone; each implementer can pick up a section and work from it.

Organization:

1. Background on existing clustering, reporting, and semantic infrastructure.
2. High-level architecture.
3. Schema changes.
4. Signal aggregation (inputs to synthesis).
5. Feature derivation algorithm.
6. LLM synthesis pass (naming, description, role assignment).
7. Feature-to-feature dependency derivation.
8. Pipeline integration.
9. Renderer / viewer design.
10. `features.yaml` override protocol.
11. CLI, configuration, cache.
12. Testing strategy.
13. Security, performance, observability.
14. Migration and backward compatibility.
15. Phased delivery plan.
16. Open technical questions.
17. Appendix — references.

---

## 1. What we are building on

Everything graphify already does contributes signal to feature synthesis:

- **Leiden communities** — produced by `graphify/src/analysis/cluster.py`; returned as `{community_id: [node_id, …]}`.
- **Cohesion scores** — `score_all(G, communities)` returns a quality metric per community.
- **God nodes** — `graphify/src/analysis/analyze.py:god_nodes` identifies the most-connected real entities.
- **Surprising connections** — `surprising_connections()` returns cross-community edges that bridge distant parts of the graph.
- **Community labels** — the skill asks the LLM to name communities; results stored in `.graphify_labels.json`.
- **Suggested questions** — `suggest_questions(G, communities, labels)` returns graph-unique questions; useful as anchor prompts for feature naming.
- **Hyperedges** — already round-trip through `build` / `cache` / `export` / `report`.
- **Node metadata** — `source_file`, `source_location`, `file_type`, plus Feature 1's `node_kind` and Feature 2's flow memberships.
- **Docs / papers / images** — already extracted as nodes with `file_type` ∈ `{document, paper, image}`.
- **Rationale comments** (`# NOTE:`, `# WHY:`) — already captured as `rationale_for` nodes.

Feature 3 does not invent signals; it synthesizes them.

---

## 2. High-level architecture

### 2.1 Principles

- **Additive.** Feature outputs live alongside existing outputs; nothing existing is renamed or removed.
- **Hybrid derivation.** Deterministic signal aggregation first, then a single bounded LLM call, then deterministic post-processing (dependencies, weights, cross-linking).
- **Human authority.** `features.yaml` always wins. The feature derivation is a first-draft proposal.
- **Stable IDs.** Feature IDs are content-derived so unchanged code → unchanged IDs.
- **Hypergraph primitive reuse.** Features are hyperedges with `kind="feature"`. They coexist with flow hyperedges (`kind="flow"`) and generic hyperedges (`kind="generic"`) on the same graph object.

### 2.2 Pipeline placement

```
detect → extract → [structure synthesis] → build → cluster → analyze → [flow synthesis + naming] → [+ feature synthesis + naming + dep derivation] → report → export
```

Feature synthesis runs after flows for two reasons:

1. Flows are a signal (they tell us "these N functions execute together under entry X").
2. Per-feature flow lists are required for US-5 and AC-14.

### 2.3 Module layout

- `graphify/src/analysis/features.py` — **new** module. Signal aggregation, derivation, dependency derivation, ID generation. Deterministic. No I/O.
- `graphify/src/analysis/feature_naming.py` — **new** module. Single LLM call + cache + `features.yaml` override merge. I/O-bearing.
- `graphify/src/pipeline/export_features.py` — **new** module (or functions in `export.py` if it remains under 800 lines). `export_feature_json`, `export_feature_html`.

No extractor changes. No build changes beyond the schema extension in §3.

---

## 3. Schema changes

### 3.1 Hyperedge extensions (shared with Feature 2, with new fields)

Feature hyperedges use the same base shape introduced for flow hyperedges and add:

- `kind`: `"feature"`.
- `description`: 1–2 sentence summary.
- `members`: list of `{node_id, role, weight}` — replaces the simple `nodes` array for feature hyperedges (the base `nodes` array is computed as `[m.node_id for m in members]` for backward compat).
- `roles`: summary counts `{core: N, shared: N, entry: N, terminal: N, rationale: N, data: N}`.
- `flows`: list of flow IDs that implement this feature.
- `communities`: list of community IDs this feature spans.
- `sensitivity` (v1.1): `{tags: [str], reason: str}`.
- `confidence`: `EXTRACTED | INFERRED | AMBIGUOUS`.
- `evidence`: structured justification surfaced to the user — see §3.2.

### 3.2 `evidence` sub-schema

For auditability, each feature carries:

```
evidence: {
  community_ids: [int],
  representative_nodes: [node_id],       // top-N by degree within feature
  doc_node_ids: [node_id],               // docs that mention the feature name
  flow_ids: [flow_id],                   // contributing flows
  override_applied: bool,                // true if features.yaml touched this feature
  llm_reasoning: "..."                    // short LLM-emitted rationale, sanitized
}
```

This makes the feature auditable without adding free-form text in user-visible fields.

### 3.3 Node attribute additions

Each node in the exported JSON gains (again, only at export, not in in-memory `G`):

- `feature_memberships`: list of `{feature_id, role, weight}`.
- `primary_feature_id`: the single feature where this node is `core` with the highest weight, or null.

### 3.4 Inter-feature edges

Feature-to-feature dependencies are **not** stored as NetworkX edges on `G`. They live at `G.graph["feature_dependencies"]` (new) and are serialized at the top level of `feature_graph.json`. Reasons:

- NetworkX edges assume endpoints are nodes; features are hyperedges, not nodes.
- Keeping feature deps in a separate structure avoids muddying call-graph / import-graph traversals.

Edge shape:

```
{
  source_feature_id,
  target_feature_id,
  weight,
  evidence: {
    via_flows: [flow_id],
    via_shared_nodes: [node_id],
    via_imports: [[src_node, tgt_node], ...]
  }
}
```

### 3.5 Schema version

Bump `schema_version` from `"1.2"` (Feature 2) to `"1.3"`. Fields are all optional in `validate.py`.

---

## 4. Signal aggregation

The synthesis step consumes a structured snapshot of everything graphify knows. It lives entirely in memory — no file writes — and is the *sole* input to the deterministic derivation and the LLM prompt.

### 4.1 Structure signals

- Folder tree (Feature 1's folder nodes, if present; otherwise derived ad-hoc from file paths).
- File nodes grouped by folder.
- Class / function / method counts per file.

### 4.2 Topology signals

- Communities `{cid: [node_ids]}` with cohesion scores.
- God nodes (top N by degree, excluding file/folder nodes).
- Surprising cross-community edges.

### 4.3 Flow signals (Feature 2)

- Per flow: entry kind, entry label, participant set, salience.
- Per node: list of flows it participates in.

### 4.4 Semantic / documentation signals

- Doc / paper / image nodes grouped by file.
- `rationale_for` nodes grouped by their target node.
- Existing community labels (from `.graphify_labels.json`, if present).

### 4.5 Naming signals

- README top-level headings (already ingested as doc nodes).
- `ARCHITECTURE.md` section headings.
- Folder names (e.g. `auth/`, `billing/` — strong prior for feature names).
- Module docstrings of top-degree files.

All of the above are assembled into a single immutable "signal pack" dataclass. It is the *only* thing passed to the LLM and to the derivation functions. This gates reproducibility.

---

## 5. Feature derivation algorithm

### 5.1 Two-stage derivation

**Stage A — deterministic candidate generation.**
Produce a list of candidate features from topology and flows alone, without LLM help. This guarantees that even in `--no-feature-names` mode, useful features exist.

**Stage B — LLM synthesis.**
The LLM takes the signal pack plus Stage A candidates and proposes a refined feature set with names, descriptions, role assignments, and re-partitioning where justified.

Users can run either stage alone:

- `--features=deterministic` → Stage A only, names like `feature:community_3_plus_flows`.
- `--features=full` (default) → Stage A + Stage B.

### 5.2 Stage A — deterministic candidate generation

Algorithm:

1. **Seed from communities.** Each community with cohesion ≥ threshold becomes a candidate feature. Low-cohesion communities are flagged for potential merge.
2. **Enrich with flows.** For each candidate, add all nodes from any flow where ≥ 70% of participants already belong to the candidate. This extends a feature to include incidental participants.
3. **Attract shared utilities.** For each god node not already in a candidate, attach it with `shared` role to every candidate whose core contains ≥ 3 edges to that god node.
4. **Attach documentation.** Any doc / rationale node that mentions the label of ≥ 3 members of a candidate is attached with `rationale` role.
5. **Merge / split.**
   - Merge two candidates if their Jaccard similarity exceeds 0.75.
   - Split a candidate if it contains two disconnected subgraphs whose only links are `shared` nodes.
6. **Orphan detection.** Any node not attached anywhere is flagged as orphan.
7. **Stable ID assignment** (§5.5).

Output: an ordered list of `StageACandidate` records with nodes, tentative roles, weights, and membership evidence.

### 5.3 Stage B — LLM synthesis

Input: signal pack + Stage A candidates.

Single batched prompt (budget ≤ 8k input tokens) with:

- Short project description (from README first paragraph, if any).
- Folder tree summary (depth 2).
- Stage A candidates: id, member count, top-5 labels, community ids, flow ids.
- Instruction to either accept, rename, split, or merge each candidate — always citing evidence.
- Expected output: strict JSON.

Output JSON shape (abbreviated):

```
{
  "features": [
    {
      "id_hint": "payments",
      "name": "Payments",
      "description": "...",
      "members": [{"node_id": "...", "role": "core", "weight": 1.0}, ...],
      "flows": [...],
      "communities": [...],
      "evidence": {...}
    }, ...
  ],
  "orphans_review": [node_id, ...]
}
```

Post-processing:

- Validate every `node_id` exists in `G`.
- Clamp weights to [0.05, 1.0].
- Ensure every flow reference exists in `flow_graph.json`.
- Reject features with fewer than `min_feature_size` nodes (default 5).
- Reject features whose name collides with another's; force LLM to rename on retry.

Failure modes:

- Invalid JSON → retry once with stricter instruction; on second failure, fall back to Stage A only and log a warning.
- Missing API key → skip Stage B entirely; emit Stage A features with provisional names.

### 5.4 Role & weight derivation

For each feature and each member:

- **Role**:
  - `entry` if the node is an entry point of a flow belonging to this feature.
  - `terminal` if the node is a terminal of a flow belonging to this feature.
  - `core` if the node is uniquely in this feature's candidate seed (not shared with others).
  - `shared` if the node is `core` or `entry` in another feature.
  - `rationale` if `file_type ∈ {document, paper}` and the node references this feature's members.
  - `data` if the node is a config-like file (`.yaml`, `.toml`, `.json`, `.env`-style) and is read by the feature.
- **Weight**:
  - core → 1.0
  - entry / terminal → 0.9
  - rationale → 0.7
  - data → 0.6
  - shared → clip(1 / feature_count, 0.1, 0.5)

Roles and weights derived *after* LLM synthesis so the LLM's member choices remain authoritative but the labels stay deterministic.

### 5.5 Stable feature IDs

`feature_id = "feature:" + slug(name)` where `slug()` is lowercase, alphanumeric-with-dashes, collision-resolved by appending `-2`, `-3`, etc.

A content hash is additionally stored as `canonical_hash = sha1(sorted(member_node_ids))[:12]`.

The pair (`id`, `canonical_hash`) lets the `features.yaml` override mechanism track features even if their generated name changes between runs — the hash is the stable anchor.

### 5.6 Determinism guarantees

- All iteration over `G`, communities, flows, docs is done after stable sorting.
- Stage A operations are pure set/graph ops with sorted inputs.
- Stage B LLM output is cached by `sha256(signal_pack_canonical_json)` so unchanged inputs produce identical outputs.
- The final feature list is sorted by `(salience desc, id asc)`.

---

## 6. Feature naming pass

Encapsulated in `feature_naming.py`:

- Assembles the Stage B prompt.
- Calls the configured model via the same integration graphify already uses for community labeling (the skill's LLM calls).
- Parses and validates the JSON response.
- Applies `features.yaml` overrides *after* the LLM pass — user overrides win.
- Caches results in `graphify-out/.graphify_feature_names.json`.

### 6.1 features.yaml override protocol

The override file at `graphify-out/features.yaml` has the shape:

```
features:
  - id: feature:payments
    name: "Payments"                       # override name
    description: "..."                     # override description
    pin:                                   # pin these nodes into this feature
      - src_billing_charge
      - src_billing_refund
    exclude:                               # remove these nodes from this feature
      - src_billing_test_fixture
    merge_with: []                         # optionally list other feature ids to merge in
features_new:                              # user-defined features from scratch
  - id: feature:infra
    name: "Infrastructure"
    nodes:
      - logger
      - db
      - cache
    description: "Shared infrastructure utilities"
```

The synthesis step, after Stage B, reads this file and applies each directive in a documented order:

1. Create `features_new` entries first.
2. Apply `pin` additions.
3. Apply `exclude` removals (log a warning if this empties a feature).
4. Apply `merge_with` mergers (both sides' members union; override name/description as specified).
5. Re-derive roles and weights on the post-override membership.

Overrides are always applied before the dependency derivation pass (§7) so dependencies reflect the user's authoritative view.

### 6.2 Cost envelope

One batched LLM call per run. ≤ 8 kB input, ≤ 4 kB output. Matches existing community-labeling cost.

---

## 7. Feature-to-feature dependency derivation

Runs after all features are finalized. Deterministic.

Algorithm:

1. Initialize empty dependency map `{(A, B): evidence}`.
2. **Flow transitions.** For each flow, if the flow's entry belongs to feature `A` and the flow's sequence later passes through an entry node of feature `B`, add `A → B` with `via_flows` evidence.
3. **Cross-core imports.** For each edge in `G` where `relation ∈ {imports, imports_from, uses, inherits}` and source belongs to `A` as `core` and target belongs to `B` as `core`, add `A → B` with `via_imports` evidence.
4. **Shared-as-core.** For each node `n` that is `shared` in `A` and `core` in `B`, add `A → B` with `via_shared_nodes` evidence.
5. **Aggregate.** Merge duplicate `(A, B)` entries, summing evidence into weight.
6. **Cycle flagging.** If both `A → B` and `B → A` exist, flag both edges with `is_mutual=true`.
7. **Prune.** Drop edges with weight below `dep_threshold` (default 0.1).

The resulting list is stored at `G.graph["feature_dependencies"]` and re-serialized into `feature_graph.json`.

---

## 8. Pipeline integration

### 8.1 Call site

Inserted into the skill after Step 4 (build/analyze/export) and after flow synthesis:

```
features = synthesize_features(G, communities, flows, detection, docs, signal_pack)
features = name_features(features, cache_path='.graphify_feature_names.json',
                         overrides_path='features.yaml', model=configured_model)
deps = derive_feature_dependencies(G, features, flows)
attach_hyperedges(G, features)
G.graph["feature_dependencies"] = deps
```

`attach_hyperedges()` already handles dedup and idempotency.

### 8.2 Report integration

`GRAPH_REPORT.md` gains a top-level "## Features" section above the existing "## Communities" section. Structure:

- Top 5 features: name, description, size, confidence.
- Feature-to-feature dependencies summarized as a short directed list.
- Orphan list (if any).
- Pointer: "See `feature_graph.html` for interactive exploration."

Existing "Communities" section is retained unchanged; users with workflows depending on it are not affected.

### 8.3 Incremental update behavior

When `watch.py` re-runs the pipeline on a change:

- Signal pack is recomputed; a feature whose underlying members change gets a new `canonical_hash`.
- If the user's `features.yaml` references a stale hash, graphify logs a migration hint but keeps the overrides applied by name/slug where possible.

### 8.4 Wiki integration

`graphify/src/analysis/wiki.py` currently renders one article per community. We extend it (v1.1) to also render one article per feature, named `feature_<slug>.md`. v1 deliberately does not change the wiki to keep the feature release scoped.

---

## 9. Renderer / viewer design

### 9.1 Renderer choice

Two viable options:

- **vis-network** — reuse the existing dependency, consistency with other graphify viewers.
- **D3 (custom)** — richer bubble/Venn rendering for overlapping features.

**Decision**: vis-network for v1 for consistency and minimal new dependencies. Features are rendered as *cluster groups* with per-group styling. Shared-node overlap is visualized using vis's multi-group tagging (a node can belong to multiple groups by stacking group membership in its tooltip and using a multi-color swatch icon).

D3-based Venn rendering is tracked for v1.1 as a potential upgrade if user feedback asks for it.

### 9.2 Data shape passed to the viewer

`feature_graph.json`:

- `schema_version`: `"1.3"`.
- `features`: list of feature objects, each with members (role+weight), flows, communities, evidence.
- `feature_dependencies`: list of dependency objects (§7).
- `nodes`: subset of `G` nodes that belong to any feature.
- `edges`: subset of `G` edges that belong to any feature (for in-feature highlighting).
- `overlap_matrix`: `{node_id: [feature_id, ...]}` precomputed.
- `metrics`: per-feature metrics (member count, dep count, flow count, community count).

### 9.3 Viewer layout

- **Left sidebar** — feature list, sortable/filterable, with confidence chips and member-count badges.
- **Center canvas** — features drawn as large translucent colored disks; overlapping disks where shared nodes exist; nodes placed in disk centers (core) or overlap regions (shared); dependency arrows drawn between disks with thickness = weight.
- **Right inspector** — selected feature: description, evidence block, member list grouped by role, flow list, community list, dependency list.

Two view modes:

- **Map mode** (default): the disk layout above.
- **Table mode**: features as rows; columns are flow count, member count, deps, sensitivity (v1.1).

### 9.4 Overlap highlighting

Clicking a shared node in the center canvas highlights every feature that contains it and fades everything else. A toolbar button "isolate shared" shows only shared nodes with their feature memberships as chips.

### 9.5 Cross-linking

From the feature viewer:

- Clicking a flow chip opens `flow_graph.html?flow=<id>`.
- Clicking a community chip opens `graph.html` filtered to that community.
- Clicking a node chip opens the structure viewer (Feature 1) scrolled to that node, or the semantic viewer.

From the other viewers:

- Semantic (`graph.html`): node info panel gains a "Features" section listing this node's feature memberships with chips deep-linking into `feature_graph.html`.
- Structure (Feature 1 `structure_graph.html`): same addition.
- Flow (Feature 2 `flow_graph.html`): per-flow inspector gains "Implements feature(s)" badges.

---

## 10. `features.yaml` override protocol — details

### 10.1 Lifecycle

- On first run with `--features` enabled, graphify writes `features.yaml` with default content reflecting the derived features. It is a commentable starter file.
- On subsequent runs, graphify reads `features.yaml` if it exists and treats it as authoritative.
- If `features.yaml` is absent, graphify writes it again at the end of the run (a "did you rm by mistake?" safety net). This behavior is off if `--no-features-yaml` is passed.

### 10.2 Schema validation

- Uses `yaml.safe_load`.
- Validated against a lightweight schema (can be pydantic/dataclass-based; no heavyweight dependency added).
- Any schema violation raises an error with the offending line number; pipeline aborts. Silent fallback would be dangerous given the "human wins" principle.

### 10.3 Diff surfacing

On each run, if `features.yaml` produced changes relative to synthesis, print:

```
Features: 3 kept from override, 2 merged, 1 new (user-defined), 0 excluded
```

Full diff written to `graphify-out/.graphify_feature_diff.md` for audit.

---

## 11. CLI, configuration, cache

### 11.1 CLI flags

- `--features` (default on in Phase 7) — enable feature synthesis.
- `--no-features` — disable.
- `--feature-limit N` — cap features surfaced (default 20).
- `--feature-mode {deterministic, full}` — Stage A only vs A+B (default `full`).
- `--no-feature-names` — same as `--feature-mode deterministic`; convenience alias.
- `--features-yaml PATH` — custom override file path.
- `--feature-model MODEL` — LLM override.
- `--dep-threshold FLOAT` — minimum dependency weight to surface (default 0.1).
- `--min-feature-size N` — minimum members required (default 5).

### 11.2 Help text

`__main__.py:main()` help block gains a "Feature hypergraph" section.

### 11.3 Caches

- `graphify-out/.graphify_feature_names.json` — keyed by signal-pack hash; stores LLM responses.
- Same `CACHE_VERSION` bump mechanism as prior features.
- On cache hit and no override change, zero LLM calls and zero semantic re-processing.

### 11.4 `.graphifyignore`

Honored transitively — ignored paths never enter the signal pack.

---

## 12. Testing strategy

### 12.1 Unit tests (`tests/test_features.py`)

- Signal-pack assembly: small fixtures, assert expected shape.
- Stage A candidate generation: fixture with 3 communities → expect 3 candidates before enrichment, with flow enrichment and god-node attachment asserted separately.
- Merge / split thresholds: pairs crossing the Jaccard threshold merge; subgraphs disconnected except by shared nodes split.
- Role / weight derivation: every role case has a dedicated fixture and expected output.
- Stable ID: same inputs → same IDs.
- Orphan detection.

### 12.2 Naming tests (`tests/test_feature_naming.py`)

- Stage B cache hit path: no model call.
- Stage B cache miss: mocked model returns JSON; features named.
- Invalid model output → retry → final fallback to Stage A names.
- `features.yaml` override paths: pin, exclude, merge_with, features_new, name/description overrides.
- Conflicting override (e.g. pin and exclude same node) → error with line number.

### 12.3 Dependency derivation tests

- Fixture: flow transitioning from feature A's entry into feature B's entry → A→B edge.
- Cross-core imports → A→B edge.
- Shared-as-core → A→B edge.
- Mutual dependency flagged.
- Threshold pruning.

### 12.4 Integration tests (`tests/test_pipeline.py`)

- Full pipeline with `--features` produces `feature_graph.{json,html}`.
- Without `--features`, byte-stable `graph.json` modulo feature hyperedges.
- Re-run on unchanged input: cache hit, zero LLM cost, byte-identical output (modulo any naming-cache timestamps which are separate).

### 12.5 Regression tests

- All existing tests pass.
- `tests/test_hypergraph.py` extended to cover `kind="feature"` edges.

### 12.6 Performance benchmark

- Extend `tests/test_benchmark.py` with a feature-synthesis timing step; CI fails if ≥ 20% of pipeline time.

### 12.7 Manual acceptance

- Run on `worked/karpathy-repos/` and at least one real multi-feature repo; human review ≥ 80% features judged meaningful (SC-1).

---

## 13. Security, performance, observability

### 13.1 Security

- Feature names and descriptions pass through `runtime/security.py:sanitize_label`.
- `features.yaml` parsed with `yaml.safe_load`.
- LLM output validated strictly before it touches the graph.
- `evidence.llm_reasoning` stripped of any HTML and capped at 500 chars before being written to any user-visible artifact.
- No new network endpoints.

### 13.2 Performance

- Signal-pack assembly: O(|V| + |E| + |flows|). Sub-second on 10k-node graphs.
- Stage A derivation: polynomial in community count × god-node count; typically ≤ 100 ms.
- Stage B LLM: one call; 5–20 s wall-clock.
- Dependency derivation: O(|flows| + |features|² · avg_core_size); typically ≤ 200 ms.
- Export JSON: linear; ≤ 200 ms.
- Viewer first paint: ≤ 3 s on typical feature counts (≤ 50).

### 13.3 Observability

- Log counts: Stage A candidates, Stage A after merges/splits, Stage B count, override-applied count, orphans.
- Log LLM cache hit/miss.
- Log per-feature member count and confidence distribution.
- Emit `graphify-out/.graphify_feature_diff.md` on every run that changes outputs.

---

## 14. Migration and backward compatibility

- `graph.json` schema additions are optional.
- Legacy hyperedges (no `kind`) continue to render as generic shaded regions in existing viewers.
- Neo4j / GraphML / Cypher exports unchanged. Features are not serialized into those formats in v1; revisit in v1.1.
- MCP server can add `list_features`, `get_feature`, `features_for_node` queries — targeted for v1.1.
- Downgrade path: `--no-features` skips synthesis. Deleting `feature_graph.*` and stripping `kind == "feature"` hyperedges from `graph.json` fully reverts.

---

## 15. Phased delivery plan

### Phase 0 — Schema + scaffolding
- Extend hyperedge schema (§3); update `validate.py`.
- Stub `features.py`, `feature_naming.py`, `export_features.py` with empty functions returning empty structures.
- Tests: schema round-trips.

### Phase 1 — Signal aggregation
- Implement signal-pack assembly.
- Tests: fixtures → expected shapes.

### Phase 2 — Stage A deterministic derivation
- Seed, enrich, attract, attach, merge/split, orphan detection, stable IDs.
- Tests: AC-2, AC-6, AC-7, AC-8 (for the deterministic mode).

### Phase 3 — Stage B LLM synthesis
- Prompt assembly, cache, validation, retry.
- `features.yaml` first-write-on-first-run.
- Tests: AC-1, AC-10.

### Phase 4 — `features.yaml` override
- pin / exclude / merge_with / features_new / name / description.
- Diff file.
- Tests: AC-4, AC-5.

### Phase 5 — Dependency derivation
- Flow transitions, cross-core imports, shared-as-core.
- Cycle flagging and pruning.
- Tests: AC-3.

### Phase 6 — Report + existing viewer integration
- `GRAPH_REPORT.md` Features section.
- Structure / flow / semantic viewer info panels gain Features section.
- Tests: AC-13, AC-14.

### Phase 7 — Dedicated feature viewer
- `feature_graph.json` export.
- `feature_graph.html` map + table modes.
- Overlap highlighting.
- Tests: AC-9, AC-11, AC-12, AC-15.

### Phase 8 — Docs + skill + changelog + translations

### Phase 9 — Default-on rollout with `--no-features` opt-out.

---

## 16. Open technical questions

1. **Stage A threshold calibration.** Jaccard 0.75 for merges, 0.7 flow overlap for enrichment — need empirical tuning on multiple corpora. Propose: ship defaults; expose flags; adjust after Phase 9 user feedback.
2. **Sensitivity detection (v1.1).** Allow-list-based pattern matching (Stripe, AWS, auth tokens, PII fields) vs LLM-based. Propose: pattern-based in v1.1, LLM-augmented in v2.
3. **Venn/D3 renderer (v1.1).** Move from vis-network cluster styling to custom D3 rendering if overlap becomes unreadable with >8 features. Decision deferred.
4. **Wiki integration.** Add `feature_<slug>.md` articles to `--wiki` in v1.1. Requires `wiki.py` changes; keep out of v1.
5. **MCP queries.** `list_features`, `get_feature`, `features_for_node` — added in v1.1 once feature data is stable.
6. **Nested sub-features.** v1.1 or v2. Data model supports it via `sub_features` on each feature; viewer does not render nesting in v1.
7. **Community label reuse vs re-labeling.** If community labels already exist (from an earlier run), should the LLM be allowed to rename them? Propose: no — community labels are a separate concept; features can carry both original community IDs and feature-level names.
8. **Handling repos with no flows (Feature 2 disabled).** Feature synthesis degrades: no `entry`/`terminal` roles assigned, no flow-based dependencies. Graph is still produced with clearly lower quality. Log a warning recommending `--flows`.

---

## 17. Appendix — references into existing code

- `graphify/src/analysis/cluster.py` — `cluster()`, `score_all()`, `cohesion_score()`. Consumed by signal aggregation.
- `graphify/src/analysis/analyze.py:39` — `god_nodes()`. Consumed.
- `graphify/src/analysis/analyze.py:61` — `surprising_connections()`. Consumed.
- `graphify/src/analysis/analyze.py` — `suggest_questions()`. Consumed (for prompt anchors).
- `graphify/src/analysis/report.py:101–109` — hyperedge section; extended with a Features subsection above it.
- `graphify/src/pipeline/export.py:271–279` — `attach_hyperedges`; features attach through this.
- `graphify/src/pipeline/export.py:282–297` — `to_json`; features serialize into the `hyperedges` array alongside flows.
- `graphify/src/runtime/watch.py` — incremental update path; re-runs synthesis.
- `graphify/src/analysis/features.py` — **new**.
- `graphify/src/analysis/feature_naming.py` — **new**.
- `graphify/src/pipeline/export_features.py` — **new**.
- `tests/test_features.py`, `tests/test_feature_naming.py` — **new**.
- `tests/test_hypergraph.py` — extended.

---

## 18. Acceptance review checklist (for implementer)

- [ ] New modules under 800 lines; functions under 50 where practical.
- [ ] Type annotations on every public signature.
- [ ] Immutable inputs; synthesis returns new structures.
- [ ] Stable feature IDs; test asserts byte-identical IDs on unchanged input.
- [ ] LLM cache + `features.yaml` override paths covered.
- [ ] Dependency derivation covered including mutual cycles.
- [ ] Orphan detection surfaces in report.
- [ ] `pytest tests/ -q` green; 80%+ coverage on new code.
- [ ] `bandit -r graphify/` clean.
- [ ] `black`, `isort`, `ruff` clean.
- [ ] `CHANGELOG.md` updated.
- [ ] Manual: open `feature_graph.html` on ≥ 2 real corpora; overlap correct; deps plausible.
- [ ] `features.yaml` round-trip works: edit, re-run, see the edit honored.
