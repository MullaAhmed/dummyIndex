"""Tunables and wire-vocabulary constants for the graph-query domain."""

from __future__ import annotations

SCHEMA_VERSION = 1

DEFAULT_LIMIT = 20
DEFAULT_DEAD_CODE_LIMIT = 50
DEFAULT_IMPACT_DEPTH = 2
DEFAULT_NEIGHBOR_HOPS = 1
MAX_CANDIDATES_LISTED = 10
DOCSTRING_CLIP_CHARS = 120

FILE_TYPE_RATIONALE = "rationale"
FILE_TYPE_CODE = "code"
COMMUNITIES_ARTIFACT = "graph-communities.json"
