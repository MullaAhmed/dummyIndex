"""Frozen dataclasses for features + flows.

Persisted as JSON under ``.context/features/`` — schema versioned by
``constants.SCHEMA_VERSION``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dummyindex.pipeline.enums import ConfidenceLevel

from .constants import SCHEMA_VERSION


@dataclass(frozen=True)
class FlowStep:
    depth: int
    node_id: str
    label: str
    path: str | None
    range: list[int] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "node_id": self.node_id,
            "label": self.label,
            "path": self.path,
            "range": self.range,
        }


@dataclass(frozen=True)
class Flow:
    flow_id: str
    feature_id: str
    entry_point: str
    entry_point_label: str
    entry_point_path: str | None
    steps: tuple[FlowStep, ...]
    files: tuple[str, ...]
    confidence: str = ConfidenceLevel.EXTRACTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "flow_id": self.flow_id,
            "feature_id": self.feature_id,
            "entry_point": self.entry_point,
            "entry_point_label": self.entry_point_label,
            "entry_point_path": self.entry_point_path,
            "steps": [s.to_dict() for s in self.steps],
            "files": list(self.files),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Feature:
    feature_id: str
    kind: str  # "community" for now; "entry_point_group" reserved
    name: str
    summary: str | None
    members: tuple[str, ...]
    files: tuple[str, ...]
    entry_points: tuple[str, ...]
    flow_ids: tuple[str, ...]
    confidence: str = ConfidenceLevel.EXTRACTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "feature_id": self.feature_id,
            "kind": self.kind,
            "name": self.name,
            "summary": self.summary,
            "members": list(self.members),
            "files": list(self.files),
            "entry_points": list(self.entry_points),
            "flow_ids": list(self.flow_ids),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ScaffoldResult:
    features_dir: Path
    features: tuple[Feature, ...]
    flows: tuple[Flow, ...]
    written: tuple[str, ...]


@dataclass(frozen=True)
class RenameResult:
    from_id: str
    to_id: str
    new_name: str | None
    new_summary: str | None
    files_touched: tuple[str, ...]


@dataclass(frozen=True)
class MergeResult:
    """Outcome of `merge_feature` — source folder deleted, target absorbed it."""

    from_id: str
    to_id: str
    section: str
    files_touched: tuple[str, ...]


@dataclass(frozen=True)
class RemoveResult:
    """Outcome of `remove_feature` — a feature folder + its index entries gone."""

    feature_id: str
    files_touched: tuple[str, ...]


@dataclass(frozen=True)
class PlacementResult:
    """Outcome of `scaffold_feature` / `assign_files` — a feature gained files.

    `created` distinguishes a brand-new feature (`scaffold_feature`) from an
    extension of an existing one (`assign_files`). `files` is the feature's
    full repo-relative file list after the op (not just the added ones).
    """

    feature_id: str
    created: bool
    files: tuple[str, ...]
    members: tuple[str, ...]
    files_touched: tuple[str, ...]
