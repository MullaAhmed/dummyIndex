"""Package-private constants for `context/features/`.

Kept out of `enums.py` because they're tunables and string sentinels,
not closed-alphabet enums.
"""
from __future__ import annotations

SCHEMA_VERSION = 1

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

# Section names `merge_feature` will accept for `--as-section`. Anything
# outside this set is rejected to prevent ad-hoc audit files (e.g. the
# `noise-absorbed.md` pattern observed in prior consolidation passes,
# where 21 parser-artifact features were glued into unrelated parents
# under an invented section name that no reader ever looked at).
#
# Extending the set is a deliberate spec change — update
# `dummyindex/skills/council/filter-trivial.md` at the same time.
_VALID_MERGE_SECTIONS = frozenset({"supporting"})
