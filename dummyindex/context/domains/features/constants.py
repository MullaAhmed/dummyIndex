"""Package-private constants for `context/features/`.

Kept out of `enums.py` because they're tunables and string sentinels,
not closed-alphabet enums.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

# `features/graph.json` has its own lineage. v1 was a denormalized dump of the
# whole extraction (folder → file → class → method → feature → flow): on a
# mid-size repo that is ~4k nodes / ~8k edges — complete, and unreadable. v2 is
# the *curated scan*: a small map a teammate can hold in their head, seeded
# deterministically from features/flows and then rewritten by the authoring
# council stage (`skills/council/55-codebase-scan.md`). Bumped independently of
# SCHEMA_VERSION so feature.json / flow.json / INDEX.json stay on v1.
SCAN_SCHEMA_VERSION = 2

# Caps. These are the whole point of the artifact — a map that cannot exceed
# them is a map that stays readable. The seed enforces them by construction;
# `scan.validate` enforces them on the model-authored rewrite. Doubled from
# 60/120 by the graph-consumption upgrade (proposal A3): the ranked seed aims
# at 40-80 nodes, and the hard cap leaves the council headroom to promote the
# AI surface without cutting the business logic.
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
# A `symbolRef` is a `features/symbol-graph.json` node id (or, once the
# community roll-up lands, a `graph-communities.json` community id) — same
# budget as a source ref.
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

# Sentinel file the placement ops (`scaffold_feature` / `assign_files`) drop
# into a feature folder to flag "placed during a reconcile, still owes council
# (re-)enrichment". The reconcile report surfaces these as
# `awaiting_enrichment`; `reconcile-stamp` refuses to advance the anchor while
# any remain (overridable with --force); `mark-enriched` clears one.
#
# Tracked (NOT gitignored) so it survives a session restart — restart-safe
# reconcile is the whole point: a feature scaffolded then abandoned mid-pass
# must still be visible as "needs enrichment" in the next session. It can't be
# inferred from confidence (a scaffold output is non-`community-*` + EXTRACTED,
# which a renamed-then-skipped trivial feature is NOT — rename flips to
# INFERRED — but the signal is indirect and would drift if rename semantics
# changed). An explicit marker is unambiguous and self-documenting.
PENDING_ENRICHMENT_MARKER = ".pending-enrichment"

# Section names `merge_feature` will accept for `--as-section`. Anything
# outside this set is rejected to prevent ad-hoc audit files (e.g. the
# `noise-absorbed.md` pattern observed in prior consolidation passes,
# where 21 parser-artifact features were glued into unrelated parents
# under an invented section name that no reader ever looked at).
#
# Extending the set is a deliberate spec change — update
# `dummyindex/skills/council/18-filter-trivial.md` at the same time.
_VALID_MERGE_SECTIONS = frozenset({"supporting"})
