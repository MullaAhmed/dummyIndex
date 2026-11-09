"""Detect features and flows; emit `.context/features/`.

Two deterministic passes: each graph community becomes a feature, and each
in-degree-0 node of the `calls`/`uses` subgraph seeds a BFS flow attached to its
community. Writes `INDEX.{json,md}`, `HOW_TO_NAVIGATE.md`, `graph.{json,html}`
(curated scan v2) and per feature `feature.json`, `spec.md`, `flows/<id>.{json,md}`.
All start `EXTRACTED` (enrichment flips to `INFERRED`); `__all__` is the stable API.
"""

from __future__ import annotations

from .builder import scaffold_features
from .constants import PENDING_ENRICHMENT_MARKER, SCHEMA_VERSION
from .errors import FeatureRenameError
from .indexes import rebuild_features_graph, refresh_features_index_md
from .models import (
    Feature,
    Flow,
    FlowStep,
    MergeResult,
    PlacementResult,
    RemoveResult,
    RenameResult,
    ScaffoldResult,
)
from .ops import merge_feature, remove_flow, rename_feature, write_section
from .placement import (
    assign_files,
    clear_pending_enrichment,
    remove_feature,
    scaffold_feature,
    unassign_files,
)

__all__ = [
    "Feature",
    "FeatureRenameError",
    "Flow",
    "FlowStep",
    "MergeResult",
    "PENDING_ENRICHMENT_MARKER",
    "PlacementResult",
    "RemoveResult",
    "RenameResult",
    "SCHEMA_VERSION",
    "ScaffoldResult",
    "assign_files",
    "clear_pending_enrichment",
    "merge_feature",
    "rebuild_features_graph",
    "refresh_features_index_md",
    "remove_feature",
    "remove_flow",
    "rename_feature",
    "scaffold_feature",
    "scaffold_features",
    "unassign_files",
    "write_section",
]
