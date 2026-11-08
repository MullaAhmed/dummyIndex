"""The curated codebase scan — `features/graph.json`, schema v2.

One map of the AI surface and the business logic; the interesting sentence goes
on the *edge*. `seed_scan` writes the `EXTRACTED` backbone at ingest,
`skills/council/58-codebase-scan.md` rewrites it to `INFERRED`, `validate_scan`
(`dummyindex context scan-check`) is the boundary check. Rebuilds keep an
`INFERRED` scan and regenerate an `EXTRACTED` one.
"""

from __future__ import annotations

from .models import Scan, ScanChip, ScanEdge, ScanNode, ScanProject, ScanStats
from .mutate import drop_feature, drop_nodes, rename_node
from .rank import RankEntry, SeedRank, load_seed_rank
from .refs import SymbolRefIndex, load_symbol_ref_index
from .seed import seed_scan, slugify
from .validate import ScanViolation, validate_scan

__all__ = [
    "RankEntry",
    "Scan",
    "ScanChip",
    "ScanEdge",
    "ScanNode",
    "ScanProject",
    "ScanStats",
    "ScanViolation",
    "SeedRank",
    "SymbolRefIndex",
    "drop_feature",
    "drop_nodes",
    "load_seed_rank",
    "load_symbol_ref_index",
    "rename_node",
    "seed_scan",
    "slugify",
    "validate_scan",
]
