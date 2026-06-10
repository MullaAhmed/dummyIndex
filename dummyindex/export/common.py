"""Shared constants and tiny helpers for graph exports."""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

import unicodedata

_CONFIDENCE_SCORE_DEFAULTS = {ConfidenceLevel.EXTRACTED: 1.0, ConfidenceLevel.INFERRED: 0.5, ConfidenceLevel.AMBIGUOUS: 0.2}


def _node_community_map(communities: dict[int, list[str]]) -> dict[str, int]:
    """Invert communities dict: node_id -> community_id."""
    return {n: cid for cid, nodes in communities.items() for n in nodes}


def _strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))
