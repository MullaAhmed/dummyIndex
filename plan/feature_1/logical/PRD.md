# Feature 1 — Structure Graph (Folder → File → Class → Function/Global)

**Document type:** Product Requirements Document (PRD)
**Audience:** Product, engineering leads, UX, doc writers
**Status:** Draft v1
**Scope note:** This PRD describes *what* and *why* only. No code, no APIs, no file layout. Technical design lives in `plan/feature_1/technical/TECHNICAL.md`.

---

## 1. Summary

Today, graphify produces a single force-directed semantic graph clustered by Leiden community detection. That graph is excellent for answering "what concepts connect across my corpus?" but it is **not a structural map of the codebase**. A developer who wants to answer "where does `PaymentService.charge()` live, and what else lives near it?" has to read the file tree and the graph separately.

Feature 1 adds a second, complementary graph artifact — the **Structure Graph** — that renders the codebase as a top-down, collapsible hierarchy rooted at the input directory. Folders nest inside folders, files nest inside folders, classes nest inside files, and methods/functions nest inside classes (or directly inside files when they are module-level). The *leaves* of this tree are the atomic units of the codebase: top-level functions, methods, and module-level global variables.

On top of this hierarchy, we overlay the same *lateral* relationships that the current graph shows — `calls`, `imports`, `inherits`, `uses`, `references_constant`, etc. — so the developer can simultaneously see **where** code lives (hierarchy) and **how** it talks to the rest of the system (cross-edges).

This is not a replacement for the existing graph; it is a second lens on the same underlying data. Both artifacts coexist and are generated from the same extraction pass.

---

## 2. Problem statement

### 2.1 What users currently do

When a developer opens a graphify output for an unfamiliar codebase:

1. They read `GRAPH_REPORT.md` to learn the god nodes and communities.
2. They open `graph.html` to see the semantic cluster layout.
3. They open their file tree (IDE, `tree`, GitHub) **separately** to understand the physical layout.
4. They mentally correlate "this cluster" ↔ "this folder" ↔ "this file" — a reconciliation the tool does not perform for them.

Step 4 is where the existing product leaks value. Two files in the same folder may live in different communities; two files in different communities may be architecturally siblings; a god node may turn out to be a utility shared across five folders and the user has no visual evidence of that until they click into each file.

### 2.2 What the existing graph does not answer

- "Show me every function in `src/auth/`."
- "Collapse this package — I only want to see its public surface from outside."
- "What other parts of the codebase call anything inside `src/auth/`?"
- "Which file contains the 3 methods involved in this cross-community edge?"
- "Is there a global variable in this module that everything else depends on?"
- "Hide everything except the classes — show me the type hierarchy only."

These are **structural** questions. The current graph is organized by edge density, not by physical containment, and cannot answer them.

### 2.3 Why a second graph rather than fixing the first

The existing force-directed graph optimizes for **semantic proximity** — nodes that interact pull toward each other regardless of file/folder. That property is exactly what makes it useful for finding surprising cross-cutting concerns. Forcing it to also respect folder containment would either (a) break its semantic layout or (b) produce a hybrid that does neither job well.

A second graph, generated from the same extraction dict, lets each view specialize. Users switch between them the way IDEs switch between "package view" and "call hierarchy view."

---

## 3. Users and personas

### Persona A — New-team engineer (Onboarding)
**Situation:** Just joined a team, has two weeks to become productive in a 200-file Python service.
**Need:** A map of the codebase they can navigate top-down, collapsing areas they don't yet need, expanding the ones they do.
**Value from feature:** Fastest path from "repo URL" to "mental model of the code." They collapse everything, then drill into `api/`, then into `api/routes/`, then into a single file, then into a single method. At each step, cross-edges show them what else that unit touches.

### Persona B — Reviewing architect
**Situation:** Asked to audit an unfamiliar codebase for coupling, layering violations, or shared global state.
**Need:** See the physical structure and overlay cross-cutting relationships to spot "this leaf function in `utils/` is called by 40 other places."
**Value from feature:** Immediate visual identification of cross-folder coupling; detection of inappropriate inheritance across module boundaries; flagged globals.

### Persona C — AI coding assistant (Claude / Codex / Gemini / Aider, etc.)
**Situation:** Consuming the graph programmatically to answer a user question.
**Need:** Structured, hierarchical node metadata that can be walked deterministically to build a focused context window.
**Value from feature:** A `structure_graph.json` with explicit `node_kind` and `parent` fields gives the assistant a stable backbone for "give me all functions in this folder" without having to reconstruct the hierarchy from `contains` edges.

### Persona D — Technical writer / doc author
**Situation:** Producing or updating architecture documentation.
**Need:** An accurate, exportable hierarchical diagram — SVG or similar — that reflects the actual code layout.
**Value from feature:** Static SVG export of the hierarchy at a chosen depth, usable in PRs, wikis, and `ARCHITECTURE.md` updates.

---

## 4. User stories

**Numbered for traceability. Each story becomes one or more acceptance tests.**

### 4.1 Primary stories (P0 — must ship in v1)

- **US-1** As a developer, I can run graphify on a folder and, in addition to the existing `graph.html`, I get a second artifact showing my codebase as a top-down tree.
- **US-2** I can see folder nodes, file nodes, class nodes, and function/method nodes, each visually distinct, so that I can tell them apart at a glance.
- **US-3** I can click any non-leaf node to collapse its descendants; clicking again expands them.
- **US-4** When a subtree is collapsed, any cross-edges that originate or terminate inside the collapsed subtree are **lifted** to the visible ancestor so I don't lose information.
- **US-5** I can see cross-edges (calls, imports, inherits, etc.) rendered differently from hierarchy edges, so I can visually distinguish "this function is inside this file" from "this function calls that function."
- **US-6** I can click any node and see the same info panel the existing graph shows (label, source file, source location, degree, community).
- **US-7** I can search the structure graph by label or path substring, and matching nodes are highlighted with their ancestors expanded automatically.
- **US-8** The structure graph is deterministic — running graphify twice on the same input produces the same structure graph.

### 4.2 Secondary stories (P1 — v1.1)

- **US-9** I can see module-level global variables as leaf nodes, distinguishable from functions.
- **US-10** I can filter cross-edges by relation type (only `calls`, only `imports`, etc.).
- **US-11** I can filter cross-edges by confidence (hide `INFERRED` / `AMBIGUOUS`).
- **US-12** I can export the visible (post-collapse) state as an SVG snapshot.
- **US-13** The graph respects `.graphifyignore` so I don't see folders I've excluded.

### 4.3 Tertiary stories (P2 — v1.2 and beyond)

- **US-14** I can pin a node so it remains expanded during "collapse all."
- **US-15** I can see per-node metrics (fan-in, fan-out, incoming cross-edge count) on hover.
- **US-16** I can toggle a "public surface only" mode that hides private members (language-dependent: `_` prefix in Python, `private` in Java/TS, unexported identifiers in Go, etc.).
- **US-17** When multiple languages coexist in one folder, I can filter by language.

---

## 5. Scope

### 5.1 In scope for v1

- **Hierarchy derivation** from the input root, walking up parent folders until the root.
- **Node kinds** added to the extraction schema: folder, file, class, function, method, global variable.
- **Containment edges** expressed uniformly so a consumer can rebuild the tree without language-specific knowledge.
- **Cross-edges preserved** exactly as the existing graph records them, with no re-labeling.
- **A new interactive viewer** (`structure_graph.html`) rendered hierarchically top-to-bottom with collapsible nodes.
- **A new data artifact** (`structure_graph.json`) that embeds the hierarchy and the overlaid cross-edges in one document.
- **A new CLI flag** to enable/disable structure-graph generation.
- **Cache and determinism** guarantees equivalent to the existing pipeline.
- **Documentation** updates: `README.md`, `ARCHITECTURE.md`, `skill.md` family, `CHANGELOG.md`.

### 5.2 Out of scope for v1

- **Runtime / dynamic call graphs** (we stay deterministic-AST-only).
- **Test coverage overlays.**
- **Per-commit diff views** ("what changed in this PR in the structure?").
- **Cross-repo hierarchies** (only one input root per run, same as today).
- **Writing back to source** (no refactor tool; read-only view).
- **3D layouts, WebGL, or GPU-accelerated rendering.** Keep vis.js as the renderer to match the existing graph.
- **Feature 2 (flow hypergraph)** and **Feature 3 (feature hypergraph)** — those are separate PRDs.

---

## 6. Logical model

### 6.1 The hierarchy

Reading top to bottom:

1. **Root folder** — the directory passed to `/graphify`.
2. **Descendant folders** — every directory between the root and each extracted file, inclusive.
3. **Files** — each source file that graphify's detector classified as extractable.
4. **Classes** — every class-like construct found by the AST extractor (Python `class`, TS/JS `class`, Go `type … struct`, Rust `struct`/`enum`/`trait`, Java `class`/`interface`, etc.).
5. **Functions / methods** — every top-level function (parented by a file) and every class member (parented by a class).
6. **Global variables** — every module-level named binding that is neither a class nor a function.

Nothing below a function is materialized in the graph. Local variables, nested functions, lambdas, and statements are **not** nodes in the structure graph. The leaves are always one of: function, method, or global.

### 6.2 Containment rule (the one invariant)

Every non-root node has **exactly one** structural parent.
The parent is:

| Node kind | Parent kind |
|-----------|-------------|
| folder | folder (or none, for the root) |
| file | folder |
| class | file (or another class, for nested classes) |
| function | file |
| method | class |
| global | file |

Any edge in the structure graph whose `relation` is the containment relation obeys this rule. Every other edge (`calls`, `imports`, `inherits`, `uses`, `references_constant`, `semantically_similar_to`, …) is a **cross-edge** and is allowed to cross any hierarchy boundary.

### 6.3 Cross-edges

Cross-edges are identical in semantics to the existing graph. We do not invent new relations. We do not drop existing relations. The structure graph is a *rendering* of the same edge set, grouped by a different organizing principle.

### 6.4 Collapse / expand semantics

A node is **collapsed** when the viewer hides all of its descendants. A collapsed node is drawn as a single unit and typically shown with a count ("src/auth/ [12]").

When a subtree is collapsed:

- **Hierarchy edges** inside the subtree are hidden (they are implied by the collapse visual).
- **Cross-edges** with at least one endpoint inside the subtree are **lifted**: the endpoint inside the subtree is redrawn as pointing to the collapsed ancestor. If multiple cross-edges now map to the same ancestor pair, they are **aggregated** into a single rendered edge carrying a count and a dominant relation.
- **Cross-edges fully inside the subtree** (both endpoints inside the same collapsed subtree) are hidden — by definition, they describe internal structure the user chose not to see.

The user can always undo this by expanding.

### 6.5 The default view

On first open, the structure graph shows:

- All folders expanded down to the file level.
- All files collapsed (so classes, functions, methods, and globals are hidden under each file).
- Cross-edges lifted to file-level aggregates.

Rationale: this gives the fastest "mental map" — the user sees the physical layout and the inter-file coupling at a glance. Drilling into a specific file is one click away.

---

## 7. Interaction model (logical; concrete UX lives in TECHNICAL.md)

The viewer must support:

- **Click to expand / collapse** a non-leaf node.
- **Shift-click** or a dedicated toolbar button to "expand all descendants" / "collapse all descendants."
- **Search** that highlights matches and auto-expands their ancestors.
- **Hover** to preview label, kind, source file, source location, degree, and community.
- **Select** to inspect in a side panel, as the existing graph does.
- **Legend** explaining node shapes/colors (by kind) and edge styles (by relation/confidence).
- **Toolbar** toggles: show/hide cross-edges, filter by relation, filter by confidence, expand all, collapse all, reset view.

Keyboard behavior is desirable (arrow keys to walk siblings, enter to expand) but not required for v1.

---

## 8. Success criteria

The feature is successful if all of the following hold:

- **SC-1 (Adoption)** On a representative corpus (e.g. the existing `worked/karpathy-repos/` example, or a 200-file project), opening `structure_graph.html` reveals the folder tree correctly to a reader who has never seen the project.
- **SC-2 (Correctness)** Every file present in the extracted set appears in the structure graph. No file is orphaned.
- **SC-3 (Containment correctness)** For every non-root node, walking its parent chain reaches the root. No cycles, no orphans.
- **SC-4 (Cross-edge preservation)** The set of cross-edges in `structure_graph.json` equals the cross-edge set in `graph.json`. Neither is a superset.
- **SC-5 (Collapse lifting correctness)** On a fixture with two files each containing a function, with a call from one to the other, collapsing either file produces exactly one aggregated cross-edge; collapsing both produces one inter-file aggregated cross-edge.
- **SC-6 (Determinism)** Running on the same input twice produces byte-identical `structure_graph.json` (after normalizing timestamps).
- **SC-7 (No regressions)** All existing tests pass. `graph.html`, `graph.json`, `GRAPH_REPORT.md`, and the Obsidian vault are unchanged.
- **SC-8 (Performance)** On a 500-file repo, generation adds less than 20% to total pipeline wall-clock time. The viewer loads in under 3 seconds in a modern browser at the default view.
- **SC-9 (AI-assistant compatibility)** A coding assistant given only `structure_graph.json` can answer "list all functions under `src/auth/`" via a deterministic tree walk — no ambiguity, no per-language knowledge required.

---

## 9. Acceptance criteria (test matrix)

Every row below must pass before v1 ships. Concrete fixtures live in `tests/fixtures/`.

| # | Scenario | Expected result |
|---|----------|-----------------|
| AC-1 | Single file, one class, one method, one top-level function | Graph has 4 nodes (file, class, method, function) + root folder |
| AC-2 | Nested folders `a/b/c/file.py` | Structure contains folder `a/`, folder `b/` parented by `a/`, folder `c/` parented by `b/`, file parented by `c/` |
| AC-3 | Two files in the same folder, one calling a function in the other | Cross-edge is `calls` between function nodes; after collapsing both files, one aggregated cross-edge exists between the two file nodes |
| AC-4 | Python module with `API_KEY = "abc"` at top level | Global node `API_KEY` is a leaf, parented by the file |
| AC-5 | JavaScript module with `export const FOO = 1;` | Global node `FOO` is a leaf, parented by the file |
| AC-6 | Class with nested class | Inner class is parented by outer class, not by the file |
| AC-7 | Empty folder (no extractable files) | Folder node is **not** emitted (no orphan leaves) |
| AC-8 | `.graphifyignore` excludes `vendor/` | No folder or file node under `vendor/` appears |
| AC-9 | Corpus above `MAX_NODES_FOR_VIZ` | Generation falls back to JSON-only, viewer emits a friendly "too large" message |
| AC-10 | Run with `--no-structure` flag | Neither `structure_graph.html` nor `structure_graph.json` is produced; existing outputs unchanged |
| AC-11 | Two sibling folders each containing a `utils.py` | Both files present, parented by their respective folders, no ID collision |
| AC-12 | Monorepo with mixed Python and TypeScript | Both languages produce nodes; node kind is independent of language |
| AC-13 | Symlink pointing at a folder inside the root | Resolved per existing `collect_files` policy; no infinite loop |
| AC-14 | Re-run after editing one file | Cache is honored for unchanged files; new globals in the edited file appear |
| AC-15 | Search for `charge` in a fixture containing `PaymentService.charge` | The `charge` node is highlighted; its ancestors up to the root are auto-expanded |

---

## 10. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Global-variable extraction is noisy — every `_tmp = 0` becomes a node | Med | Document per-language filters (e.g. skip single-underscore-prefixed names, skip magic `__all__` unless it has value, skip names that start with `_` in Python top-level). Offer a `--strict-globals` flag if needed. |
| Cache invalidation: old cache entries lack globals | Med | Bump the extraction schema version; cache loader refuses to read entries below the new version, forcing re-extract of affected files only. |
| Deep monorepos produce thousands of folder nodes | Med | Default view collapses all files; the hierarchy is still browsable; same 5k-node hard cap applies. Oversized corpora get JSON only. |
| Label collision when two files share a short label (`utils.py`) | Low | Node IDs are path-based and unique; labels may be decorated with their parent folder in display when disambiguation is needed. |
| Cross-edge lifting produces misleading aggregates | Med | Always show the count on aggregated edges and let the user hover to see the component edges. |
| Users confuse the two HTML files | Low | Clear titles in the `<title>` tag and a visible header band; link between them from each sidebar. |
| Performance degrades on very large cross-edge sets | Low | Rendering is capped to the default-view edge set (file-level aggregates); deeper expansion is user-triggered. |
| Language-specific extractor bugs produce bad leaves | Med | Per-language unit tests (one fixture per supported language) validate that expected leaf counts appear. |

---

## 11. Non-goals (explicit)

- **We do not** build a new clustering algorithm for the structure graph. Community coloring, if shown, reuses the existing Leiden output.
- **We do not** attempt to infer "logical" groupings beyond what the filesystem already expresses. A folder is a folder.
- **We do not** add a server. Everything remains a static file in `graphify-out/`.
- **We do not** ship a theme switcher, a dark/light toggle, or a multi-language UI in v1. The viewer's chrome inherits the dark theme of the existing `graph.html`.
- **We do not** promise feature parity with IDE outlines (symbol kinds like "decorator," "enum variant," "trait impl"). v1 resolves to: folder / file / class / function / method / global. Finer distinctions can be added later.

---

## 12. Open questions (flagged for the technical design)

1. Should folder nodes carry any metadata beyond name and path (e.g. aggregate LOC, file count)? Decision punted to technical design.
2. Should the structure graph be emitted even when `--no-viz` is set, as JSON only? Recommended yes — it's cheap and useful for AI assistants.
3. Should cross-edges from external modules (e.g. `imports stdlib.X`) be shown at all in the structure view? Recommended: hidden by default, toggleable on.
4. For `__init__.py` in Python, should the file node carry the package label instead of the file name? Recommended: label the file as `__init__.py` but have the *folder* inherit the package docstring for the hover tooltip.
5. For languages where a single file declares multiple top-level siblings (e.g. Rust mod files, Go `package` files across multiple `.go`), does each file remain a distinct node? Recommended: yes — the filesystem wins; semantic packaging is out of scope.
6. Should collapse state persist across page reloads (localStorage)? Recommended: yes, keyed by output path.

---

## 13. Rollout plan (logical)

- **Phase 0 — Preparation.** Update schema documentation (`ARCHITECTURE.md`, validate schema). Announce the schema bump in `CHANGELOG.md` so downstream consumers of `graph.json` are not surprised.
- **Phase 1 — Silent enablement.** Structure graph generated but disabled by default; enabled with `--structure`. Gather internal feedback on representative corpora.
- **Phase 2 — Default-on.** Flip the default; keep `--no-structure` as an escape hatch.
- **Phase 3 — Deprecation candidates.** None planned. This feature is purely additive.

Each phase ends with a checklist: tests green, docs updated, `skill.md` variants updated, `CHANGELOG.md` line added.

---

## 14. Documentation touchpoints

When this feature ships, the following user-facing documents must be updated:

- `README.md` — new `What you get` bullet: "Structure graph: hierarchical, collapsible view of your codebase with lateral relationships overlaid."
- `ARCHITECTURE.md` — new `structure_graph` artifact described; pipeline diagram gains a second output fork after `export()`.
- `graphify/markdown/skill.md` and every platform variant (`skill-codex.md`, `skill-opencode.md`, …) — CLI flag surfaced; output filenames documented.
- `CHANGELOG.md` — feature entry under the next release.
- Translated READMEs under `docs/translations/` — update alongside the English README per existing policy.

---

## 15. Glossary

- **Structure graph** — the new artifact introduced by this feature.
- **Original graph** / **semantic graph** — the existing force-directed graph produced today.
- **Hierarchy edge** — an edge that expresses physical containment (folder→folder, folder→file, file→class, class→method, file→function, file→global).
- **Cross-edge** — any edge that is not a hierarchy edge: `calls`, `imports`, `inherits`, `uses`, `references_constant`, `semantically_similar_to`, `rationale_for`, etc.
- **Lifting** — the act, during rendering, of rerouting a cross-edge endpoint that lives inside a collapsed subtree to the visible ancestor that represents it.
- **Aggregated edge** — a rendered edge that represents multiple underlying cross-edges sharing the same (ancestor, ancestor) pair after lifting.
- **Leaf / unit element** — a node with no structural children: function, method, or global variable.
