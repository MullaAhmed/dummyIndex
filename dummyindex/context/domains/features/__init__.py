"""Detect features and flows; emit `.context/features/`.

Two passes, both deterministic:

1. **Community-based features** — every Leiden community in
   `graph/graph.json` becomes a candidate feature. Covers the whole
   codebase coarsely.
2. **Entry-point-based flows** — functions with in-degree 0 in the
   call subgraph (`calls` / `uses` edges) are likely user-facing entry
   points (HTTP handlers, CLI commands, public APIs). For each, a BFS
   over the call graph captures the ordered flow of calls. The flow
   gets attached to the community that contains its entry point.

Output:

    .context/features/
    ├── INDEX.json             # machine-readable list (the agent's nav)
    ├── INDEX.md               # human-readable summary
    ├── HOW_TO_NAVIGATE.md     # agent navigation guide
    ├── graph.json             # denormalized graph for the HTML viewer
    └── <feature-id>/
        ├── feature.json       # canonical machine description
        ├── spec.md            # human-readable entry point
        └── flows/
            ├── <flow-id>.json # ordered call sequence
            └── <flow-id>.md   # human-readable flow doc

The /dummyindex skill enriches names / summaries / flow narratives on
top of this scaffolding (every node carries `confidence: "EXTRACTED"`
initially; enrichment flips to `"INFERRED"`).

Public surface (kept stable for ``context/cli/*`` and tests):

- Dataclasses: ``Feature``, ``Flow``, ``FlowStep``, ``ScaffoldResult``,
  ``RenameResult``, ``MergeResult``
- Exception: ``FeatureRenameError``
- Operations: ``scaffold_features``, ``rename_feature``, ``merge_feature``,
  ``remove_flow``, ``write_section``
- Index rebuilders: ``refresh_features_index_md``, ``rebuild_features_graph``
"""
from __future__ import annotations

from ._constants import PENDING_ENRICHMENT_MARKER, SCHEMA_VERSION
from .builder import scaffold_features
from .errors import FeatureRenameError
from .indexes import rebuild_features_graph, refresh_features_index_md
from .models import (
    Feature,
    Flow,
    FlowStep,
    MergeResult,
    PlacementResult,
    RenameResult,
    ScaffoldResult,
)
from .ops import merge_feature, remove_flow, rename_feature, write_section
from .placement import assign_files, clear_pending_enrichment, scaffold_feature

__all__ = [
    "Feature",
    "FeatureRenameError",
    "Flow",
    "FlowStep",
    "MergeResult",
    "PENDING_ENRICHMENT_MARKER",
    "PlacementResult",
    "RenameResult",
    "SCHEMA_VERSION",
    "ScaffoldResult",
    "assign_files",
    "clear_pending_enrichment",
    "merge_feature",
    "rebuild_features_graph",
    "refresh_features_index_md",
    "remove_flow",
    "rename_feature",
    "scaffold_feature",
    "scaffold_features",
    "write_section",
]
