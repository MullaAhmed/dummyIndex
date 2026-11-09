# Symbol-graph query verbs — concerns

## Data integrity

Read-only queries over `.context/` JSON; no writes, so no write-integrity exposure.
The concerns are input fidelity.
The reader is only as truthful as the artifact.
Two items below are **upstream artifact bugs this feature faithfully reproduces**, not defects in the reader itself.

- **Rationale node-id collisions in the artifact cross-wire docstrings across same-named files (upstream bug; observed live).**
  Rationale node ids are minted from *module stem + line* (`common_rationale_16`).
  So all five `common.py` files in this repo share one id namespace.
  A docstring node minted from one file can be wired to a symbol in another.
  Verified against the live artifact (2026-07-25): **173** `rationale_for` links whose rationale node's `source_file` differs from its target symbol's.
  For example, `common_rationale_16` from `pipeline/extract/common.py` attaches to `common_resolve_context_root`, defined in `dummyindex/cli/common.py`.
  So `graph callers-of resolve_context_root` prints another file's docstring under the subject.
  **Mitigated as of `acd07cb`**: `load.py`'s co-located-`source_file` guard now suppresses cross-file rationale attachment at the query surface.
  The ~173 cross-file `rationale_for` links (upstream id-collision root cause) still exist in the artifact.
  The loader's lowest-id tiebreak (`load.py:98-113`) is deterministic but cannot repair a miswired edge.
  The fix belongs upstream in id minting (`pipeline/extract/common.py:_make_id`), not in this reader.
  Do not "fix" it here.

- **Staleness: every answer is as of the last rebuild.**
  `load_symbol_graph` reads the committed artifact with no drift check, no mtime warning, and no in-band freshness signal.
  A `callers-of` run hours after an edit cites line numbers that may have moved.
  Rows render identically to fresh ones.
  Same posture, and same gap, as context-query's stale-index concern.
  Related: citations are relativized against `repo_root = context_dir.parent` at load (`load.py:74,23-31`).
  An artifact whose `source_file` paths were recorded under a different absolute root silently degrades to absolute-path citations.
  The `relative_to` fallback keeps the raw path.

- **The dead-code note is unconditional and now overstates imprecision.**
  The note "…may be false positives until those edges are extracted" ships on every `dead-code` result (`verbs.py:331-335`).
  The A4 dispatch extractor landed in the same commit (1921bbf).
  The live artifact already carries the `INFERRED` dispatch edges (4,250 `calls`, 6 `imports_from`).
  On a freshly rebuilt artifact the caveat is stale-leaning.
  Cosmetic.
  Consider conditioning it on the absence of `INFERRED` dispatch edges, or rewording.

- **`community`'s slug path depends on the `graph-communities.json` wire shape.**
  An all-stale card degrades to a misleading error.
  Slug resolution assumes cards shaped `{communities: [{slug, name?, members: [{id, …}]}]}`.
  They carry **no partition int** on the wire, deliberately, because Leiden ids renumber (`verbs.py:405-437`).
  The filter int is recovered from the first card member still present in the graph (`verbs.py:440-456`).
  Stale members are skipped.
  Two consequences:
  - First, any upstream rename of `slug`/`name`/`members[].id` silently breaks slug lookup. The defensive parse returns `None`, and the key falls through to symbol resolution.
  - Second, a card **all** of whose members have been renamed away resolves the same way. The user sees `unknown symbol: 'the-slug'` (exit 1) even though the card exists. Stale members, not unknown slug, is the truth.
  The wire shape is pinned the right way: `test_community_by_slug_reads_graph_communities_artifact` builds its fixture with the real `rollup_communities` (`test_graph_query.py:402-434`).
  So a shape change breaks the test before it breaks users.

## Security

Local, single-user, read-only CLI over first-party `.context/` artifacts.
Same narrow threat model as context-query: a hostile or corrupt artifact (e.g. a cloned repo's committed index) and nothing else.
Verdict: **no exploitable vulnerability; two informational notes.**

- **No path traversal surface.**
  The loader opens exactly two fixed paths under `context_dir`: `features/symbol-graph.json` (`load.py:56`) and `features/graph-communities.json` (`verbs.py:415`).
  Node `source_file` strings from the artifact are only ever *printed* as citations.
  They are never opened, so a hostile artifact cannot steer reads.
  Both parses are defensively typed.
  Typed errors cover a missing or invalid graph (`load.py:57-72`).
  An unreadable communities file yields silent `None` (`verbs.py:418-421`).
  Malformed nodes and links are skipped (`load.py:76-91`).

- **Labels and docstrings are echoed verbatim to stdout** (`render.py:20-45`).
  A hostile artifact could embed terminal control sequences in a node label or rationale text.
  Informational, same class as context-query's excerpt surfacing.
  The data is first-party plaintext the caller already owns.
  Nothing is logged, cached, or transmitted.

## Product surface

User lens: a developer (or agent) asking who-calls, what-breaks, or what's-dead before an edit.
Verdict: answers are cited and deterministic.
But every call pays a full artifact load, and a couple of failure modes read worse than they are.

- **~1.1 s artifact load on every invocation, no cache.**
  `load_symbol_graph` re-parses the full 11.7 MB node-link JSON.
  It rebuilds a 6.8k-node / 19.5k-edge `MultiDiGraph` per CLI call (measured on this repo).
  One-shot interactive use is fine.
  An agent chaining `callers-of` → `impact` → `neighbors` pays the load three times.
  There is deliberately no store or daemon.
  If looping agents become the dominant caller, measure before adding one.
- **Exit 1 conflates three different "nothing to answer" cases** — unknown symbol, ambiguous symbol, and no-path/empty-community (`cli/graph.py:170-183`).
  A script cannot distinguish "typo" from "genuinely disconnected" without parsing stderr/stdout text.
- **Ambiguity is capped, not pageable.**
  `AmbiguousSymbolError` lists at most 10 cited candidates plus `… and K more` (`constants.py:11`, `cli/graph.py:172-175`).
  A very common bare name (`run`, `to_dict`) leaves the user to re-query with a `path:name` suffix.
  That is the right escape hatch, but nothing in the error suggests that form.
- **Dead-code output is a lead, not a verdict.**
  Precision is the extractor's (see the note concern above).
  Consumers, including the GC sweep, must treat rows as candidates for the implementer+tester path.
  They are never safe-to-delete facts.
  The per-result note carries this caveat in-band, which is the correct default.
