# Symbol-graph query verbs — spec

confidence: INFERRED

Output is capped at 16,000 serialized bytes without cutting JSON records. ID
collisions preserve distinct definitions; legacy ambiguous IDs list cited choices.
Unknown call targets show explicit candidates and never prove those candidates
have zero callers. Collision-affected IDs may change when the scan gains a conflict.

## Intent

Answer the relational questions token-overlap retrieval cannot: who calls this, what breaks if I change it.

`dummyindex context graph <verb>` runs seven bounded query verbs over `features/symbol-graph.json`.
It is the full extracted node-link artifact the curated scan keeps off-screen.
The verbs use no database, no LLM, and no new store.
The artifact loads read-only into a directed multigraph.
Every answer is bounded, deterministically ordered, and cited `path:line` (`dummyindex/context/domains/graph_query/__init__.py:1-28`).
Docstrings ride along from co-located `rationale_for` nodes, so an answer explains itself without a follow-up read (`load.py:98-113`, `verbs.py:57-77`).

The CLI is wire-only per the CLI contract.
It parses flags, delegates to the domain package, prints, and returns an exit code (`dummyindex/cli/graph.py:1-11`).
The `graph --help` slice, owned by cli-dispatch (`dummyindex/cli/help.py:245-258`), is pinned to list every verb (`tests/cli/test_graph_command.py:32-49`).

## User-visible behavior

`dummyindex context graph <callers-of|callees-of|impact|path|neighbors|dead-code|community> [SYMBOL] [SYMBOL2] [--limit N] [--depth N] [--hops N] [--json]` (usage string, `cli/graph.py:82-87`).

- **The seven verbs** (closed alphabet `GraphVerb`, `enums.py:33-44`; arity table `cli/graph.py:97-105`):
  - `callers-of SYMBOL` — direct incoming `calls` edges: who calls this, and where (`verbs.py:110-120`).
  - `callees-of SYMBOL` — direct outgoing `calls` edges (`verbs.py:123-133`).
  - `impact SYMBOL` — transitive dependents: reverse walk over dependency edges (`calls`/`uses`/`imports_from`/`inherits`), capped at `--depth` (default 2) (`verbs.py:174-207`).
  - `path SYMBOL SYMBOL2` — shortest undirected chain between two symbols, each hop annotated with its relation, direction, and site (`verbs.py:229-267`). `rationale_for` edges never route.
  - `neighbors SYMBOL` — every node within `--hops` (default 1) over any relation except `rationale_for`, both directions (`verbs.py:270-312`).
  - `dead-code` — code nodes with zero incoming dependency edges (`verbs.py:315-336`). Structural relations (`contains`/`method`/`rationale_for`) never count as usage. Results sort by file, then line.
  - `community KEY` — members of one Leiden community, ranked by dependency degree (`verbs.py:352-379`).
  - `KEY` is a community int, a slug/name from `features/graph-communities.json`, or any symbol form. A symbol form falls back to that symbol's own community.
- **Bounded output** — results clip rows to `--limit` (default 20; `dead-code` default 50). They keep the pre-truncation `total` and a `truncated` flag. Markdown shows `N of M row(s) (truncated by --limit)` (`verbs.py:85-104`, `constants.py:7-8`, `render.py:26-27`).
- **`file:line` citations** — every row cites its definition site, repo-relative (`src/app.py:L10`). Edge-backed rows also cite the connecting edge's site (`at src/app.py:L14`). Missing data degrades to `L?` / `?`; rows are never omitted (`load.py:23-45`, `models.py:29`, `render.py:31-45`).
- **Docstring attachment** — a symbol's `rationale_for` neighbor text attaches to its subject line and rows. The text is whitespace-flattened and clipped to 120 chars. When several rationale nodes attach, the lowest rationale node id wins deterministically (`load.py:98-113`, `verbs.py:41-47`, `constants.py:12`).
- **Symbol resolution** — a symbol operand is tried in order (`resolve.py:54-106`):
  - Exact node id (`app_main`).
  - Case-insensitive bare name (`helper`, `run`, `app.py`). Function/method labels reduce to the bare callable name; classes/modules keep the whole label.
  - `path:name` suffix (`cli/common.py:resolve_context_root`), matched on a path boundary, backslash-tolerant.
  - Finally, an unambiguous prefix of a node id or bare name.
  Rationale nodes are never lookup targets (`resolve.py:25-31`).
- **Ambiguity listing** — several matches raise `AmbiguousSymbolError`. The CLI prints `error: ambiguous symbol 'X': N candidates`, then up to 10 cited candidates (`id — label (path:Lnn)`) and `… and K more` (`cli/graph.py:170-176`, `resolve.py:45-51`, `constants.py:11`).
- **Flags** — `--limit`/`--depth`/`--hops` accept both `--flag N` and `--flag=N`. A non-integer or `< 1` value is a usage error, exit 2 (`cli/graph.py:60-76`). `--depth` only applies to `impact`; `--hops` only to `neighbors`. Both are rejected elsewhere (`cli/graph.py:112-115`). Unknown flags are rejected (`cli/graph.py:77-78`). `--root` is handled by the shared `parse_path_and_root`. `graph` takes no positional path (`cli/graph.py:48`).
- **`--json`** — emit `render_json` (indented `to_dict()`) instead of the default `render_markdown` (`cli/graph.py:50-59,181`; `render.py:49-50`). Optional row fields are absent, never `null` (`models.py:12-15,40-43`).
- **Exit codes** (`cli/graph.py:5-11`):
  - `0` — the query was answered, and a valid *empty* answer counts (zero callers is what `dead-code` hunts for).
  - `1` — nothing to answer: unknown or ambiguous symbol, no path between the endpoints, empty community (`cli/graph.py:170-183`).
  - `2` — usage error, or no `features/symbol-graph.json` (with a `run \`dummyindex ingest\`` hint) / invalid artifact (`cli/graph.py:117-129`).

## Contracts

Public surface re-exported from `dummyindex/context/domains/graph_query/__init__.py:61-90`:

- Verbs — `callers_of(graph, node_id, *, limit=20)`, `callees_of(...)`, `impact(graph, node_id, *, depth=2, limit=20)`, `path_between(graph, a_id, b_id, *, limit=20)`, `neighbors(graph, node_id, *, hops=1, limit=20)`, `dead_code(graph, *, limit=50)`, `community(graph, key, *, limit=20)`. Each returns `GraphQueryResult` (`verbs.py`).
- `load_symbol_graph(context_dir: Path) -> SymbolGraph` — raises `GraphArtifactMissingError` / `GraphArtifactInvalidError` (typed, path-carrying); read-only (`load.py:48-113`, `errors.py:12-26`).
- `resolve_symbol(graph: SymbolGraph, query: str) -> str` — raises `AmbiguousSymbolError` (with `.candidates` + `.total`) / `UnknownSymbolError` (`resolve.py:54-106`, `errors.py:29-44`).
- `render_markdown(result) -> str` / `render_json(result) -> str` (`render.py:11-50`).
- Frozen models, both `to_dict()` with optional-means-absent (`models.py:18-71`):
  - `GraphRow` (node_id, label, citation, community, depth, optional relation/direction/site/docstring).
  - `GraphQueryResult` (schema_version, verb, args, subject, total, truncated, rows, optional note).
- `SymbolGraph` is the loaded-artifact carrier, not a wire model (`models.py:74-88`).
- Errors rooted at `GraphQueryError` (`errors.py:8-9`); enums `GraphRelation`, `GraphVerb`, `EdgeDirection`, and `DEPENDENCY_RELATIONS` (`enums.py`).
- `SCHEMA_VERSION = 1` carried on every result (`constants.py:5`, `verbs.py:96`).
- CLI entry `run(args: list[str]) -> int` (`cli/graph.py:23`), registered under `ContextSubcommand.GRAPH` (`tests/cli/test_graph_command.py:27-28`).

Pinned by `tests/context/domains/test_graph_query.py`, a synthetic fixture that scrambles `source`/`target` so only a `_src`/`_tgt` reader passes.
Also pinned by `tests/cli/test_graph_command.py`: wire contract plus a read-only smoke over this repo's real artifact, asserting only stable shapes.

## Examples

```
$ dummyindex context graph callers-of lib.py:util
# graph callers-of lib_util

Subject: `util()` `lib_util` — src/lib.py:L5 (community 1)

_1 of 1 row(s)._

- `main()` `app_main` — src/app.py:L10  [depth 1, ←calls, at src/app.py:L14]
  > Entry point of the app.
```

```
$ dummyindex context graph dead-code --limit 2
# graph dead-code

_2 of 7 row(s) (truncated by --limit)._
_graph-driven precision: symbols reached only via dispatch-dict values or function-body imports may be false positives until those edges are extracted_

- `app.py` `app_py` — src/app.py:L1
- `main()` `app_main` — src/app.py:L10
  > Entry point of the app.
```

```
$ dummyindex context graph callers-of util
error: ambiguous symbol 'util': 2 candidates
  lib_util — util() (src/lib.py:L5)
  other_util — util() (src/other.py:L8)
# exit 1
```
