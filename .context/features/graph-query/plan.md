# Symbol-graph query verbs — plan

confidence: INFERRED

## Bounded context

This feature is the **read side of the full extracted symbol graph** — the node-link artifact the curated codebase scan deliberately keeps off-screen (on this repo: ~11.7 MB, 6,778 nodes, 19,460 links). It answers relational questions (`callers-of` … `community`) that the token-overlap **context-query** feature cannot: context-query ranks *features by text*, graph-query walks *edges between symbols*. It owns no writes, no clustering, no LLM — it is a pure consumer of `features/symbol-graph.json` (and optionally `features/graph-communities.json`), delivered as proposal `graph-consumption-upgrade` item A1.

The boundary is one wire-only CLI module plus a domain package, split along the repo's CLI/domain rule (`.context/conventions/folder-organization.md`, "The CLI / domain split"):

- `dummyindex/cli/graph.py` (184 lines) — flag parsing, verb dispatch, exit-code mapping; imports the domain lazily inside `run()` (`cli/graph.py:25-46`).
- `dummyindex/context/domains/graph_query/` — the engine, as a package.

**Why a package, not one module:** the domain-split convention (`folder-organization.md`, "How a domain directory is split") mandates canonical concern files once a domain outgrows one file, and the repo's file-size norm caps modules well below what a single-file version would be (~1,019 lines of domain code; `verbs.py` alone is 456). The split keeps closed alphabets, models, errors, and behavior in their canonical homes; privacy is the package boundary — `__init__.py` re-exports the entire public surface (`__init__.py:61-90`) and no filename carries an underscore.

File map:

- `constants.py` (16 lines) — tunables (`DEFAULT_LIMIT=20`, `DEFAULT_DEAD_CODE_LIMIT=50`, `DEFAULT_IMPACT_DEPTH=2`, `DEFAULT_NEIGHBOR_HOPS=1`, `MAX_CANDIDATES_LISTED=10`, `DOCSTRING_CLIP_CHARS=120`) + wire vocabulary (`FILE_TYPE_RATIONALE`/`FILE_TYPE_CODE`, `COMMUNITIES_ARTIFACT`, `SCHEMA_VERSION=1`).
- `enums.py` — closed alphabets: `GraphRelation` (the artifact's seven relations), `DEPENDENCY_RELATIONS`, `GraphVerb`, `EdgeDirection`.
- `errors.py` — typed hierarchy rooted at `GraphQueryError`; artifact errors carry the path, resolution errors carry the query (+ cited candidates).
- `models.py` — frozen `GraphRow`/`GraphQueryResult` (wire via `to_dict`, optional-means-absent via `_put`, `models.py:12-15`) + the `SymbolGraph` carrier.
- `load.py` — artifact → `SymbolGraph` (see below).
- `resolve.py` — user string → node id (id / bare name / `path:name` suffix / prefix).
- `verbs.py` — the seven verbs + row/result helpers; `_result` clips to `max(1, limit)` so a domain caller can never request zero rows (`verbs.py:94`).
- `render.py` — `render_markdown` / `render_json` off one model; neither re-derives state.

Tests pin both halves: `tests/context/domains/test_graph_query.py` (synthetic fixture) and `tests/cli/test_graph_command.py` (dispatch contract + read-only smoke on this repo's real artifact, `test_graph_command.py:185-209`).

## Load path (the wire subtlety)

`features/symbol-graph.json` is written by `context/build/graph.py:51-62` as an **undirected** NetworkX node-link export whose links live under the `links` key. NetworkX normalises `source`/`target` on undirected graphs, so the true direction of every link rides in its `_src`/`_tgt` attributes — `_src calls _tgt`, `_src rationale_for _tgt` — and the loader reads **only those** (`load.py:1-8,84-97`), building a directed `nx.MultiDiGraph` (multi because parallel edges of different relations between the same pair are real, e.g. `contains` + `calls`). The unit fixture deliberately scrambles `source`/`target` so a loader that reads the wrong keys fails these tests (`test_graph_query.py:59-73`).

Loading is defensive, not fatal: malformed links and links referencing unknown nodes are skipped (`load.py:84-91`); only a missing file, unreadable/invalid JSON, or a non-node-link payload raises the typed artifact errors (`load.py:57-72`). Docstrings are extracted at load time into a side table `symbol id → rationale node's label text`: a `rationale_for` link attaches its source node's label to the target symbol, and when several rationale nodes attach, the lowest rationale node id wins deterministically (`load.py:98-105`). `repo_root = context_dir.parent` (`load.py:74`); all citations are relativized against it once, at load (`load.py:23-37`).

## Dead-code derivation

`DEPENDENCY_RELATIONS = {calls, uses, imports_from, inherits}` (`enums.py:23-30`) — incoming edges of these relations mean "someone depends on this symbol". A code node (`file_type == "code"`) is dead iff it has **zero** incoming edges among them (`verbs.py:315-336`). The structural relations are deliberately excluded: `contains` (a file containing a function does not use it), `method` (a class owning a method does not call it), `rationale_for` (a docstring is not a caller). `inherits` **does** count — a subclass is a real dependent of its base. Rows sort by `(source_file, line, node id)` (`verbs.py:339-349`) so output is stable across runs. `impact` walks the same relation set in reverse (`verbs.py:174-207`), and `community` ranks members by total in+out dependency degree (`verbs.py:382-390`).

## Forward-compat with the dispatch extractor (A4)

Dead-code precision is exactly the extractor's. The A4 fix — `pipeline/extract/python_dispatch.py` — emits real `calls` edges for enum-keyed dispatch-dict values and `imports_from` edges for function-body imports, graded `INFERRED` / score 0.8 (`python_dispatch.py:1-35`). Because every verb re-derives from edges at query time, those edges flow through with **zero change in this package** (`verbs.py:6-13`); the live artifact already carries 4,250 `INFERRED` `calls` edges. The same posture covers `features/graph-communities.json` (A2, written by `rollup_communities`, `context/domains/features/communities.py:94`): `community` reads it defensively and works with or without it (`verbs.py:405-437`).

## Dependencies

**Upstream (this feature reads their output):**
- `context/build/graph.py` writes `symbol-graph.json` (refreshed by `rebuild --changed` via `context/build/enriched_refresh.py`); `pipeline/extract/` (incl. `python_dispatch.py`) determines edge recall; `analysis/cluster.py` (Leiden) supplies the per-node `community` ints.
- `rollup_communities` writes the `graph-communities.json` cards the `community` verb's slug lookup reads — **optional**: absent/unreadable artifact degrades to int-or-symbol resolution (`verbs.py:415-421`).
- `cli/common.py` — `parse_path_and_root` / `resolve_context_root` / `usage_error` (`cli/graph.py:17,48,117`).

**Downstream (consumers):**
- Only `cli/graph.py`; agents consume the CLI/markdown/JSON contract (documented in the `graph` help slice owned by cli-dispatch, `cli/help.py:245-258`), never the internals.

**Cycles:** none. Intra-package imports run strictly `constants/enums/errors → models → load → resolve → verbs`, with `render` off to the side (`enums` + `models` only).

## Decisions (decided X because Y)

- **Decided to read `_src`/`_tgt` and never `source`/`target`** because the undirected node-link export normalises the latter; direction is the entire product (callers vs. callees). The scrambled-fixture tests make a regression fail loudly (`test_graph_query.py:4-8,59-73`).
- **Decided empty-is-an-answer exit-code semantics** because zero callers is a *finding*, not a failure (it is what `dead-code` hunts for) — exit 0; whereas "no path" / "empty community" mean there was nothing to answer — exit 1 (`cli/graph.py:5-10,182-183`).
- **Decided dead-code counts only dependency relations** because structural membership (`contains`/`method`) keeps everything trivially "alive" and `rationale_for` is documentation, not usage; `inherits` stays in because a subclass genuinely depends on its base (`enums.py:22-30`, pinned by `test_dead_code_is_purely_graph_driven`).
- **Decided the community card carries no partition int** (A2 wire shape) because raw Leiden ids renumber between runs — a card's identity is its slug and its *members*; the int the verbs filter on is recovered from the first card member still present in the loaded graph, and stale member ids are skipped rather than failing the card (`verbs.py:405-456`). The test builds its fixture with the **real** `rollup_communities` so a synthetic `community` key can never false-green a reader (`test_graph_query.py:402-434`).
- **Decided docstring attachment happens once at load, lowest-rationale-id-wins** because query-time answers must be deterministic and cheap; the side table costs one pass over the links (`load.py:83,98-105`).
- **Decided every hop/row annotation is picked by lexicographic minimum** — `_edge_between` sorts `(relation, direction, site)`, `impact`/`neighbors` keep the min relation per node (`verbs.py:193-194,210-226,290-298`) — because multigraph edge iteration order is not a contract; determinism is.
- **Decided the domain import is lazy inside `run()`** so `dispatch --help` paths stay import-light and networkx is only paid for when a graph verb actually runs (`cli/graph.py:25-46`).

## Open questions

- **No load cache.** Every invocation re-parses the full artifact (~1.1 s on this repo — see concerns). Acceptable for one-shot interactive use; an agent looping over verbs pays it per call. Deliberately no store so far; revisit only with evidence.
- **The dead-code note is static** (`verbs.py:331-335`): it still says "until those edges are extracted" although the A4 extractor has landed. Harmless overstatement on a fresh artifact; could become conditional on observing `INFERRED` dispatch edges.
- **`community` ranks by total (in+out) dependency degree** (`verbs.py:382-390`); whether in-degree alone reads better as "importance" is untested.
