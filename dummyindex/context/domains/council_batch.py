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
