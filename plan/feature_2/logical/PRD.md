# Feature 2 — Flow Hypergraph (End-to-End Execution Flows)

**Document type:** Product Requirements Document (PRD)
**Audience:** Product, engineering leads, UX, doc writers
**Status:** Draft v1
**Scope note:** This PRD describes *what* and *why* only. No code, no APIs, no file layout. Technical design lives in `plan/feature_2/technical/TECHNICAL.md`.
**Depends on:** Feature 1 (Structure Graph) for hierarchical node kinds; can ship independently but is more useful when Feature 1 is present.

---

## 1. Summary

A codebase is most easily understood not as a pile of functions but as a set of **flows** — end-to-end chains of calls that begin at an entry point (an HTTP route, a CLI command, an event handler, a scheduled job, a `main()`) and terminate in a meaningful side effect or return. "The login flow," "the checkout flow," "the password-reset flow" are the mental models developers actually carry.

Today, dummyindex shows a semantic graph and (with Feature 1) a structural graph. Neither of these expresses flows. A user who wants to answer "walk me through what happens when a request hits `/api/login`" has to read `GRAPH_REPORT.md`, click around `graph.html`, and mentally reconstruct the call chain.

Feature 2 introduces the **Flow Hypergraph** — a new artifact pair (`flow_graph.json` + `flow_graph.html`) that enumerates every flow in the codebase as a first-class object. Each flow is a **hyperedge** that groups the files, classes, functions, and methods participating in one end-to-end execution path, along with the ordered sequence of calls that connects them.

The hypergraph property is essential. A single function — say `db.query()`, `auth.verify_token()`, or a shared validator — participates in **many** flows at once. A pairwise graph cannot express "this function belongs to the login flow *and* the API-request flow *and* the settings-update flow." A hyperedge can. Flows are allowed to overlap freely, and the viewer must make the overlap visible.

This feature is not about discovering semantic similarity. It is about tracing **what actually happens at runtime** using deterministic static analysis of the call graph, augmented by light-weight LLM naming once flows have been identified structurally.

---

## 2. Problem statement

### 2.1 What flows are today in dummyindex

Invisible. The existing `calls` edges can be traversed by a human with patience, but:

- There is no grouping: nothing in the output says "these 12 functions together constitute one flow."
- There is no ordering: the call graph is a set of pairwise edges; the sequence in which calls fire during one execution is implicit at best.
- There is no entry-point concept: every function is equal in the current graph; the viewer cannot surface "this function is where execution begins."
- There is no overlap highlighting: a shared utility appears as just another node with lots of edges; the viewer cannot say "this function shows up in 6 different flows."

### 2.2 Why a flow view is a different problem from what Feature 1 solves

Feature 1 (Structure Graph) answers **where code lives**. Feature 2 answers **how code runs**. A function lives in exactly one folder and one file, but it can participate in many flows. These are orthogonal dimensions. Folding them into one view produces either a tree that ignores runtime paths or a runtime graph that ignores physical location. Keeping them separate lets each answer its question well.

### 2.3 Why a hypergraph

A pairwise graph records "A calls B." Flows are not pairs; they are *sets* with an attached *ordering*. Expressing them as pairwise edges loses the grouping — which is the part users actually want.

Two concrete examples illustrate the limit of pairwise edges:

- **Shared-utility overlap.** `sanitize_input()` is called from `login()`, `register()`, `update_profile()`, and `submit_comment()`. In a pairwise graph it has four `calls` edges pointing at it. That tells the user the function is shared but not which **flows** it participates in, or whether those flows have anything else in common.
- **Cross-cutting branch.** Inside the checkout flow, there is a side branch for "if the user is new, trigger account creation." That branch re-enters the registration flow. A pairwise `calls` edge records that the checkout code calls the registration entry point, but cannot say "the checkout flow *contains* a transitively-nested registration sub-flow."

Hyperedges give us exactly one primitive for both: a flow is a named set of participating nodes, with optional internal sequence and optional nested sub-flows.

### 2.4 Why this is the right time to add it

dummyindex already has call-graph edges from every AST extractor (`ARCHITECTURE.md` — "call-graph second pass for INFERRED `calls` edges"). The hypergraph primitive is already supported by the export pipeline (hyperedges are stored on `G.graph["hyperedges"]` and round-trip through build/export). What is missing is (a) the derivation step that turns the call graph into flow hyperedges, (b) a dedicated viewer, and (c) light semantic labeling. None of these require new infrastructure.

---

## 3. Users and personas

### Persona A — New engineer tracing a bug
**Situation:** A customer reports a 500 error on password reset. The engineer has the stack trace but doesn't know which functions "own" that path.
**Need:** Show me, in order, every function that fires when `/api/reset-password` is hit, across all files.
**Value from feature:** A single-click view of the reset flow, ordered, colored by module. Finds the culprit function in seconds instead of tens of minutes of grepping.

### Persona B — Architect reviewing coupling
**Situation:** Asked to evaluate whether `auth/` is too tangled with the rest of the codebase.
**Need:** See which non-auth flows also call into auth, and how deeply.
**Value from feature:** The overlap list shows all flows that enter auth, with counts and entry points. A shared-utility heat map surfaces the auth functions that are most reused.

### Persona C — Test-coverage strategist
**Situation:** Deciding where to invest limited QA time.
**Need:** Identify the highest-value flows to cover — usually the ones that touch many shared components or cross the most module boundaries.
**Value from feature:** Each flow is ranked by a simple "impact" score (entry-point traffic, node count, cross-module spread). Coverage planning becomes "cover the top five flows" rather than "cover every branch."

### Persona D — AI coding assistant
**Situation:** A user asks "what does the upload flow do?"
**Need:** A structured, named object containing every file and function involved, in sequence, with confidence indicators.
**Value from feature:** The assistant answers from the flow object rather than re-deriving the call chain on the fly. Tokens saved; determinism gained.

### Persona E — Onboarding tech writer
**Situation:** Writing the "how the system works" section of the engineering handbook.
**Need:** A list of named flows with short descriptions, so the writer can pick the three or four to feature.
**Value from feature:** Direct output. LLM-generated flow descriptions become the first draft.

---

## 4. User stories

### 4.1 Primary stories (P0 — must ship in v1)

- **US-1** As a developer, after running dummyindex I have an artifact listing every identified flow with a human-readable name.
- **US-2** I can click a flow and see the ordered sequence of calls it contains, across files.
- **US-3** I can see which functions participate in which flows; a single function may show up in many flows (the hypergraph property).
- **US-4** I can hover any function in the structure or semantic graph and see the flows it is part of.
- **US-5** Each flow has an entry point (function or file) clearly marked.
- **US-6** Each flow has one or more terminal nodes (return, emit, HTTP response, DB write, external call) clearly marked.
- **US-7** I can filter flows by entry-point kind: HTTP route, CLI command, scheduled job, event handler, internal.
- **US-8** I can search flows by name or by any participant's label.
- **US-9** Re-runs of dummyindex on unchanged code produce the same set of flows with the same IDs.

### 4.2 Secondary stories (P1 — v1.1)

- **US-10** I can export a flow as a standalone diagram (SVG or Mermaid) for embedding in docs or PRs.
- **US-11** I can see a heat-map of shared nodes — functions that appear in many flows — with counts.
- **US-12** I can see *flow dependencies*: flow A "calls into" flow B when A's sequence transitions through B's entry point.
- **US-13** Flow names come from an LLM pass that reads entry points, docstrings, and neighboring comments. The names are reviewable and stable across re-runs on unchanged code.
- **US-14** Confidence: each flow carries `EXTRACTED` (entry point explicitly tagged), `INFERRED` (entry point heuristically identified), or `AMBIGUOUS` (competing candidates).

### 4.3 Tertiary stories (P2 — later)

- **US-15** I can merge or split flows manually via a companion `flows.yaml` that dummyindex respects on future runs.
- **US-16** I can see per-flow metrics (fan-out, depth, external-I/O count, number of languages crossed).
- **US-17** I can simulate the impact of deleting a function — which flows break, which degrade.
- **US-18** Flows cross-reference Feature 3 features: "this flow implements the Billing feature."

---

## 5. Scope

### 5.1 In scope for v1

- **Entry-point detection** across supported languages and common frameworks.
- **Flow derivation** via deterministic call-graph traversal.
- **Flow naming** via a single bounded LLM call per run, with caching.
- **Flow hyperedges** added to the graph's hyperedge list, carrying entry, exits, ordered sequence, participants.
- **A new data artifact** (`flow_graph.json`) with the flow list and the nodes/edges they reference.
- **A new interactive viewer** (`flow_graph.html`) with a flow list on the side and the selected flow as a directed sequence.
- **Cross-references from the semantic graph and the structure graph**: each node's info panel shows the flows it belongs to and links to the flow viewer.
- **Report integration**: `GRAPH_REPORT.md` gains a "Flows" section summarizing the top flows.

### 5.2 Out of scope for v1

- **Runtime instrumentation.** No profiling, no tracing, no log ingestion. Everything is derived from static analysis.
- **Control-flow analysis.** We do not model `if`/`else` branches, loops, early returns. A flow is a set of call edges with a sequence derived from source order, not a CFG.
- **Dynamic dispatch resolution beyond what the existing extractor supports.** Where the call graph is uncertain, we mark flows `AMBIGUOUS`.
- **Test coverage / code coverage overlays.**
- **Cross-process flows** (e.g. service A → Kafka → service B). One repo, one process.
- **Mutation of source** (no refactors, no code-generation).
- **Feature 3 (feature hypergraph).** Separate PRD.

---

## 6. Logical model

### 6.1 Entry points

An **entry point** is a function or file that can be invoked from outside the running program.

Canonical entry kinds:

| Kind | Examples |
|------|----------|
| HTTP route | `@app.route`, Flask blueprints, Express `app.get`, FastAPI `@app.post`, Django `urls.py`, Rails routes, Spring `@RequestMapping`, Go `http.HandleFunc` |
| CLI command | Click `@cli.command`, argparse parsers, Cobra commands, Commander.js, Rust `clap` derive, Python `__main__`, Node `bin` scripts |
| Scheduled job | Cron configs, Celery `@task`, AWS Lambda handler, GitHub Actions workflow steps |
| Event handler | DOM `addEventListener`, message queue consumers, Kafka subscribers, Django signals, Rails callbacks, Spring `@EventListener` |
| Test entry | pytest `def test_…`, JUnit `@Test`, Go `Test*`, Jest `test()`/`it()` |
| Library export | Public functions exported from package entry points (`__init__.py`, `index.ts`, `lib.rs` pub) |
| Internal entry | Any function that is never called from inside the repo but *is* imported — likely a library boundary |

Not every entry kind is equally useful for flow naming. v1 ranks entry points by "flow salience": HTTP and CLI beat test entries, which beat library exports.

### 6.2 What a flow is

A flow is a named, ordered set of node IDs that:

1. Begins at an entry point.
2. Extends along `calls` edges (transitively, up to a configurable depth bound).
3. Terminates at one or more terminal nodes (return, emit, external I/O, or a bounded recursion cut-off).
4. Carries a sequence — a list of (from, to) pairs in an order derived from a traversal strategy (see §6.5).

A flow may include:

- Functions, methods, and classes.
- Files (implicit, derived from participants' parents).
- Global variables that are *read or written* along the path.
- Nested sub-flows (another flow re-entered mid-sequence).

A flow may not include:

- Unreachable code from the entry point.
- Dead branches (v1: static reachability only, not CFG-based).

### 6.3 Hypergraph semantics

Each flow is a single hyperedge. Two flows may share any subset of their nodes. A node's "flow membership" is the set of flow IDs whose hyperedge contains it. The viewer must render this explicitly — for any selected node, show the count and list of flows it belongs to.

### 6.4 Terminal conditions

A traversal terminates when it reaches:

- A function with no outgoing `calls` edges (pure leaf).
- An I/O-like call: database, HTTP client, logging, filesystem, cache, message queue. Detected by name heuristics per language.
- A return statement in the source (treated as a synthetic terminal).
- The configured maximum depth (default: 10 hops).
- A node already in the flow's visited set (cycle break).

### 6.5 Sequence derivation

Given the entry point, traversal order is:

- **Source-order first, topological-sort second.** Within a single function body, calls are visited in the order they appear in source. Across functions, the traversal is DFS, producing a stable linearization.
- Edges that form a cycle are truncated; the first occurrence wins.
- If the same function is reached via multiple paths, the *first* path in source order is the canonical sequence; alternate paths are recorded as "alt-paths" metadata.

Source-order DFS yields a deterministic, human-legible sequence that matches how a reader walks the code.

### 6.6 Flow granularity

Two flows that share >95% of their nodes are merged. Two flows with distinct entry points but full sequence equivalence are merged with both entry points attached. Below that threshold they remain distinct.

### 6.7 Flow confidence

Each flow inherits the minimum confidence of its member `calls` edges:

- `EXTRACTED` — every edge is directly observed in source.
- `INFERRED` — at least one edge is a call-graph inference (e.g. dynamic dispatch, method-name matching across files).
- `AMBIGUOUS` — at least one edge is flagged ambiguous.

Users can filter by confidence.

### 6.8 Flow naming

An LLM pass proposes a 2–5-word name per flow, using:

- The entry point's function name, file, and docstring.
- The labels of the top three most-central nodes in the flow.
- Any inline rationale comments dummyindex already extracts.

Names are cached by a content hash of the above inputs so re-runs on unchanged code produce stable names. Users can override names via `dummyindex-out/flows.yaml`.

---

## 7. Interaction model

The viewer provides:

- **Flow list sidebar** with name, entry kind, participant count, confidence chip, and a count of overlapping flows. Sortable by entry kind, participant count, confidence, or overlap.
- **Selected flow canvas** showing an ordered top-to-bottom or left-to-right sequence of calls. Entry node pinned at origin; terminals pinned at the far side. Nodes outside the selected flow are dimmed.
- **Overlap panel** listing the other flows that intersect the selected flow, with counts of shared nodes.
- **Search** across flow names and participant labels. Matching flows jump to the top of the list.
- **Filter bar** for entry kind, confidence, node count, whether the flow crosses module boundaries.
- **Node info panel** reused from the existing viewer, extended with "Flows this node appears in."
- **Cross-links**: "Open in structure graph" / "Open in semantic graph" buttons for the currently highlighted nodes.

---

## 8. Success criteria

- **SC-1 (Coverage)** On a typical web-service corpus, every public HTTP route becomes an entry point and yields a named flow.
- **SC-2 (Correctness)** A flow's sequence never contains an edge that is not also present in the underlying `calls` edge set of the graph.
- **SC-3 (Overlap correctness)** For a representative corpus, the set of (node, flow) memberships matches a hand-audited reference on a chosen 10-flow fixture.
- **SC-4 (Determinism)** Running dummyindex on unchanged code produces the same flow IDs and the same sequences.
- **SC-5 (Naming stability)** LLM-produced names are stable across re-runs when inputs are unchanged, by virtue of content-hash caching.
- **SC-6 (Performance)** Flow derivation adds less than 15% to pipeline wall-clock on a 500-file repo. Viewer first paint under 3 s.
- **SC-7 (No regressions)** All existing tests pass; `graph.json`, `graph.html`, Obsidian outputs unchanged except for an additive hyperedge section.
- **SC-8 (Human audit)** On the existing `worked/` corpora, at least 80% of generated flows are judged "meaningful" by a human reviewer. "Meaningful" means: has a named entry, terminates sensibly, participants make sense together.

---

## 9. Acceptance criteria

| # | Scenario | Expected |
|---|----------|----------|
| AC-1 | Single Flask app with two routes | Two flows, each rooted at the route handler |
| AC-2 | CLI app with three commands | Three flows, each rooted at its command handler |
| AC-3 | Utility function called by three routes | The utility appears in three flow hyperedges |
| AC-4 | Recursive function within one flow | Recursion terminates at depth bound; sequence logs a cycle break |
| AC-5 | Flow with no calls (entry point body is one line) | Flow exists, has entry, has one terminal (the entry itself) |
| AC-6 | Cross-language repo (Python backend + JS frontend) | Each language contributes its own entry-point detection; flows stay within one language in v1 |
| AC-7 | Flow naming runs once, second re-run uses cache | No new LLM call; names identical |
| AC-8 | User overrides a flow name in `flows.yaml` | Override wins and is preserved in the artifact |
| AC-9 | Ambiguous dispatch (duck-typed call to one of three implementations) | Flow marked `AMBIGUOUS`; all three candidates recorded as alt-paths |
| AC-10 | Two flows with ≥95% node overlap | Merged into one flow with both entry points listed |
| AC-11 | `--no-flows` flag passed | No `flow_graph.{json,html}` emitted; existing outputs unchanged |
| AC-12 | Flow hyperedge appears in `graph.json` as well | Yes — added to `G.graph["hyperedges"]` so the semantic viewer can shade it |
| AC-13 | Node info panel in structure viewer | Lists flows this node is in, with clickable links to the flow viewer |
| AC-14 | Search "login" in flow viewer | Matches `login_flow` by name *and* any flow containing a node labeled `login` |
| AC-15 | Large repo with >200 detected entry points | Flow count capped (default 100 top-ranked); others available via `--flow-limit N` |

---

## 10. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Too many flows drown the user | High | Default cap at 100 flows ranked by salience (entry kind × participant count). Expose `--flow-limit`. |
| Duplicate/near-duplicate flows add noise | Med | 95% overlap merge rule; alt-entry-point merging. |
| Dynamic dispatch produces wrong flows | Med | Mark as `AMBIGUOUS`, record alt-paths, do not silently pick one. |
| LLM naming is unstable across runs | Med | Cache names by content hash; expose override YAML. |
| Entry-point detection misses framework-specific patterns | Med | Ship a per-framework detector registry; document extension points; fall back to "internal entry" for any function with zero in-degree. |
| Very large flows become unreadable | Low | Max-depth clamp; "expand deeper" toggle in viewer for interactive drilling. |
| Flows conflate unrelated sub-traversals | Med | Source-order DFS with cycle-break; not global merging. Clear boundaries. |
| Cross-language flows hidden | Low | v1 documents that flows stay per-language. Cross-language flow unification is v2. |
| Hyperedge bloat in `graph.json` | Low | Flows live in both `graph.json` and `flow_graph.json`; keep references, not duplicated node payloads. |

---

## 11. Non-goals (explicit)

- Runtime correctness. A flow is a *plausible* execution path, not a proven one.
- Guarantees about paths taken under specific inputs.
- Exhaustive enumeration of all possible execution paths. We name **canonical** flows.
- Full semantic disambiguation of dynamic dispatch. We record ambiguity; we do not resolve it.

---

## 12. Open questions (for technical design)

1. Should flows be stored inside `graph.json`'s existing `hyperedges` array, or only in `flow_graph.json`? Recommended: both. The `graph.json` copy is a thin reference (id, label, confidence, node list) so downstream tooling sees them; `flow_graph.json` carries the full sequence metadata.
2. How do we represent the sequence? Ordered list of edge IDs, or ordered list of (from, to) tuples? Punt to technical doc.
3. Should flows cross process boundaries if the user's repo contains two services? Out of scope v1.
4. Should we support user-authored flow definitions (reverse direction: user declares a flow in YAML, dummyindex validates)? Desired for v1.1; not required v1.
5. What is the LLM budget per flow? Recommendation: one batched call per run, grouping all unnamed flows in one prompt, yielding structured JSON.
6. Should the viewer support "replay" animation (highlighting the sequence one hop at a time)? Nice-to-have; not required for v1.

---

## 13. Rollout plan

- **Phase 0 — Schema**: hyperedge schema extensions documented; no behavior change.
- **Phase 1 — Deterministic detection**: entry-point detection + call-graph traversal + flow emission. No LLM naming yet; flows carry provisional names (e.g. `flow:auth_login_route`).
- **Phase 2 — LLM naming + caching**.
- **Phase 3 — Dedicated viewer**.
- **Phase 4 — Cross-reference integration** with semantic + structure viewers.
- **Phase 5 — Docs, CHANGELOG, skill.md variants**.
- **Phase 6 — Default-on** with opt-out flag.

---

## 14. Documentation touchpoints

- `README.md` — new bullet under "What you get": "Flow hypergraph — named end-to-end flows, with overlap detection."
- `ARCHITECTURE.md` — pipeline diagram gains a "synthesize_flows" step after `build_graph`.
- `dummyindex/markdown/skill.md` + platform variants — new CLI flags and a Step for flow synthesis.
- `CHANGELOG.md` — feature entry.
- Translations to follow per existing policy.

---

## 15. Glossary

- **Flow** — a named, ordered, end-to-end set of calls from an entry point to one or more terminals.
- **Entry point** — a function or file that is invokable from outside the process (HTTP route, CLI command, event handler, scheduled job, test, library export).
- **Terminal** — the node at which a traversal stops: leaf function, I/O call, depth-bound, or cycle.
- **Sequence** — the ordered list of call edges that constitutes a flow, derived by source-order DFS.
- **Alt-path** — an alternate route from entry to terminal that was detected but not taken as canonical.
- **Overlap** — the set of nodes shared between two flows. Central to the hypergraph framing.
- **Salience** — a flow's ranking score, computed from entry kind and participant count; used to pick the top N shown by default.
- **Flow hyperedge** — the single hyperedge representing one flow; stored in `G.graph["hyperedges"]`.
