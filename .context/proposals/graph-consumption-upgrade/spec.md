# Graph consumption upgrade

## Problem

The schema-v2 curated scan (commit 53eeca3) fixed the v1 hairball (4,083 nodes /
8,062 edges, unreadable) but over-corrected: the visible graph is now capped at
60 nodes and, on this repo, sits at the degenerate 26-service seed because the
council authoring stage never ran. Meanwhile the full detail — 6,387 nodes,
18,326 typed edges (`calls`/`uses`/`contains`/`imports_from`/`inherits`/`method`
plus 2,159 `rationale_for` docstring links), 47 Leiden communities, source
locations on 99.9% of nodes — sits unused in the 11MB
`features/symbol-graph.json`. The complaint "not detailed enough, not useful
enough" is a **consumption gap, not an extraction gap**.

## Evidence (bakeoff, 2026-07-24)

Three reference tools were run on a clone of this repo and opus-audited against
8 fixed benchmark questions (max 16): **code-review-graph 15/16** (query-first
bounded verbs + community-aggregate progressive-disclosure viewer),
**graphify 11/16** (same NetworkX node-link format as ours; viz skips HTML above
5k nodes), **GitNexus 8/16** (richest model — Cypher, per-edge provenance — but
Node/KuzuDB stack, no offline HTML, silent gitignore anchoring bug dropped 35
`build/` files). Web research independently converged on the same missing
pieces: aider's personalized-PageRank ranked shortlist, GraphRAG Leiden
community summaries, CodexGraph-style query surface, Sourcetrail focus+expand.
All three tools shared one blind spot **our own extractor also has**: dummyindex's
enum-keyed dict dispatch and function-local imports produce false "zero callers".
Full evidence: bakeoff scratch dirs + `RESULTS-*.md` (session scratchpad).

## Intent

Keep both layers of the two-layer contract and connect them:

1. **Query surface** (`dummyindex context graph <verb>`) over the existing
   `symbol-graph.json` — bounded, file:line-cited answers for agents and humans:
   `callers-of`, `callees-of`, `impact`, `path`, `neighbors`, `dead-code`,
   `community`. No new store, no DB, no new deps (networkx already present).
2. **Deterministic ranked seed**: personalized PageRank over the symbol graph
   (seeded on entry points, down-weighting test files) + greedy fill to a node
   budget produces the council's draft — "edit a ranked shortlist", not "invent
   boxes from a blank page". Reproducible selection replaces keep-a-third-by-feel.
3. **Community mid-tier**: `features/graph-communities.json` (EXTRACTED,
   rebuild-regenerated) — one card per Leiden community: stable name, size, top
   members by PageRank, owning feature. The drill path becomes curated map →
   community → symbol neighborhood.
4. **Schema v2 extension (backward-compatible)**: optional `symbolRef` +
   `evidence` (EXTRACTED|INFERRED) per ScanNode; node cap 60 → 120;
   `scan-check` validates the new fields and cross-artifact referential
   integrity.
5. **Viewer three-tier zoom + focus+expand**: curated map (default) ↔ community
   aggregate ↔ per-node symbol neighborhood, from a bounded precomputed
   expansion index inlined into `graph.html` (top-k neighbors per curated node,
   total budget ≤ 300KB). EXTRACTED vs INFERRED rendered distinctly. Stays a
   single offline self-contained file, no CDN.
6. **Extractor dispatch fix (narrow)**: resolve enum-keyed dict-literal
   `module.attr` handler values and function-body imports into `calls`/
   `imports_from` edges so `dead-code`/`callers-of` don't inherit the blind spot
   every reference tool showed.
7. **Council prompt rewrite** (`skills/council/58-codebase-scan.md`): consume
   the ranked seed + community scaffold; require `symbolRef` on repo-owned
   nodes and per-node `evidence`.

## Contracts

- `graph.json` stays the INFERRED overlay `rebuild --changed` preserves;
  `graph-communities.json` + the ranked seed are EXTRACTED backbone it
  regenerates. Nothing about `symbol-graph.json`'s wire shape changes.
- Old scans (no `symbolRef`/`evidence`) still validate — additive only.
- Viewer output remains one offline HTML file; expansion data is precomputed
  and size-capped, never the full 11MB graph.
- Query verbs are read-only and bounded (depth/度 caps with explicit flags).

## Non-goals

- No MCP server (CLI + skill docs only, for now).
- No new extraction languages or general-purpose dynamic-dispatch resolution —
  only the narrow enum-dict + local-import patterns, behind tests.
- No replacement of the curated council stage — it is upgraded, not removed.
