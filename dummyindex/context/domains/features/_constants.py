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
# feature's README. The block is reopened on subsequent merges, never
# overwritten — see `merge_feature` in `ops.py`.
_MERGE_BEGIN = "<!-- dummyindex:merged:begin -->"
_MERGE_END = "<!-- dummyindex:merged:end -->"

# Maximum docs.md entries per feature.
_FEATURE_DOCS_TOP_N = 10
