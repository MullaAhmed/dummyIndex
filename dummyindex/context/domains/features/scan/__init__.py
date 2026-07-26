"""The curated codebase scan — `features/graph.json`, schema v2.

One map holding both halves of a project: the AI surface (agents, the
models they call, the tools those models can reach) and the business logic
the product is actually built from (entry points, scheduled jobs, internal
services, datastores, third-party APIs). Nodes are boxes; the interesting
sentence goes on the *edge* ("charges Stripe on trial end").

Three pieces, in the order they run:

1. `seed_scan` — deterministic backbone from extracted features and flows.
   Written at ingest, `confidence: EXTRACTED`.
2. The authoring stage (`skills/council/58-codebase-scan.md`) rewrites it
   against real source, filling in the AI surface and the group layout,
   and flips `confidence` to `INFERRED`.
3. `validate_scan` — the boundary check the author loops against, surfaced
   as `dummyindex context scan-check`.

Rebuilds preserve an `INFERRED` scan and regenerate an `EXTRACTED` one,
the same contract that protects an enriched `spec.md`.
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
