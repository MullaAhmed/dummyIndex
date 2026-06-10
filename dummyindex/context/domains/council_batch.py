"""Parallel-council batch frontier — the council twin of build's `next_wave`.

The serial council loop processed one feature at a time. This module computes,
deterministically and with no LLM, the *earliest incomplete stage* across all
non-trivial features and the dispatch-units for that stage, so the council
skill can fan independent features out to parallel Task subagents.

Stage numbers match the council-log convention (`council/00-overview.md`):
specify=1, plan=2, critique=3 — extended here with flow=4, tree-enrich=5.
"""
from __future__ import annotations

from enum import Enum, IntEnum
from pathlib import Path
from typing import Optional

from dummyindex.context.domains.council import is_stage_complete


class CouncilStage(IntEnum):
    """The ordered council stages, numbered as written to `_council-log.json`."""

    SPECIFY = 1
    PLAN = 2
    CRITIQUE = 3
    FLOW = 4
    TREE = 5


class CouncilMode(str, Enum):
    """Council depth modes (passed via `/dummyindex --mode`)."""

    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


def active_stages(mode: CouncilMode, *, tree_enrich: bool) -> tuple[CouncilStage, ...]:
    """The stages that actually run for ``mode``.

    light = dev only (specify) + flow; standard/deep add plan + critique.
    Tree-enrich is mode-gated and appended only when ``tree_enrich`` is set.
    """
    stages: list[CouncilStage] = [CouncilStage.SPECIFY]
    if mode in (CouncilMode.STANDARD, CouncilMode.DEEP):
        stages.append(CouncilStage.PLAN)
        stages.append(CouncilStage.CRITIQUE)
    stages.append(CouncilStage.FLOW)
    if tree_enrich:
        stages.append(CouncilStage.TREE)
    return tuple(stages)


def earliest_incomplete_stage(
    features_dir: Path,
    feature_ids: tuple[str, ...],
    *,
    mode: CouncilMode,
    tree_enrich: bool,
) -> Optional[CouncilStage]:
    """The lowest active stage not yet complete for *every* feature, or None.

    A stage ``S`` is the frontier iff at least one feature has not completed it.
    Returns None when every feature has completed every active stage.
    """
    for stage in active_stages(mode, tree_enrich=tree_enrich):
        if any(
            not is_stage_complete(features_dir, fid, int(stage))
            for fid in feature_ids
        ):
            return stage
    return None


def _prior_active_stage(
    stage: CouncilStage, mode: CouncilMode, *, tree_enrich: bool
) -> Optional[CouncilStage]:
    """The active stage immediately before ``stage``, or None if it is first."""
    stages = active_stages(mode, tree_enrich=tree_enrich)
    idx = stages.index(stage)
    return stages[idx - 1] if idx > 0 else None


def _feature_ready_for(
    features_dir: Path,
    feature_id: str,
    stage: CouncilStage,
    mode: CouncilMode,
    *,
    tree_enrich: bool,
) -> bool:
    """True iff ``feature_id`` needs ``stage`` and its prior active stage is done."""
    if is_stage_complete(features_dir, feature_id, int(stage)):
        return False  # already done this stage
    prior = _prior_active_stage(stage, mode, tree_enrich=tree_enrich)
    if prior is None:
        return True
    return is_stage_complete(features_dir, feature_id, int(prior))
