# Feature 3 — Feature Hypergraph (Capability-Level Clusters with Shared Infrastructure)

**Document type:** Product Requirements Document (PRD)
**Audience:** Product, engineering leads, UX, doc writers
**Status:** Draft v1
**Scope note:** This PRD describes *what* and *why* only. No code, no APIs, no file layout. Technical design lives in `plan/feature_3/technical/TECHNICAL.md`.
**Depends on:** Feature 1 (Structure Graph) and Feature 2 (Flow Hypergraph). Feature 3 is the capstone — it references both and degrades gracefully if either is absent.

---

## 1. Summary

Codebases organize themselves around **features** — business-level capabilities like *Authentication*, *Payments*, *Reporting*, *Search*, *Notifications*, *Admin Console*. A feature is not a folder, a class, or a call chain; it is a cross-cutting concept that recruits pieces from all of those. A single feature pulls in a handful of routes, a few classes, a dozen functions, a couple of config files, and — critically — **shared infrastructure** that also participates in other features: `db.query`, `logger`, `cache.get`, `auth.verify_token`, `ratelimiter.check`.

Today, dummyindex shows communities via Leiden detection. Communities are a useful proxy for features, but they are not features. Communities are edge-density clusters; features are product-meaningful groupings that often span communities and always share infrastructure across feature boundaries. Two limits of the existing community view:

1. A community is a **partition**. Every node belongs to exactly one community. That rules out expressing shared utilities, which is how real codebases actually organize themselves.
2. A community is **unnamed** until a labeling pass assigns a short phrase. Users still have to mentally bridge "Community 3" to "the Payments feature."

Feature 3 introduces the **Feature Hypergraph** — a new artifact pair (`feature_graph.json` + `feature_graph.html`) in which each feature is a first-class hyperedge. Features may overlap freely. A utility that serves three features appears in all three hyperedges explicitly. Each feature carries a name, a short description, a list of participating nodes weighted by role, a list of the flows (Feature 2) that implement it, a list of the communities it touches, and a dependency graph to other features.

Feature 3 is the capstone because it combines every other signal dummyindex already produces:

- Structure (Feature 1): folders, files, classes, functions.
- Semantics (existing): communities, god nodes, surprising connections, semantic similarity.
- Flows (Feature 2): end-to-end execution paths with entries and terminals.
- Documentation (existing): docs, rationale comments, PDFs, images.

The feature-level hypergraph synthesizes these into the user's actual mental model.

---

## 2. Problem statement

### 2.1 What users do today

A user who wants to answer "what is the Payments feature in this codebase?" today has to:

1. Skim `GRAPH_REPORT.md` for communities.
2. Guess which community is Payments — there may not be one.
3. Cross-check folders (`billing/`, `charges/`, `subscriptions/`?).
4. Find the Stripe integration file.
5. Mentally reconstruct the feature boundary.

A user who wants to answer "which features does this `db.query` helper serve?" gets nothing from the current graph: the community partition assigns it to one community; the shared reality is invisible.

### 2.2 Why communities are not features

Communities are a graph-topological artifact. They maximize intra-community edges and minimize inter-community ones. That produces excellent *topical* clusters but:

- A *product* feature often includes both a densely-connected core *and* thin references into shared utility modules. Leiden places the utility in the utility community; the feature boundary disappears.
- A *product* feature may span two semantically distinct modules (e.g. "Notifications" spans the email module and the in-app toast module). Leiden splits those into separate communities.
- A *product* feature is named by humans and shaped by product decisions. Leiden doesn't know that.

### 2.3 Why a hypergraph

Partitions cannot express shared membership. Sets can. Each feature is a set of node IDs; two features are allowed to intersect. A shared utility is explicitly a member of every feature that uses it. This is the only data structure that honors the shape of real codebases.

### 2.4 Why this is the capstone

Features are the dial users turn most. When a PM asks "can we ship Payments v2 without touching Search?" — that is a feature-scoped question. When a reviewer asks "is this PR cross-cutting?" — that is a feature-interference question. When an AI assistant builds a context window for a user task — feature membership is the right filter, not community membership and not folder membership.

Features also give the graph a **business-readable** top layer. The existing report reads like engineering output. A feature graph reads like a product org chart.

---

## 3. Users and personas

### Persona A — Product manager
**Situation:** Planning the next quarter's roadmap.
**Need:** A list of features in the codebase, their sizes, their shared dependencies, and their cross-links.
**Value from feature:** A high-level map produced automatically from the code, usable as a starting point for a roadmap discussion without engineering handholding.

### Persona B — Engineering lead reviewing architecture
**Situation:** Pre-refactor audit.
**Need:** Identify cross-feature coupling — where the same code serves many features, and where changes ripple across feature boundaries.
**Value from feature:** Immediate surface area of shared infrastructure. Feature dependencies shown as arrows between features, not between classes.

### Persona C — Engineer onboarding onto a specific feature
**Situation:** Assigned to work on "Notifications" for the first time.
**Need:** Everything that constitutes Notifications: its code, its flows, its shared helpers, its dependencies on other features.
**Value from feature:** One-click scope.

### Persona D — AI coding assistant
**Situation:** User asks "implement a new kind of notification." The assistant needs a bounded context.
**Need:** The exact set of files and functions that constitute Notifications, plus the shared infrastructure that Notifications uses.
**Value from feature:** Tight, correct context built from the feature hyperedge instead of grep-ing for "notification" across the repo.

### Persona E — Security / compliance reviewer
**Situation:** Audit which features touch PII, payments, auth, or external integrations.
**Need:** Features tagged by sensitivity; list of shared code that crosses sensitive feature boundaries.
**Value from feature:** Sensitivity propagates along hyperedge overlap; the review list is filtered to high-risk crossings.

---

## 4. User stories

### 4.1 Primary stories (P0 — must ship in v1)

- **US-1** As a user, after running dummyindex I have a list of features with names, descriptions, and participant counts.
- **US-2** I can click a feature and see every node that participates, grouped by role: **core** (unique to this feature), **shared** (present in 2+ features), **entry** (entry points), **terminal** (I/O endpoints).
- **US-3** I can see, for any node, the features it belongs to (hypergraph overlap).
- **US-4** I can see dependencies between features — arrows labeled "depends on" derived from flow transitions, imports, and shared god nodes.
- **US-5** I can see which flows (Feature 2) implement each feature.
- **US-6** I can see which communities (Leiden) the feature spans.
- **US-7** I can search and filter features.
- **US-8** Re-runs on unchanged code produce the same feature set with the same IDs.
- **US-9** I can override feature names, merge two features, split one, or assign nodes to a feature manually via a `features.yaml` file that dummyindex respects.

### 4.2 Secondary stories (P1 — v1.1)

- **US-10** I can export a per-feature overview as a standalone markdown or PDF handed to product/design.
- **US-11** I can see each feature's "sensitivity" tag — inferred from kind of data it touches (detected by file names, API surface, dependency names).
- **US-12** I can see "feature hotspots" — files that participate in 3+ features (maximum cross-feature coupling).
- **US-13** I can see the **feature-of-features** dependency graph rendered as an architecture diagram.
- **US-14** The feature report surfaces "orphan" nodes — code that doesn't clearly belong to any feature, for review.

### 4.3 Tertiary stories (P2 — later)

- **US-15** Version-to-version diff: "feature X added these nodes, lost these, gained a new dependency on feature Y."
- **US-16** I can ask the graph "if I delete feature X, what breaks?" and see the blast radius.
- **US-17** Sub-features (Payments → Checkout, Refunds, Subscriptions) rendered as a two-level hypergraph.
- **US-18** Cross-repo feature linking (out of scope v1; placeholder).

---

## 5. Scope

### 5.1 In scope for v1

- **Feature derivation** from the combined signals of communities, flows, folder structure, and top-level semantic concepts.
- **LLM labeling** to propose feature names and short descriptions. Bounded, cached, overridable.
- **Hypergraph membership** with weights indicating strength of participation ("core" 1.0 to "tangentially used" 0.1).
- **Feature-to-feature dependency edges**, derived from flow transitions and shared-node overlaps.
- **A data artifact** (`feature_graph.json`) carrying all of the above.
- **A viewer** (`feature_graph.html`) that renders features as large overlapping bubbles with clickable drill-down.
- **Report integration**: `GRAPH_REPORT.md` gains a "Features" section with names, sizes, dependencies, and flow links.
- **Cross-references** from structure and flow viewers to the feature viewer.
- **`features.yaml` override file** for human-in-the-loop corrections.

### 5.2 Out of scope for v1

- **Automated sub-feature trees.** We emit flat features; sub-features are v1.1.
- **Feature sensitivity tagging.** v1.1.
- **Blast-radius simulation.** v2.
- **Diffing across git revisions.** v2.
- **Cross-repo feature linking.** v2+.
- **Real-time feature updates from CI signals.** Out of scope indefinitely.

---

## 6. Logical model

### 6.1 What a feature is

A feature is a **named set of nodes** with:

- A human-readable name (2–5 words, e.g. "User Authentication", "Stripe Billing", "Daily Reports").
- A short description (≤ 200 chars).
- A membership set, where each node carries a **weight** ∈ (0, 1] and a **role** ∈ {core, entry, terminal, shared, rationale, data}.
- A set of flow IDs (Feature 2) that implement it.
- A set of community IDs (Leiden) it touches.
- A dependency list of other feature IDs.
- A confidence tag: `EXTRACTED` (feature directly named in docs/code), `INFERRED` (derived from signals), `AMBIGUOUS` (multiple candidate groupings).

### 6.2 How features differ from communities

| Property | Community | Feature |
|----------|-----------|---------|
| Membership | Partition (exactly one) | Hypergraph (zero or more) |
| Named | After labeling pass | Yes, by design |
| Source of truth | Graph topology (Leiden) | Synthesis of topology + flows + structure + docs + LLM |
| Shared utilities | Assigned to one community | Appear in every consuming feature |
| Can span folders | Yes | Yes |
| Can span languages | Yes | Yes |
| Dependency graph | No | Yes |

Both exist in the output. Communities remain the unsupervised topological layer. Features are the curated product-level layer.

### 6.3 Membership weights and roles

A node's participation in a feature carries:

- **Role** — what this node does inside the feature:
  - `core`: the feature's identity would change if this node were removed.
  - `entry`: an entry point of a flow that belongs to this feature.
  - `terminal`: an I/O terminal the feature writes to or reads from.
  - `shared`: participates, but also participates in ≥ 2 other features.
  - `rationale`: a docs/comment/PDF node explaining part of this feature.
  - `data`: a config file or data schema the feature depends on.
- **Weight** — a number in (0, 1] roughly equal to "fraction of this node's activity that serves this feature." Defaults:
  - core → 1.0
  - entry / terminal → 0.9
  - rationale → 0.7
  - data → 0.6
  - shared → 1 / (number of features sharing), clipped to [0.1, 0.5]

Weights are visualization hints, not probabilities. Thresholds are user-adjustable.

### 6.4 Feature-to-feature dependencies

A directed edge `Feature A → Feature B` is emitted when any of:

- A flow belonging to A transitions through an entry point of B.
- A node that is `core` in A has an outgoing `imports`, `imports_from`, `uses`, or `inherits` edge to a node that is `core` in B.
- A `shared` node in A is `core` in B.

Edge weight aggregates the above signals. Cycles are allowed (A depends on B depends on A — mutual) but flagged.

### 6.5 Orphans

A node not assigned to any feature is an **orphan**. Orphans are surfaced in the report as a review list. Common causes: experimental code, dead code, pure infrastructure that should be its own synthetic "Infrastructure" feature.

### 6.6 Confidence model

- `EXTRACTED`: the feature name or scope is stated directly in docs, README, `ARCHITECTURE.md`, or module-level docstrings that dummyindex already ingests. Example: a README section titled "Payments" that lists files.
- `INFERRED`: the feature is synthesized from signals (communities + flows + folder names + LLM).
- `AMBIGUOUS`: two plausible features compete for the same dense region; both are emitted, tagged, and surfaced for user review.

---

## 7. Interaction model

The viewer provides:

- **Feature list** with size, description, confidence chip, dependency count, flow count.
- **Feature canvas** with each feature rendered as a large translucent bubble. Overlapping bubbles represent shared nodes — Venn-diagram-like where overlaps exist in reality.
- **Node chips** placed inside their feature bubbles. Shared nodes sit in the overlap region of the features they participate in.
- **Dependency arrows** drawn between feature bubbles with aggregate weight thickness.
- **Inspector** showing selected feature's core/shared/entry/terminal lists, flows, communities, and depended-upon features.
- **Search** across feature names, node labels, flow labels.
- **Filter** by confidence, by minimum weight, by role.
- **Mode switch** between "feature map" (bubbles) and "feature table" (tabular view sortable by any column).

---

## 8. Success criteria

- **SC-1 (Meaningful features)** On a representative corpus, ≥ 80% of emitted features are judged meaningful by a human reviewer — meaning: the name fits, the membership makes sense, the dependencies are plausible.
- **SC-2 (Shared-node correctness)** Shared utilities (like loggers, DB helpers, validators) appear in every feature that uses them meaningfully, not just one.
- **SC-3 (Determinism)** Running dummyindex on unchanged code produces the same features with the same IDs and the same membership.
- **SC-4 (Override respect)** `features.yaml` overrides are honored byte-for-byte and do not regress on subsequent runs.
- **SC-5 (No regressions)** All existing outputs unchanged except for the additive feature hyperedges in `graph.json`.
- **SC-6 (Performance)** Feature synthesis adds less than 20% to pipeline wall-clock. The single LLM call is bounded ≤ 8 kB input.
- **SC-7 (Cross-link correctness)** Every feature's listed flows exist in `flow_graph.json`. Every feature's listed communities exist in `GRAPH_REPORT.md`. No dangling references.
- **SC-8 (AI-assistant utility)** A coding assistant given only `feature_graph.json` can answer "list every file that contributes to the Payments feature" deterministically.

---

## 9. Acceptance criteria

| # | Scenario | Expected |
|---|----------|----------|
| AC-1 | Repo with 5 major functional areas | 5–10 features emitted, each with a sensible name |
| AC-2 | Repo with a `utils/` folder used everywhere | Utility functions appear as `shared` members in multiple features |
| AC-3 | Feature A's flow passes through Feature B's entry | A → B dependency edge emitted |
| AC-4 | User adds entry in `features.yaml`: `{id: "auth", nodes: [file_x, func_y]}` | On next run, `auth` feature exists with those nodes attached |
| AC-5 | User renames a feature via `features.yaml` | Rename persists; ID stable |
| AC-6 | Single-file repo | At most one feature emitted (the whole repo or none) |
| AC-7 | Repo where communities don't align with features | Features span communities and each feature lists the communities it touches |
| AC-8 | Node that clearly doesn't fit any feature | Appears in orphan list in `GRAPH_REPORT.md` |
| AC-9 | Two plausible groupings of the same region | Two `AMBIGUOUS`-tagged features emitted, both surfaced |
| AC-10 | Re-run with cache: no LLM call | Feature names identical, cache hit reported |
| AC-11 | `--no-features` passed | `feature_graph.{json,html}` not emitted; existing outputs unchanged |
| AC-12 | Feature hyperedges round-trip into `graph.json` | `kind == "feature"` hyperedges present |
| AC-13 | Structure viewer (Feature 1) node info panel | Shows "Features" section with the node's feature memberships |
| AC-14 | Flow viewer (Feature 2) per-flow detail | Shows "Implements feature" badge linking into feature viewer |
| AC-15 | Feature with zero flows (pure data / config cluster) | Emitted; flow list empty; still listed in report |

---

## 10. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM invents features that don't map to reality | High | Prompt constraints: features must be grounded in a community + flows or explicit docs references; cite evidence per feature; ask the user to confirm via `features.yaml`. |
| Too many features surface — noise | Med | Default `--feature-limit 20`; salience ranking (community size × flow count × doc coverage). |
| Too few features — everything collapsed into "App" | Med | Minimum feature size floor; if the LLM proposes a single feature for a >200-node repo, re-prompt. |
| Overlap visualization gets unreadable | Med | Max N (configurable, default 8) overlapping bubbles per view; extras shown as "more features" chips; switch to table mode for large N. |
| `features.yaml` becomes stale after major refactor | Med | On run, validate every override references an existing node; stale references surface as warnings. |
| Feature boundaries unstable across re-runs as code changes | Med | Cache + stable ID scheme (§6.x in technical doc) anchor features to canonical node subsets; small code changes do not re-label. |
| Features cannot be defined until Feature 2 ships | N/A | We document Feature 2 as a dependency; the feature derivation degrades gracefully without flows but quality drops. |
| LLM cost per run | Low | One batched call per run; cached by content hash. |
| Sensitivity detection mis-flags (v1.1) | Med | v1 doesn't tag sensitivity. v1.1 will use an explicit allow/deny list and clearly mark tags as heuristic. |

---

## 11. Non-goals (explicit)

- **Ground-truth features.** Features are our *best guess* from available signals plus LLM synthesis. They are a draft; the user owns the authoritative `features.yaml`.
- **Replacing communities.** Leiden stays.
- **Replacing flows.** Feature 2 stays.
- **Replacing folders.** Feature 1 stays.
- **Cross-repo reasoning.**
- **Dynamic / runtime feature detection.**

---

## 12. Open questions (flagged for technical design)

1. Should features nest (sub-features)? Proposed: flat in v1; hierarchical in v1.1.
2. Where does the "Infrastructure" catch-all live? Proposed: emit a synthetic feature for unattributed but heavily-depended-on utilities, clearly tagged as infrastructure.
3. Should feature IDs be path-like (`feature:payments`) or hashed (`feature:a7c4`)? Proposed: human-readable slug derived from the canonical label, fallback to hash if the label is ambiguous.
4. Should the feature viewer support "expand all shared into their own mini-feature" mode? Potentially useful; design decision deferred.
5. Should features appear in Obsidian as community-note-style overview files? Proposed: yes in v1.1; adds one file per feature.
6. Should `GRAPH_REPORT.md`'s "Communities" section be replaced or complemented by "Features"? Proposed: keep both. Communities remain the topological lens; Features are the product lens.
7. What's the UX when `features.yaml` conflicts with LLM output? Proposed: human wins, warning logged.

---

## 13. Rollout plan

- **Phase 0 — Dependency confirmation.** Ensure Features 1 and 2 have shipped.
- **Phase 1 — Signal aggregation.** Gather communities, flows, folders, docs, god nodes into a single pre-LLM input structure.
- **Phase 2 — LLM synthesis + caching + overrides.**
- **Phase 3 — Feature-to-feature dependency derivation.**
- **Phase 4 — Dedicated viewer.**
- **Phase 5 — Cross-link integration** with structure + flow viewers.
- **Phase 6 — Docs + skill + changelog.**
- **Phase 7 — Default-on rollout** with `--no-features` opt-out.

---

## 14. Documentation touchpoints

- `README.md` — new bullet: "Feature hypergraph — capability-level groupings with shared-infrastructure overlap and feature-to-feature dependencies."
- `ARCHITECTURE.md` — new pipeline step: "synthesize_features" after report.
- `skill*.md` — CLI flags, new Step, artifact names.
- `CHANGELOG.md`.
- Translations.
- New: `docs/features.md` — how to read the feature view, how to edit `features.yaml`.

---

## 15. Glossary

- **Feature** — a named hypergraph over nodes representing a product-meaningful capability.
- **Role** — a participation category for a node within a feature: core, entry, terminal, shared, rationale, data.
- **Weight** — participation strength in (0, 1].
- **Orphan** — a node not assigned to any feature.
- **Dependency** — a directed edge between features derived from flows, cross-imports, and shared cores.
- **Sensitivity** (v1.1) — a heuristic tag indicating whether a feature handles PII, payments, secrets, or external integrations.
- **features.yaml** — the user's override file; always wins.
- **Ambiguous feature** — one where multiple plausible groupings of the same region were detected and none was definitively preferred.
