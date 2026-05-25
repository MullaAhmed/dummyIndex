"""Shared constants and tiny helpers for graph exports."""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

import unicodedata

COMMUNITY_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

MAX_NODES_FOR_VIZ = 5_000

_CONFIDENCE_SCORE_DEFAULTS = {ConfidenceLevel.EXTRACTED: 1.0, ConfidenceLevel.INFERRED: 0.5, ConfidenceLevel.AMBIGUOUS: 0.2}


def _strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))
