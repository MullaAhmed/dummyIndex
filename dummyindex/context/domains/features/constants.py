"""Package-private constants for `context/features/`.

Kept out of `enums.py` because they're tunables and string sentinels,
not closed-alphabet enums.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

# `features/graph.json` (the curated scan, a small readable map seeded from
# features/flows and rewritten by `skills/council/58-codebase-scan.md`) is
# versioned independently so feature.json / flow.json / INDEX.json stay on v1.
SCAN_SCHEMA_VERSION = 2

# Caps keep the map readable: the seed meets them by construction and
# `scan.validate` enforces them on the model rewrite. The seed aims at 40-80
# nodes; the cap leaves the council headroom to promote the AI surface.
MAX_SCAN_NODES = 120
MAX_SCAN_EDGES = 240
MAX_TOP_MODELS = 3
MAX_TOP_TOOLS = 10
MAX_TOP_INTEGRATIONS = 10

# Text caps, in characters. Sized to what the viewer can render on one line
# at its node width without ellipsis or reflow.
MAX_NODE_LABEL = 28
MAX_NODE_SUB = 40
MAX_EDGE_LABEL = 24
MAX_NODE_DETAIL = 200
MAX_NODE_SOURCE_REF = 120
# A `symbolRef` is a `features/symbol-graph.json` node id or a
# `graph-communities.json` community slug — same budget as a source ref.
MAX_NODE_SYMBOL_REF = 120
MAX_NODE_GROUP = 24
MAX_PROJECT_NAME = 48
MAX_PROJECT_SLUG = 48
MAX_PROJECT_TAGLINE = 80

# How many of the node budget the seed spends on `service` nodes before it
# starts adding `entry` nodes. Features are the backbone; entry points are
# the garnish, and a repo with 200 flows must not bury its 12 features.
_SEED_SERVICE_SHARE = 0.6

# Hard cap so flows don't blow up on deep call chains. Tunable.
_DEFAULT_FLOW_DEPTH = 6

# Call-like relations that count toward "this function leads to that one".
_CALL_RELATIONS = frozenset({"calls", "uses"})

# HTML-comment sentinels that mark a "merged feature" block inside another
# feature's section file (e.g. `supporting.md`). The block is reopened on
# subsequent merges, never overwritten — see `merge_feature` in `ops.py`.
_MERGE_BEGIN = "<!-- dummyindex:merged:begin -->"
_MERGE_END = "<!-- dummyindex:merged:end -->"

# Maximum docs.md entries per feature.
_FEATURE_DOCS_TOP_N = 10

# Sentinel from `scaffold_feature`/`assign_files`: placed in a reconcile, still owes
# council enrichment. Reported as `awaiting_enrichment`, blocks `reconcile-stamp`
# (unless --force), cleared by `mark-enriched`. Tracked so an abandoned pass stays
# visible next session; explicit because confidence is too indirect a signal.
PENDING_ENRICHMENT_MARKER = ".pending-enrichment"

# Section names `merge_feature` accepts for `--as-section`; anything else is
# rejected so merges can't invent ad-hoc section files nobody reads. Extending
# it is a spec change — update `dummyindex/skills/council/18-filter-trivial.md`.
_VALID_MERGE_SECTIONS = frozenset({"supporting"})
